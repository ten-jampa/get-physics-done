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
find ".gpd/learning/{slug}" -maxdepth 1 -name "ASSESSMENT-*.md" 2>/dev/null
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

Ensure prerequisite graph exists (empty object is valid):

```bash
if [ ! -f .gpd/learning/concept-prereqs.json ]; then
  cat > .gpd/learning/concept-prereqs.json <<'EOF'
{}
EOF
fi
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
difficulty_level = 2
score_history = []
gap_history = []
concept_dir = .gpd/learning/{slug}
session_file = {concept_dir}/SESSION.json
memory_file = {concept_dir}/MEMORY.json
challenge_file = {concept_dir}/CHALLENGE.md
prereq_graph_file = .gpd/learning/concept-prereqs.json
```

Create concept directory and migrate legacy flat files once (move in place):

```bash
mkdir -p "{concept_dir}"
for suffix in SESSION.json CHALLENGE.md; do
  legacy=".gpd/learning/{slug}-${suffix}"
  target="{concept_dir}/${suffix}"
  if [ -f "$legacy" ] && [ ! -f "$target" ]; then
    mv "$legacy" "$target"
  fi
done
for legacy in .gpd/learning/{slug}-ASSESSMENT-*.md .gpd/learning/{slug}-EXPLANATION-*.md; do
  if [ -f "$legacy" ]; then
    base="$(basename "$legacy")"
    new_name="$(printf "%s" "$base" | sed "s/^${slug}-//")"
    target="{concept_dir}/${new_name}"
    if [ ! -f "$target" ]; then
      mv "$legacy" "$target"
    fi
  fi
done
```

Initialize or load `{concept_dir}/SESSION.json` so re-attempt routing is deterministic across pauses:

```json
{
  "concept": "{concept}",
  "current_type": "{type}",
  "difficulty_level": 2,
  "attempt_number": 1,
  "score_history": [],
  "gap_history": [],
  "plateau_count": 0,
  "status": "active"
}
```

Initialize or load `{concept_dir}/MEMORY.json`:

```json
{
  "concept": "{concept}",
  "slug": "{slug}",
  "last_mastery_level": null,
  "last_type": "{type}",
  "last_difficulty": 2,
  "active_gaps": [],
  "misconceptions": [],
  "updated_at": "{ISO timestamp}"
}
```

Soft prerequisite routing before challenge generation:

1. Read `{prereq_graph_file}` and collect prereq slugs for `{slug}` (empty list if absent).
2. For each prereq slug, check `.gpd/learning/{prereq_slug}/MEMORY.json`.
3. Mark prereq weak if memory file missing OR `last_mastery_level < 2`.
4. If weak prereqs exist:
   - Show top 1-2 weak prereqs
   - Recommend bridge commands:
     - `/gpd:learn "{prereq human name}" --type recall`
     - `/gpd:explain "{prereq human name}"`
   - Continue current concept unless user chooses the bridge path.

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
- Challenge focus: {single-gap if regression else multi-gap}
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
- `IMPROVED_SINCE_LAST`

### Step 5c: Mastery Check (Orchestrator Logic — No Agent Spawn)

Evaluate the assessment result:

**Mastery achieved (Level 3+):**
```
if mastery_level >= 3:
    → Display celebration message
    → Show assessment highlights
    → session.status = "mastered"
    → Jump to update_learning_log with status=mastered
```

**Improving but below mastery:**
```
if mastery_level > previous_level:
    consecutive_plateau = 0
    difficulty_level = min(5, difficulty_level + 1)
    if recommended_next_type is valid and recommended_next_type != type:
        type = recommended_next_type
    → "Improving! Level {previous_level} → {mastery_level}."
    → "Gap remaining: {primary_gap}. Increasing difficulty to {difficulty_level}."
    → Continue to Step 5d
```

**Single plateau (same level once):**
```
if mastery_level == previous_level:
    consecutive_plateau += 1
    if consecutive_plateau == 1:
        → "Same level as last attempt. Keep difficulty at {difficulty_level}, refocus on primary gap."
        → Continue to Step 5d
```

**Repeated plateau (same level at least twice):**
```
if mastery_level == previous_level and consecutive_plateau >= 2:
    difficulty_level = max(1, difficulty_level - 1)
    if type == "derive":
        type = "apply"
    elif type == "apply":
        type = "derive"
    elif type == "recall":
        type = "derive"
    consecutive_plateau = 0
    → "Plateau detected — switching challenge type to {type} and reducing difficulty to {difficulty_level}."
    → Continue to Step 5d
```

**Regression:**
```
if mastery_level < previous_level:
    difficulty_level = max(1, difficulty_level - 1)
    challenge_focus = "single-gap"
    if recommended_next_type is valid and recommended_next_type != type:
        type = recommended_next_type
    → "Level dropped from {previous_level} to {mastery_level}."
    → "Reducing difficulty to {difficulty_level} and isolating one gap."
    → Continue to Step 5d
```

**User pause:** At any point, if the user says "pause", jump to `update_learning_log` with status=paused.

Update loop state:
```
previous_level = mastery_level
previous_gaps = gaps
score_history.append(mastery_level)
gap_history.append(gaps)
attempt_number += 1
write session_file:
  current_type = type
  difficulty_level = difficulty_level
  attempt_number = attempt_number
  score_history = score_history
  gap_history = gap_history
  plateau_count = consecutive_plateau
  status = "active"
write memory_file:
  concept = concept
  slug = slug
  last_mastery_level = mastery_level
  last_type = type
  last_difficulty = difficulty_level
  active_gaps = gaps
  misconceptions = conceptual_misconceptions_from_assessment_if_any
  updated_at = now_iso
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
- **Difficulty journey:** {difficulty_1} → ... → {difficulty_N}
- **Files:** {slug}/SESSION.json, {slug}/MEMORY.json, {slug}/CHALLENGE.md, {slug}/ASSESSMENT-1..{N}.md, {slug}/EXPLANATION-1..{N}.md
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
