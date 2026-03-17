<workflow_goal>
Run a Feynman-style active recall loop: challenge → attempt → assess → teach gaps → re-attempt, iterating until the user achieves mastery (Level 3+) or pauses. Works both inside an initialized GPD project and standalone.

State management is delegated to the `gpd-learning` MCP server. The workflow orchestrates agent spawning, user interaction, and file I/O for challenge/assessment/explanation markdown files.
</workflow_goal>

<step name="validate_context">
Run centralized command-context preflight first.

```bash
CONTEXT=$(gpd --raw validate command-context learn "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```

Parse the returned JSON.

- If `project_exists=true`, operate in project-context mode (use conventions, notation).
- If `project_exists=false`, operate in standalone mode.
- If the request is empty or too vague, ask one clarifying question about what concept to study.
</step>

<step name="parse_request">
Extract from `$ARGUMENTS`:

1. **Concept:** The physics topic (required). E.g., "Ward identity", "harmonic oscillator", "Berry phase".
2. **--type:** Challenge type — `recall`, `derive`, or `apply`. Default: `derive`.
3. **--review:** If set, use `get_review_queue` to show due concepts and exit.

If `--review` flag is set:

```
result = mcp__gpd-learning__get_review_queue(project_dir="{cwd}")
```

Display the review queue and exit. If the user picks a concept, start a review session for it.
</step>

<step name="start_session">
Initialize or resume a learning session via MCP:

```
session_result = mcp__gpd-learning__start_session(
  project_dir="{cwd}",
  concept="{concept}",
  challenge_type="{type}"
)
```

This handles:
- Legacy flat-file migration (automatic)
- Session init or resume
- Memory init or load (with v1→v2 schema migration)
- Prerequisite checking

From the result, extract:
- `slug` — concept slug for file paths
- `resumed` — whether this is a resumed session
- `session` — current session state (attempt_number, difficulty_level, current_type, etc.)
- `memory` — concept memory (last_mastery_level, active_gaps, etc.)
- `weak_prereqs` — list of weak prerequisites

If `weak_prereqs` is non-empty:
- Show top 1-2 weak prereqs
- Recommend bridge commands:
  - `/gpd:learn "{prereq concept}" --type recall`
  - `/gpd:explain "{prereq concept}"`
- Continue current concept unless user chooses the bridge path.

**Explanation-first offer for new concepts:**

If this is a fresh concept (`memory.last_mastery_level == null` and `resumed == false`):

> "This is a new concept. Would you like to:
> 1. **Start with a full explanation** — get the complete picture first, then challenge yourself
> 2. **Jump straight into the challenge** — learn by doing, gaps get explained as you go"

- If the user chooses (1):
  1. **Check cache first:** look for `.gpd/explanations/{slug}-EXPLAIN.md`. If it exists, display the cached explanation — no agent spawn needed.
  2. **If no cache:** spawn the `gpd-explainer` agent for a full, rigorous explanation (not gap-targeted — the full treatment). Write to `.gpd/explanations/{slug}-EXPLAIN.md` (same path as `/gpd:explain` so caching works both ways). **Skip the bibliographer** — learning context does not need citation verification.
  3. After the explanation is delivered (cached or fresh), continue into the challenge loop.
- If the user chooses (2): proceed directly to the challenge loop (current behavior).

If this is a resumed session or the user has prior mastery, skip this prompt — they already have context.

Set local variables from session state:
```
concept_dir = .gpd/learning/{slug}
challenge_file = {concept_dir}/CHALLENGE.md
attempt_number = session.attempt_number
difficulty_level = session.difficulty_level
type = session.current_type
```
</step>

<step name="gather_project_context">
If a GPD project exists, gather context relevant to the learning challenge:

```bash
INIT=$(gpd init progress --include project,state,config)
```

Extract:
- Project conventions and notation (metric signature, units, field normalizations)
- Current phase context (if any)
- Relevant local files mentioning the concept

```bash
rg -n -i --fixed-strings -- "{concept}" .gpd paper manuscript docs src 2>/dev/null | head -30
```

If no project context exists, proceed with no conventions — the challenge will use standard textbook notation.
</step>

<step name="learning_loop">
This is the mastery-bounded loop. It runs until mastery is achieved (Level 3+) or the user pauses.

### Step 5a: Spawn Tutor — Generate Challenge, Collect Attempt

Resolve tutor model:

```bash
TUTOR_MODEL=$(gpd resolve-model gpd-tutor)
```

> **Runtime delegation:** Spawn a subagent for the task below. Adapt the `task()` call to your runtime's agent spawning mechanism. If `model` resolves to `null` or an empty string, omit it so the runtime uses its default model. Always pass `readonly=false` for file-producing agents. If subagent spawning is unavailable, execute these steps sequentially in the main context.

First attempt prompt:

