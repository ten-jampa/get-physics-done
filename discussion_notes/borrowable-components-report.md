# Borrowable Components Report

What to take from existing systems, where it fits in our engine, and what outcomes justify the effort.

---

## 1. Bayesian Knowledge Tracing (from OATutor)

**What it is:** A 4-parameter probabilistic model that estimates whether a learner has mastered a skill after each attempt. 42 lines of code.

**How it works:**

After each attempt (correct/incorrect), BKT updates a mastery probability using four parameters per concept:

- P(L0) = initial mastery probability (default 0.1)
- P(T) = probability of learning on each attempt (default 0.1)
- P(G) = probability of guessing correctly without mastery (default 0.1)
- P(S) = probability of slipping (wrong despite mastery) (default 0.1)

The update: observe correct/incorrect → compute posterior mastery → add transition probability. When P(mastery) > 0.95, the concept graduates.

**Where it fits in our engine:**

Right now our mastery assessment is qualitative (Level 0-4 assigned by the assessor agent). BKT would add a **quantitative mastery signal** that accumulates across attempts and sessions.

Integration point: after each assessment, map the mastery level to a correct/incorrect signal per sub-concept, then run BKT update on each. Store in `MEMORY.json` alongside the existing `last_mastery_level`.

**What we'd need to adapt:**

