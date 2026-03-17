<workflow_goal>
Run a Feynman-style active recall loop: challenge → attempt → assess → teach gaps → re-attempt, iterating until the user achieves mastery (Level 3+) or pauses. Works both inside an initialized GPD project and standalone.
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
3. **--review:** If set, show prior session history and exit without starting a new loop.

Generate a slug from the concept for file naming:
- Lowercase, hyphens for spaces, strip special characters
- E.g., "Ward identity" → `ward-identity`
</step>

<step name="check_prior_sessions">
Check if prior learning sessions exist for this concept:

```bash
ls .gpd/learning/{slug}-ASSESSMENT-*.md 2>/dev/null
cat .gpd/learning/LEARNING-LOG.md 2>/dev/null | grep -A 8 "{concept}"
```

If prior sessions exist:
- Show the last mastery level achieved
- Show the number of previous attempts
- Show remaining gaps (if any)
- If `--review` flag was set, display this summary and exit

If no prior sessions:
- Note this is a fresh start
- Continue to challenge generation
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

Create the output directory:

```bash
mkdir -p .gpd/learning
```
</step>

<step name="learning_loop">
This is the mastery-bounded loop. It runs until mastery is achieved (Level 3+) or the user pauses.

Initialize loop state:

```
attempt_number = 1
previous_level = null
previous_gaps = []
consecutive_plateau = 0
```

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
- Attempt number: {attempt_number}
- Project conventions: {conventions or "none — use standard notation"}
- Challenge file: .gpd/learning/{slug}-CHALLENGE.md
</context>

<requirements>
1. Design a {type} challenge for "{concept}" calibrated to 5-15 minutes.
2. Present it to the user and collect their attempt.
3. Write the challenge spec and attempt to .gpd/learning/{slug}-CHALLENGE.md
4. Follow the hint policy if the user asks for help (3 escalating hints, never the answer).
5. If the user says "pause" or "stop", acknowledge and return.
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
- Attempt number: {attempt_number}
- Prior mastery level: {previous_level}
- Prior gaps: {previous_gaps}
- Project conventions: {conventions or "none — use standard notation"}
- Challenge file: .gpd/learning/{slug}-CHALLENGE.md
</context>

<requirements>
1. Design a {type} challenge for "{concept}" that specifically targets these gaps: {previous_gaps}
2. Keep the same core concept but refocus to test the weak areas.
3. Present it to the user and collect their attempt.
4. Append the new attempt to .gpd/learning/{slug}-CHALLENGE.md
5. Follow the hint policy if the user asks for help.
6. If the user says "pause" or "stop", acknowledge and return.
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

If tutor returns "paused" status → jump to `update_learning_log` with status=paused.
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
- Challenge file: .gpd/learning/{slug}-CHALLENGE.md
- Attempt number: {attempt_number}
- Previous assessment: {previous_level and previous_gaps, or "first attempt"}
- Assessment output: .gpd/learning/{slug}-ASSESSMENT-{attempt_number}.md
</context>

<requirements>
1. Read the challenge file — it contains the challenge spec and the user's attempt.
2. Independently derive the expected result before evaluating.
3. Assess correctness (dimensions, signs, factors, logic).
4. Assess understanding depth (WHY vs HOW — the Level 2/3 discriminator).
5. Assign mastery level 0-4 with justification.
6. Identify specific gaps with concrete descriptions.
7. Write assessment to .gpd/learning/{slug}-ASSESSMENT-{attempt_number}.md
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

Parse the assessor's return: `mastery_level`, `gaps`, `improved_since_last`.

### Step 5c: Mastery Check (Orchestrator Logic — No Agent Spawn)

Evaluate the assessment result:

**Mastery achieved (Level 3+):**
```
if mastery_level >= 3:
    → Display celebration message
    → Show assessment highlights
    → Jump to update_learning_log with status=mastered
```

**Improving but below mastery:**
```
if mastery_level > previous_level:
    consecutive_plateau = 0
    → "Improving! Level {previous_level} → {mastery_level}."
    → "Gap remaining: {primary_gap}. Let's close it."
    → Continue to Step 5d
```

**Plateau detected:**
```
if mastery_level == previous_level:
    consecutive_plateau += 1
    if consecutive_plateau >= 2:
        → "Plateau detected — same level for {consecutive_plateau} attempts."
        → "Options:"
        →   "1. Try a different challenge type (currently: {type})"
        →   "2. Pause and study first: /gpd:explain \"{concept}\""
        →   "3. Try once more"
        → Ask user which option (ask_user)
        → If option 1: change type, reset plateau counter, continue to 5a
        → If option 2: jump to update_learning_log with status=plateau
        → If option 3: continue to 5d
    else:
        → "Same level as last attempt. Let's try a different angle."
        → Continue to Step 5d
```

**Regression:**
```
if mastery_level < previous_level:
    → "Level dropped from {previous_level} to {mastery_level}."
    → "This sometimes happens — let's refocus."
    → Continue to Step 5d
```

**User pause:** At any point, if the user says "pause", jump to `update_learning_log` with status=paused.

Update loop state:
```
previous_level = mastery_level
previous_gaps = gaps
attempt_number += 1
```

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
6. Write the explanation to .gpd/learning/{slug}-EXPLANATION-{attempt_number}.md
</requirements>

<output>
Write to: .gpd/learning/{slug}-EXPLANATION-{attempt_number}.md

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
4. If user says pause/stop → jump to `update_learning_log` with status=paused

</step>

<step name="update_learning_log">
Append to `.gpd/learning/LEARNING-LOG.md`:

```markdown
## {date} — {concept}
- **Challenge type:** {type}
- **Attempts:** {attempt_number}
- **Final mastery level:** {mastery_level} ({mastery_name})
- **Journey:** Level {level_1} → {level_2} → ... → {final_level}
- **Gaps closed:** {list of gaps that were resolved across attempts}
- **Gaps remaining:** {list or "none"}
- **Status:** mastered | paused | plateau
- **Files:** {slug}-CHALLENGE.md, ASSESSMENT-1..{N}, EXPLANATION-1..{N}
```

If the file doesn't exist yet, create it with a header:

```markdown
# Learning Log

Feynman learning loop sessions. Each entry records a mastery journey.

---

```
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

**Next challenge:** /gpd:learn "{harder_related_concept}" --type apply
**Deepen further:** /gpd:learn "{concept}" --type apply (if current was derive)

**Session files:** .gpd/learning/{slug}-*
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

**Session files:** .gpd/learning/{slug}-*
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

**Session files:** .gpd/learning/{slug}-*
```
</step>