```markdown
<objective>
Generate a physics challenge and collect the user's attempt.
</objective>

<context>
- Concept: {concept}
- Challenge type: {type}
- Difficulty level (1-5): {difficulty_level}
- Challenge focus: multi-gap
- Attempt number: {attempt_number}
- Project conventions: {conventions or "none — use standard notation"}
- Challenge file: {challenge_file}
</context>

<requirements>
1. Design a {type} challenge for "{concept}" calibrated to 5-15 minutes.
2. Calibrate complexity to difficulty level {difficulty_level} on this scale:
   - 1: direct reconstruction from explicit premises
   - 2: one non-trivial inference step
   - 3: light variation/perturbation
   - 4: transfer to a changed assumption or boundary condition
   - 5: transfer + justification of assumption changes
3. Explicitly include `target_gaps=[]` for attempt 1.
4. Present it to the user and collect their attempt.
5. Write the challenge spec and attempt to {challenge_file}
6. Follow the hint policy if the user asks for help (3 escalating hints, never the answer).
7. If the user says "pause" or "stop", acknowledge and return.
</requirements>
```

Re-attempt prompt (attempt_number > 1):

```markdown
<objective>
Generate a refocused challenge targeting specific gaps and collect the user's attempt.
</objective>

<context>
- Concept: {concept}
- Challenge type: {type}
- Difficulty level (1-5): {difficulty_level}
- Challenge focus: {challenge_focus from policy, default "multi-gap"}
- Attempt number: {attempt_number}
- Prior mastery level: {previous_level}
- Prior gaps: {previous_gaps}
- Project conventions: {conventions or "none — use standard notation"}
- Challenge file: {challenge_file}
</context>

<requirements>
1. Design a {type} challenge for "{concept}" that specifically targets these gaps: {previous_gaps}
2. Include `target_gaps` explicitly and prioritize only the first gap when `challenge_focus=single-gap`.
3. Keep the same core concept but refocus to test the weak areas.
4. Calibrate complexity to difficulty level {difficulty_level} using the same 1-5 ladder.
5. Present it to the user and collect their attempt.
6. Append the new attempt to {challenge_file}
7. Follow the hint policy if the user asks for help.
8. If the user says "pause" or "stop", acknowledge and return.
</requirements>
```

```
task(
  prompt=filled_prompt,
  subagent_type="gpd-tutor",
  model="{tutor_model}",
  readonly=false,
  description="Challenge {slug} attempt {attempt_number}"
)
```

If tutor returns "paused" status → jump to `end_session` with status=paused.
If tutor returns "blocked" status → suggest `/gpd:explain "{concept}"` and exit.

### Step 5b: Spawn Assessor — Evaluate Attempt

Resolve assessor model:

```bash
ASSESSOR_MODEL=$(gpd resolve-model gpd-mastery-assessor)
```

> **Runtime delegation:** Spawn a subagent for the task below.

```markdown
<objective>
Assess the user's physics work for correctness, understanding, and mastery level.
</objective>

<context>
- Challenge file: {challenge_file}
- Attempt number: {attempt_number}
- Previous assessment: {previous_level and previous_gaps, or "first attempt"}
- Assessment output: {concept_dir}/ASSESSMENT-{attempt_number}.md
</context>

<requirements>
1. Read the challenge file — it contains the challenge spec and the user's attempt.
2. Independently derive the expected result before evaluating.
3. Assess correctness (dimensions, signs, factors, logic).
4. Assess understanding depth (WHY vs HOW — the Level 2/3 discriminator).
5. Assign mastery level 0-4 with justification.
6. Identify specific gaps with concrete descriptions.
7. Emit required machine-readable fields in both frontmatter and return block:
   - `MASTER_LEVEL` (0-4)
   - `LEVEL_NAME`
   - `EVIDENCE` (concise bullet list)
   - `GAPS`
   - `RECOMMENDED_NEXT_TYPE` (recall|derive|apply)
   - `RECOMMENDED_DIFFICULTY_DELTA` (-1|0|+1)
8. Write assessment to {concept_dir}/ASSESSMENT-{attempt_number}.md
</requirements>
```

```
task(
  prompt=filled_prompt,
  subagent_type="gpd-mastery-assessor",
  model="{assessor_model}",
  readonly=false,
  description="Assess {slug} attempt {attempt_number}"
)
```

Parse the assessor's return:
- `MASTER_LEVEL`
- `LEVEL_NAME`
- `GAPS`
- `RECOMMENDED_NEXT_TYPE`
- `RECOMMENDED_DIFFICULTY_DELTA`

### Step 5c: Update Session via MCP (Replaces manual state management)

Call the MCP server to record the assessment, apply adaptive policy, and update Bjork state:

```
update_result = mcp__gpd-learning__update_session(
  project_dir="{cwd}",
  slug="{slug}",
  mastery_level={MASTER_LEVEL},
  gaps={GAPS as list},
  misconceptions={misconceptions if any, else null},
  recommended_next_type="{RECOMMENDED_NEXT_TYPE}"
)
```

