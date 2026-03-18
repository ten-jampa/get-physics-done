# LLM Reliability: Research Copilot vs. Learning Engine

A comparative analysis of how GPD handles the fundamental tension between LLM-generated content and reliability across its two major subsystems.

---

## The Shared Tension

Both the research copilot and the learning engine depend on LLM agents for their core value proposition. The research copilot uses LLMs to perform physics derivations, survey literature, synthesize results, and verify correctness. The learning engine uses LLMs to generate calibrated challenges, assess human understanding, and explain gaps. In both cases, the system's output quality is bounded by the reliability of LLM-generated content.

This is not a bug — it is an architectural necessity. You cannot do novel physics derivations algorithmically, and you cannot assess whether a human truly understands Ward identities without semantic judgment. The question is not whether to delegate to LLMs, but what guardrails constrain that delegation.

---

## Research Copilot: Verification Architecture

### Multi-Agent Separation of Concerns

The research copilot implements extensive role separation across its agent pool. No single agent both produces and validates research output:

| Agent | Role | Independence |
|-------|------|-------------|
| `gpd-executor` | Performs derivations, writes code, produces artifacts | Writable, production role |
| `gpd-verifier` | Verifies phase goal achievement against artifacts | Read-only, independent of executor context |
| `gpd-consistency-checker` | Cross-phase convention and notation consistency | Read-only, cross-phase scope |
| `gpd-plan-checker` | Validates plans will achieve phase goals before execution | Pre-execution gate |
| `gpd-referee` | Skeptical journal-style review of manuscripts | Anti-sycophancy protocol with recommendation floors |
| `gpd-debugger` | Investigates errors and inconsistencies | Hypothesis-testing methodology |
| `gpd-bibliographer` | Citation management with hallucination detection | 5-step verification pipeline for references |
| `gpd-review-math` | Mathematical soundness review (peer review panel) | Must list unchecked areas explicitly |
| `gpd-review-physics` | Physical soundness review (peer review panel) | Catches "formal resemblance != physical evidence" |
| `gpd-research-synthesizer` | Reconciles outputs from parallel researchers | Contradiction resolution with confidence weighting |

This is structurally analogous to the learning engine's tutor/assessor separation, but broader — the research side has 10+ specialized agents with non-overlapping verification responsibilities.

### The Verification Check Registry

The research copilot has a formal, machine-facing verification registry (`gpd.core.verification_checks`) defining 19 universal checks organized into four tiers:

**Tier 1 (Mandatory floor):**
- 5.1: Dimensional analysis
- 5.2: Numerical spot-check
- 5.3: Limiting cases

**Tier 2 (Standard):**
- 5.4: Conservation laws
- 5.5: Numerical convergence
- 5.6: Literature cross-check
- 5.7: Order-of-magnitude estimation
- 5.8: Physical plausibility

**Tier 3 (Domain-specific):**
- 5.9: Ward identities / sum rules
- 5.10: Unitarity bounds
- 5.11: Causality constraints
- 5.12: Positivity constraints

**Tier 4 (Advanced):**
- 5.13: Kramers-Kronig consistency
- 5.14: Statistical validation

**Contract-aware checks (5.15-5.19):**
- Asymptotic/limit recovery, benchmark reproduction, direct-vs-proxy consistency, fit-family mismatch, estimator-family mismatch

Each check has a defined `evidence_kind` (computational, structural, or hybrid), an `oracle_hint` for the verifying agent, and a `catches` field describing what class of error it detects.

### The Verification MCP Server

The `gpd-verification` MCP server exposes these checks as deterministic tools. Critically, it provides:

1. **Dimensional analysis parsing** — a regex-based dimension parser (`_parse_dimensions`) that tracks `[M]`, `[L]`, `[T]`, `[Q]`, `[Theta]` through expressions and compares them term-by-term. This is one of the few places where verification is genuinely algorithmic rather than LLM-delegated.

2. **Domain checklists** — 15 physics-domain-specific checklists (QFT, condensed matter, stat mech, GR/cosmology, AMO, nuclear/particle, quantum info, fluid/plasma, mathematical physics, astrophysics, soft matter, algebraic QFT, string field theory, classical mechanics) mapping domain knowledge to verification check IDs.

3. **Contract-aware checks** — checks that bind to research contract terms (observables, claims, deliverables, acceptance tests, references) and verify that contracted commitments are actually met.

4. **Artifact scanning** — keyword-based heuristics that flag common issues (e.g., quantum context without hbar, dimensionful arguments to exponentials, missing limiting case analysis).