- OATutor's parameters are all 0.1 (untuned placeholders). We'd need physics-specific priors — e.g., P(G) should be lower for derivation challenges (you can't guess a derivation) and higher for recall.
- Their skill model is flat (problem → skills). Physics needs prerequisite chains. Combine with our existing `concept-prereqs.json`.
- No forgetting model — mastery stays at 0.95 forever. Pair with FSRS-6 (below) for decay.

**Expected outcome:** Smoother mastery tracking that doesn't swing wildly between attempts. The assessor's Level 0-4 judgment remains primary, but BKT provides a running probability that informs difficulty calibration and prerequisite routing.

**Effort:** ~1-2 days. The algorithm is 42 lines. The work is in defining the physics knowledge component taxonomy (which concepts map to which sub-skills).

**Justification:** Without BKT, our engine treats each attempt independently. With it, we get cumulative evidence — 3 attempts at Level 2 followed by 1 at Level 3 is different from jumping straight to Level 3. BKT captures this.

---

## 2. FSRS-6 Forgetting Curve (from Vestige / open-spaced-repetition)

**What it is:** A 21-parameter model for scheduling reviews based on memory decay. Tells you WHEN a concept needs to be revisited.

**How it works:**

FSRS-6 models memory with two key quantities:

- **Stability (S):** How long until the memory decays to 90% retrievability. Increases with successful reviews.
- **Difficulty (D):** How hard the item is to learn. Affects stability growth rate.

The forgetting curve is power-law:

```
R(t, S) = (1 + factor * t/S)^(-0.154)
```

After each review, stability updates based on whether you remembered (stability grows) or forgot (stability resets to a lower value). The scheduler picks the next review date by solving for when R drops below your target retention (default 90%).

**Where it fits in our engine:**

Our engine currently has no concept of "when should you come back and review this?" A user masters the harmonic oscillator today — when should the system prompt them to revisit it?

Integration point: after mastery is achieved (Level 3+), initialize an FSRS-6 card for that concept. On `--review` flag or at session start, check which concepts are due for review based on their stability decay. The `MEMORY.json` already has `last_mastery_level` and `updated_at` — add FSRS state (stability, difficulty, next_review_date).

**What we'd need to adapt:**

- FSRS-6 uses a 4-grade rating (Again/Hard/Good/Easy). Map from our 5-level mastery: Level 0-1 = Again, Level 2 = Hard, Level 3 = Good, Level 4 = Easy.
- The `py-fsrs` package exists on PyPI — no need to reimplement or depend on Vestige's Rust binary.
- Vestige is AGPL-3.0 and 22MB of Rust. Don't import it. Just use the algorithm via `py-fsrs`.

**Expected outcome:** The learning engine becomes a long-term system, not just single sessions. Concepts resurface at scientifically optimal intervals. Users who master the harmonic oscillator get prompted to review it 3 days later, then 10 days, then 30 days — reinforcing the neural pathways.

**Effort:** ~1 day. `py-fsrs` handles the math. The work is wiring it into `MEMORY.json` and adding a "due for review" check at session start.

**Justification:** Without spaced repetition, mastery is ephemeral. The user demonstrates Level 3 today and forgets in a month. FSRS-6 is the state-of-the-art scheduling algorithm (used by Anki's FSRS optimizer, backed by millions of reviews of empirical data). Adding it transforms the engine from "study tool" to "long-term knowledge maintenance system."

---

## 3. Stepwise Feedback Pedagogy (from aiPlato)

**What it is:** A system that evaluates student derivations line-by-line, identifying where conceptual errors occur without revealing the answer.

**How it works (as much as is disclosed):**

The aiPlato paper (arXiv 2601.09965) describes outcomes, not architecture. What we know:

- Students write equations line-by-line in a workspace
- System parses each line, extracts equations into an "Equation Board"
- Feedback identifies which specific lines contain errors and what kind (conceptual vs. computational)
- Awards partial credit for correct intermediate reasoning
- Credits steps that are "not explicitly shown but inferable"
- Never reveals the answer — maintains "productive struggle"

The paper reports a 0.81 effect size on final exams (n=87, quasi-experimental, no true control group, self-selection acknowledged).

**Where it fits in our engine:**

Our assessor currently evaluates the whole attempt as a unit and assigns a single mastery level. Stepwise feedback would let us pinpoint WHICH step the understanding breaks down at.

Integration point: enhance the `gpd-mastery-assessor` prompt to produce per-step evaluation, not just an overall level. The assessor already does independent re-derivation — the enhancement is to align its derivation step-by-step with the user's and flag divergence points.

**What we'd need to adapt:**

- aiPlato's implementation is proprietary — we can't borrow code, only the pedagogical approach
- Our assessor works on full derivations (not line-by-line input). The per-step evaluation would be extracted from the assessor's comparison of its derivation vs the user's.
- The "productive struggle" principle should inform the explainer: teach the GAP, not the ANSWER. We already do this but should make it more explicit.

**Expected outcome:** More actionable gap identification. Instead of "you didn't explain why the measure is invariant" (current), the feedback becomes "Step 3 is correct mechanically, but Step 4 jumps from gauge transformation to Ward identity without explaining WHY the path integral measure is invariant — that's where your understanding breaks."

**Effort:** ~1 day. It's a prompt engineering change to the assessor, not new infrastructure. Add a `## Step-by-Step Analysis` section to the assessment output.

**Justification:** The 0.81 effect size (even with caveats) suggests stepwise feedback is significantly more effective than holistic feedback. Our current "5 gaps" output is already better than most systems, but localizing gaps to specific derivation steps makes the feedback immediately actionable.

---

## 4. Dual-Strength Memory Model (from Vestige / Bjork & Bjork 1992)

**What it is:** A two-track model separating storage strength (how well encoded) from retrieval strength (how accessible right now).

**How it works:**

- **Storage strength** (1.0–10.0): How deeply the concept is encoded. Never decays. Increases +0.1 on successful recall, +0.3 on a lapse (desirable difficulty effect — struggling strengthens encoding).
- **Retrieval strength** (0.0–1.0): How accessible the concept is right now. Decays over time via FSRS power-law. Resets to 1.0 on any recall attempt.
- **Retention score** = retrieval × 0.7 + (storage/10) × 0.3

The key insight: a concept can have high storage strength (deeply learned) but low retrieval strength (currently hard to access). This is the "tip of the tongue" phenomenon. Review brings retrieval back up cheaply because storage is still high.

**Where it fits in our engine:**

Currently `MEMORY.json` stores `last_mastery_level` — a single number. Dual-strength would give us a richer picture: "this user deeply understands Lagrangian mechanics (storage=8.2) but hasn't used it in 2 months (retrieval=0.3)."

Integration point: add `storage_strength` and `retrieval_strength` to `MEMORY.json`. Update on each assessment. Use for prerequisite routing — a concept with high storage but low retrieval needs a quick review, not a full re-learn.

**Expected outcome:** Smarter prerequisite routing. When the user starts learning Ward identities, the system checks: "Lagrangian mechanics: storage=8.2, retrieval=0.3 → quick recall challenge sufficient" vs "Lagrangian mechanics: storage=1.5, retrieval=0.1 → needs full re-learn."

**Effort:** ~0.5 days. Simple formula, just needs wiring into the existing memory model.

**Justification:** Without this, we treat "never learned" and "learned but forgotten" the same way. They require very different interventions. This is a small addition with outsized routing impact.

---

## Implementation Priority

| Component | Effort | Impact | Priority |
|-----------|--------|--------|----------|
| FSRS-6 review scheduling | 1 day | High — enables long-term retention | **1st** |
| Dual-strength memory model | 0.5 day | Medium — improves prerequisite routing | **2nd** |
| Stepwise feedback in assessor | 1 day | High — more actionable gaps | **3rd** |
| BKT mastery tracking | 1-2 days | Medium — smoother mastery signal | **4th** |

**Recommended order:** FSRS-6 first because it's the biggest gap in our current engine (no review scheduling at all). Dual-strength pairs naturally with it. Stepwise feedback improves the core loop quality. BKT is useful but lower priority because our 5-level assessor already provides a strong mastery signal.

**Total effort:** ~4-5 days for all four. Each is independently valuable — no dependency chain.

---

## What NOT to Borrow

- **Vestige as a whole** — AGPL-3.0 license, 22MB Rust binary, designed for agent memory not pedagogy. Take the algorithm, not the system.
- **OATutor's content model** — Pre-authored problems with static skill tagging. We generate challenges dynamically; their content infrastructure doesn't apply.
- **aiPlato's architecture** — Proprietary, undisclosed. We can only borrow the pedagogical principles, not the implementation.
- **Khanmigo's approach** — Hint-based Socratic questioning is a different paradigm from our challenge-first active recall. Not complementary.