From the result, read the adaptive policy:
- `policy.action` — one of: mastered, improving, plateau, double_plateau, regression
- `policy.next_type` — challenge type for next attempt
- `policy.next_difficulty` — difficulty for next attempt
- `policy.challenge_focus` — "multi-gap" or "single-gap"
- `policy.message` — human-readable status message

Display the policy message to the user.

**If mastered:** Jump to `end_session` with status=mastered.

**Otherwise:** Update local variables from session state:
```
type = policy.next_type
difficulty_level = policy.next_difficulty
challenge_focus = policy.challenge_focus
attempt_number = update_result.session.attempt_number
previous_level = {MASTER_LEVEL}
previous_gaps = {GAPS}
```

Continue to Step 5d.

### Step 5d: Spawn Explainer — Teach Specific Gaps

Resolve explainer model:

```bash
EXPLAINER_MODEL=$(gpd resolve-model gpd-explainer)
```

> **Runtime delegation:** Spawn a subagent for the task below.

```markdown
<objective>
Explain the specific gaps identified in the user's physics work. This is targeted gap teaching, not a full concept explanation.
</objective>

<context>
- Concept: {concept}
- Gaps to address:
{numbered list of gaps from assessor}
- User's current understanding level: {mastery_level} ({mastery_name})
- Project conventions: {conventions or "none"}
</context>

<requirements>
1. Explain ONLY the specific gaps listed — not the entire concept.
2. For each gap, explain WHY it matters and HOW to think about it correctly.
3. Bridge intuition to formalism: give the physical picture AND the math.
4. Use the project's notation/conventions if available.
5. Keep it focused: 1-3 paragraphs per gap, not a textbook chapter.
6. Write the explanation to {concept_dir}/EXPLANATION-{attempt_number}.md
</requirements>

<output>
Write to: {concept_dir}/EXPLANATION-{attempt_number}.md

Structure:
- Frontmatter (concept, gaps_addressed, date)
- For each gap: physical meaning, formal statement, common confusion
- Summary: what to keep in mind for the next attempt
</output>
```

```
task(
  prompt=filled_prompt,
  subagent_type="gpd-explainer",
  model="{explainer_model}",
  readonly=false,
  description="Teach gaps for {slug}"
)
```

### Step 5e: Re-Attempt Prompt

After the explanation is delivered:

1. Present a summary of the gap explanation to the user
2. Ask: "Ready to try the challenge again, or want to pause and come back later?"
3. If user says yes/ready → loop back to Step 5a
4. If user says pause/stop → jump to `end_session` with status=paused

</step>

<step name="end_session">
Finalize the session via MCP. This handles FSRS card initialization on mastery,
learning log append, and session status update:

```
end_result = mcp__gpd-learning__end_session(
  project_dir="{cwd}",
  slug="{slug}",
  status="{status}",
  level_name="{LEVEL_NAME}",
  gaps_closed={list of gaps that were resolved}
)
```

If `status == "mastered"` and `end_result.fsrs_initialized == true`:
- Note that spaced repetition is now active
- Show `end_result.next_review` date for when to revisit
</step>

<step name="return_results">
Return to the user with a session summary.

**If mastered (Level 3+):**

```markdown
## LEARNING SESSION COMPLETE: {concept}

**Attempts:** {N}
**Mastery journey:** Level {start} → Level {final} ({LEVEL_NAME})
**Gaps closed:** {list}

You can now derive and explain {concept} from scratch. Feynman would approve.

**Spaced repetition active:** Next review scheduled for {next_review_date}.
**Review all due concepts:** /gpd:learn --review

**Next challenge:** /gpd:learn "{harder_related_concept}" --type apply
**Deepen further:** /gpd:learn "{concept}" --type apply (if current was derive)

**Session files:** .gpd/learning/{slug}/*
```

**If paused:**

```markdown
## LEARNING SESSION PAUSED: {concept}

**Attempts so far:** {N}
**Current level:** {mastery_level} ({LEVEL_NAME})
**Gaps remaining:** {list}

Progress saved. Resume anytime:
  /gpd:learn "{concept}"

Study before retrying:
  /gpd:explain "{specific_gap}"

**Session files:** .gpd/learning/{slug}/*
```

**If plateau:**

```markdown
## LEARNING SESSION — PLATEAU: {concept}

**Attempts:** {N}
**Level:** {mastery_level} ({LEVEL_NAME}) — no improvement in last {consecutive_plateau} attempts

Consider a different angle:
  /gpd:learn "{concept}" --type {different_type}

Or build prerequisites:
  /gpd:learn "{prerequisite_concept}"

**Session files:** .gpd/learning/{slug}/*
```
</step>
</content>
</invoke>