### The LLM Physics Error Catalog

The `gpd-verifier` agent encodes a 12-class error catalog of known LLM failure modes in physics:

1. Wrong Clebsch-Gordan coefficients
2. N-particle symmetrization errors
3. Confusing Green's function types (retarded/advanced/Feynman/Matsubara)
4. Wrong group theory for non-SU(2) groups
5. Incorrect asymptotic expansions
6. Delta function mishandling
7. Wrong phase conventions
8. Confusing intensive/extensive quantities
9. Incorrect thermal field theory (Matsubara vs. real-time)
10. Wrong tensor decompositions in GR
11. Hallucinating mathematical identities
12. Incorrect Grassmann algebra signs

Each class includes detection strategies and examples. This is a direct acknowledgment that LLMs make systematic, predictable errors in physics — and the verification architecture is designed around catching them.

### Self-Critique Checkpoints in Execution

The `gpd-executor` agent implements inline self-critique at each derivation step:

- **Sign check**: "Did I flip a sign? Check by substituting test values."
- **Factor check**: "Missing 2pi, hbar, or normalization constant?"
- **Convention check**: "Am I consistent with the project's metric signature, Fourier convention, etc.?"
- **Dimension check**: "Do dimensions match on both sides?"

Additionally, the executor tags identity claims with `IDENTITY_CLAIM` markers so the verifier can specifically target error class #11 (hallucinated identities).

### Cross-Phase Consistency Verification

The `gpd-consistency-checker` implements a "Pre-Populated Cross-Convention Interaction Table" mapping which conventions interact with which (e.g., metric signature affects Dirac algebra, Fourier convention affects Green's functions). Its core principle: "Correctness != Consistency, and Pattern-Matching != Understanding."

### Workflow-Level Verification

Several workflows encode verification as a structural requirement:

- **`verify-work`**: Creates `VERIFICATION.md` tracking verification progress. Minimum floor: dimensional analysis + limiting case + numerical spot-check with code execution. Philosophy: "Show expected physics AND computational evidence, ask if reality matches."

- **`derive-equation`**: Every derivation step must be verifiable. Uses `ASSERT_CONVENTION` comments to lock conventions at each step.

- **`verify-phase`**: Goal-backward verification (did the phase achieve its goal?) with the fundamental rule that "every verification check must involve COMPUTATION, not just text search."

- **`execute-phase`**: Wave-based parallel execution with computation-type-aware adaptation (derivation, numerical, literature, paper-writing, formalism, analysis, validation — each with different verification requirements).

### Research Discovery Guardrails

The `discover` workflow implements a source hierarchy: mandatory authoritative sources (textbooks, review articles) BEFORE general search. Three depth levels (Quick Verify, Standard, Deep Dive) calibrate research effort to need.

### Bibliographic Hallucination Detection

The `gpd-bibliographer` has a 5-step verification pipeline for citations, a retracted paper handling protocol, and explicit hallucination detection. This directly addresses one of the most common LLM failure modes — fabricating references.

### Anti-Sycophancy in the Referee

The `gpd-referee` agent implements an anti-sycophancy protocol with recommendation floors. It evaluates across 10 dimensions (novelty, correctness, clarity, completeness, significance, reproducibility, literature context, presentation quality, technical soundness, publishability) and is explicitly instructed to find holes in arguments rather than validate them.

---

## Learning Engine: Verification Architecture

### Agent Separation

The learning engine uses a clean three-agent separation:

| Agent | Role | Independence |
|-------|------|-------------|
| `gpd-tutor` | Generates calibrated physics challenges | Never reveals the answer; 3 escalating hints only |
| `gpd-mastery-assessor` | Evaluates human-submitted work | Independent re-derivation; "Verify by Computation, Not Pattern Matching" |
| `gpd-explainer` | Teaches specific identified gaps | Activated only when gaps are found |

The tutor generates challenges, the human attempts them, and the assessor evaluates — the assessor never sees the tutor's solution, only the human's work and its own independent re-derivation.

### Mastery Assessment

The assessor implements five mastery levels (0-4: Incomplete, Recall, Mechanical, Understanding, Fluency) with specific discriminators at each level. The critical boundary is Level 2 to 3: correct computation vs. genuine understanding. The assessor must independently re-derive the result and compare, not pattern-match against an expected answer.

### Deterministic State Management

The learning engine has the most developed deterministic infrastructure in the system:

- **FSRS-6 spaced repetition** — evidence-based scheduling algorithm with stability, difficulty, and interval tracking. Pure math, no LLM involvement.
- **Bjork dual-strength memory** — storage strength (how deeply encoded, never decays) and retrieval strength (how accessible now, decays exponentially). The retention formula (`0.6 * mastery_fraction + 0.4 * retrieval`) is deterministic.
- **Prerequisite graph** — directed acyclic graph with cycle detection, topological sort, and weak-prerequisite checking. All deterministic.
- **Adaptive policy** — mastery level changes trigger deterministic routing decisions (mastered/improving/plateau/double_plateau/regression) that control challenge type and difficulty.
- **Learning MCP server** — 12 tools for session management, memory tracking, review scheduling, and prerequisite graphs. All state transitions are deterministic; the LLM provides mastery assessments, not state management.

This is the cleanest example of the "delegate semantic judgment to LLMs, keep state management deterministic" pattern in the codebase.

### What the Learning Engine Delegates to LLMs

1. **Challenge generation** — the tutor decides what to ask and how to calibrate difficulty
2. **Mastery assessment** — the assessor judges whether the human's work demonstrates understanding
3. **Gap identification** — the assessor identifies specific conceptual gaps
4. **Gap explanation** — the explainer teaches the identified gaps

These are all semantic judgments that cannot be made algorithmically. The learning engine correctly identifies them as LLM-appropriate and wraps them in deterministic state management.

---

## Comparative Analysis

### Where the Research Copilot Has Stronger Guardrails

1. **Broader multi-agent verification** — 10+ specialized verification agents vs. the learning engine's 3. The research side has dedicated agents for mathematical soundness, physical soundness, cross-phase consistency, bibliographic verification, and adversarial review.

2. **Formal verification registry** — 19 typed checks with tiers, evidence kinds, and error-class-to-check mappings. The learning engine has no analogous formal check taxonomy.

3. **Domain-specific checklists** — 15 physics-domain checklists with specific checks (e.g., "Ward identities after vertex corrections" for QFT, "Tr(rho)=1, eigenvalues in [0,1]" for quantum info). The learning engine assesses understanding domain-agnostically.

4. **LLM error catalog** — 12 documented error classes with detection strategies. The learning engine does not have a catalog of known LLM assessment failure modes.

5. **Contract-aware verification** — checks bound to research contract terms (observables, deliverables, acceptance tests). The learning engine's "contract" is the mastery level, which is simpler but less structured.

6. **Self-critique checkpoints** — the executor performs inline sign/factor/convention/dimension checks during derivation. No analogous self-monitoring in the tutor or assessor.

7. **Anti-sycophancy protocols** — the referee has explicit anti-sycophancy measures. The assessor has "Verify by Computation, Not Pattern Matching" but no structural anti-sycophancy protocol.

### Where the Learning Engine Has Stronger Guardrails

1. **Deterministic state management** — FSRS-6, Bjork dual-strength memory, prerequisite graphs, and adaptive policy are all pure computation. The research copilot's state management (`STATE.md`, `state.json`) is more complex but less algorithmically rigorous.

2. **Clean separation of concerns** — the learning MCP server (12 tools, all deterministic) is completely separated from research state. Learning state never pollutes research state and vice versa.

3. **Bounded assessment loop** — the mastery-bounded loop has clear termination criteria (Level 3+) and deterministic escalation. Research verification can be open-ended.

4. **Human in the loop by design** — the learning engine evaluates human-produced work, not LLM-produced work. The human's derivation is ground truth for their understanding; the assessor's job is to evaluate it, not to produce the physics.

### Where Both Are Equally Vulnerable

1. **Semantic judgment quality** — both sides ultimately depend on an LLM making correct judgments about physics. The verifier judging whether a derivation is correct and the assessor judging whether a human's work demonstrates understanding are both semantic tasks delegated to LLMs. Neither can be made deterministic.

2. **Hallucination risk in generation** — the executor can hallucinate derivation steps, and the tutor can generate challenges with incorrect physics. Both rely on downstream verification to catch errors, but that verification is also LLM-based.

3. **Calibration of difficulty** — the tutor calibrates challenge difficulty using LLM judgment, and the researcher calibrates research depth using LLM judgment (explore/balanced/exploit/adaptive modes). Both are semantic calibration tasks without deterministic anchors.

---

## Gaps in Research-Side Reliability

### Gap 1: No Symbolic Computation Integration

The verification server's dimensional analysis uses regex-based parsing, which is a step toward deterministic verification — but the system does not integrate with symbolic computation engines (SymPy, Mathematica, SageMath). The `verify-phase` workflow states that "every verification check must involve COMPUTATION, not just text search," but the actual computation is performed by the LLM, not by a CAS.

**What's missing:** A symbolic verification tool that can independently evaluate expressions, check dimensional consistency algebraically, verify limiting cases symbolically, and spot-check numerical values. This would provide a non-LLM verification channel for mathematical claims.

### Gap 2: No Independent Re-Derivation by a Second LLM

The verifier operates independently of the executor's context, but it is still a single LLM call. The learning engine's assessor independently re-derives results, but again, it is one LLM evaluating another LLM's work (or a human's work). Neither side implements true multi-model verification where two different LLMs independently derive a result and their outputs are compared.

**What's missing:** A verification mode where a second, independent LLM (potentially a different model) re-derives key results from scratch and the outputs are compared programmatically. Disagreements would flag the result for human review.

### Gap 3: No Confidence Scoring or Uncertainty Quantification

Neither the research nor learning side produces calibrated confidence scores for LLM-generated content. The verifier produces pass/fail verdicts, not probabilities. The assessor produces mastery levels (0-4), not confidence intervals.

**What's missing:** A mechanism for LLM agents to express calibrated uncertainty about their outputs. "I am 95% confident this derivation is correct" is more useful than "PASS" if the system can track calibration over time. The research contract system's acceptance tests are binary; they could be extended with confidence bounds.

### Gap 4: Executor Self-Critique Is Advisory, Not Enforced

The executor's self-critique checkpoints (sign check, factor check, convention check, dimension check) are prompt instructions, not enforced gates. The executor can skip them without structural consequences. Compare with the verifier, which has a formal check registry with tiers — but even the verifier's checks are LLM-evaluated, not machine-enforced.

**What's missing:** Mandatory machine-checkable gates at each derivation step. For example: after each step, the system could automatically run dimensional analysis via the verification MCP server and block progress if dimensions are inconsistent.

### Gap 5: Research Synthesis Trusts LLM Reconciliation

The `gpd-research-synthesizer` reconciles outputs from parallel researcher agents, resolving notation conflicts and contradictions with "confidence weighting." But the confidence weights themselves are LLM-assigned, and the reconciliation is LLM-performed. If two researchers produce conflicting results, the synthesizer's resolution is a semantic judgment, not a computation.

**What's missing:** Deterministic conflict detection. When two researcher outputs contain the same quantity with different values, the system should flag this automatically (string/expression matching) rather than relying on the synthesizer to notice.

### Gap 6: No Regression Testing for Verification

The research side has a `/gpd:regression-check` command, but there is no automated regression test suite that re-runs verification checks after changes. If a phase is modified, previously-verified results could silently become invalid.

**What's missing:** A deterministic regression harness that stores verification check inputs and expected outputs, then automatically re-runs them when artifacts change.

---

## Does the "Delegate Semantic Judgment, Keep State Deterministic" Pattern Apply to Both Sides?

**Yes, but with different maturity levels.**

The learning engine is the cleanest implementation of this pattern. Semantic judgments (challenge generation, mastery assessment, gap identification) are delegated to LLMs, while state management (FSRS-6 scheduling, Bjork memory, prerequisite graphs, adaptive policy, session tracking) is entirely deterministic. The boundary between "what the LLM decides" and "what the system computes" is sharp and well-defined.

The research copilot implements the same pattern in principle — the verification check registry, domain checklists, and contract system define what must be checked, while the verifier agent performs the actual checks. But the boundary is blurrier:

- The verification check registry is deterministic, but the checks themselves are LLM-evaluated.
- The research contract system defines acceptance tests deterministically, but evaluating whether they pass is a semantic judgment.
- The state management (`STATE.md`, `state.json`) mixes structured data with free-text summaries.
- The consistency checker has a deterministic convention interaction table, but detecting convention violations is semantic.

The research side has more "semantic judgment surface area" because research verification is inherently harder to mechanize than learning state management. You can deterministically schedule spaced repetition reviews, but you cannot deterministically verify that a QFT derivation is correct.

---

## The Fundamental Tension Is System-Wide

The `tldr-report.md` discussion note observes that "GPD is a research copilot, not a learning platform. All five areas the user asks about have partial analogues, but every mechanism is oriented toward AI-quality research output, not human cognitive development."

This observation extends to reliability: the fundamental tension — that LLM-generated content must be verified by LLM-based verification, creating a circular dependency — is a system-wide characteristic, not unique to either subsystem.

Both sides mitigate this tension through the same strategies:
1. **Role separation** — the agent that produces content never verifies its own output
2. **Specification of what to check** — formal registries (verification checks) or formal criteria (mastery levels) constrain what the verifier evaluates
3. **Deterministic anchoring** — wherever possible, LLM outputs are anchored to deterministic computations (dimensional analysis, numerical spot-checks, FSRS scheduling)
4. **Human involvement** — the research copilot keeps the human researcher in the loop for decisions, and the learning engine evaluates human-produced work

The research side has more verification surface area because research outputs are more complex (multi-phase derivations, cross-convention consistency, publication-quality manuscripts). The learning side has a cleaner separation because its state management is simpler and more naturally mechanizable.

---

## Proposed Improvements

### For the Research Copilot

1. **Integrate a symbolic computation engine** — expose SymPy or SageMath as an MCP tool. Let the verification server evaluate expressions symbolically rather than delegating all mathematical verification to LLMs. This would make dimensional analysis, limiting case checks, and numerical spot-checks genuinely deterministic.

2. **Implement dual-model verification** — for high-stakes derivations (e.g., central results of a paper), run the same derivation through two different LLMs and compare outputs programmatically. Flag disagreements for human review.

3. **Add confidence scoring to verification checks** — extend the verification check schema with a `confidence` field (0.0-1.0) that the verifier must provide. Track calibration over time: if a verifier reports 95% confidence but 20% of its "PASS" results turn out wrong, the system should flag the calibration gap.

4. **Enforce self-critique checkpoints mechanically** — after each executor step, automatically run the dimensional analysis tool from the verification MCP server. Block execution if dimensions are inconsistent. This converts an advisory check into a hard gate.

5. **Add deterministic conflict detection to the synthesizer** — when multiple researchers produce outputs, automatically extract and compare numerical values, expressions, and convention choices. Flag conflicts before the synthesizer attempts reconciliation.

6. **Build a verification regression harness** — store verification check inputs and outputs. When artifacts change, automatically re-run relevant checks. This ensures previously-verified results remain valid.

### For the Learning Engine

7. **Add an LLM assessment error catalog** — analogous to the research side's 12-class physics error catalog, document known failure modes of LLM-based mastery assessment (e.g., rewarding confident but wrong explanations, failing to distinguish memorized derivations from understood ones, over-crediting correct final answers with flawed reasoning).

8. **Implement assessor self-consistency checks** — if the same human work is assessed multiple times (e.g., by replaying the assessment), the results should be consistent. Track assessor reliability over time.

9. **Add challenge validation** — before presenting a tutor-generated challenge to the human, run the challenge through a verification check (can it be solved? is the stated answer correct? are the prerequisites accurate?). This catches tutor hallucinations before they reach the learner.

### Cross-Cutting

10. **Unify the verification philosophy documentation** — the research side's `verification-independence.md` reference articulates the principle "Verification by Re-Derivation vs. Verification by Pattern Matching" clearly. This principle applies equally to the learning engine's assessor. A shared verification philosophy document would make the architectural intent explicit across both subsystems.

11. **Track LLM reliability metrics** — both subsystems would benefit from tracking how often LLM judgments are overridden by humans, how often verification catches genuine errors vs. false positives, and how calibrated confidence scores are. This data would inform which checks are actually providing value and where the system is weakest.

---

## Summary

The research copilot has a sophisticated, multi-layered verification architecture with 19 formal checks, 12 documented LLM error classes, 15 domain-specific checklists, and 10+ specialized agents. The learning engine has a cleaner deterministic state management system with FSRS-6, Bjork memory, and prerequisite graphs.

Both sides correctly identify semantic judgment as the irreducible LLM-delegated component and build deterministic infrastructure around it. The research side has more verification breadth; the learning side has sharper separation between semantic and deterministic layers.

The most impactful improvements would be: (1) integrating symbolic computation to provide a non-LLM verification channel for the research side, (2) adding challenge validation to catch tutor errors on the learning side, and (3) building shared reliability tracking infrastructure that measures how well the verification architecture actually works in practice.

The fundamental tension — that LLM-generated content is verified by LLM-based verification — is irreducible for a physics research copilot. The system cannot verify novel physics derivations without semantic understanding. The architecture's response to this tension — role separation, formal check registries, deterministic anchoring, and human involvement — is sound. The gaps are in enforcement (advisory vs. mandatory checks), independence (single-model vs. multi-model verification), and measurement (no calibration tracking).
