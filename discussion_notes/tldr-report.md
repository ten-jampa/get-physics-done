# TLDR: Fork GPD vs Build From Scratch

**Short answer:** Fork GPD, but expect significant architectural changes.

## What Works Out-of-the-Box

- **Agent system** - Drop-in new learning agents (`gpd-tutor.md`, `gpd-mastery-assessor.md`) [1](#8-0) 
- **Wave-based DAG** - Perfect for concept prerequisites via `depends_on` [2](#8-1) 
- **Protocol bundles** - Add learning-specific bundles (spaced-repetition, cognitive-load) [3](#8-2) 
- **gpd-explainer** - Already bridges intuition-to-formalism [4](#8-3) 

## What Needs Major Surgery

- **State schema** - `ResearchState` is physics-specific; needs `LearnerState` model [5](#8-4) 
- **Status machine** - Hardcoded research states ("Planning", "Executing") → learning states ("introduced", "practicing", "mastered") [6](#8-5) 
- **Research contracts** - `extra="forbid"` physics enums → learning objectives, mastery criteria [7](#8-6) 
- **Convention locks** - 18 physics fields → learning domains (classical mechanics, QM, etc.) [8](#8-7) 

## Recommendation

**Fork GPD** - The orchestration engine, agent spawning, and wave-based execution are solid foundations. Plan to rewrite:
1. State management (30% effort)
2. Contract system (20% effort) 
3. Assessment agents (new, but reuse patterns)
4. Learning-specific protocol bundles

The alternative is building from scratch, which means recreating the sophisticated agent orchestration, state management, and verification systems that GPD already has.

## Notes

GPD's `adaptive` research mode [9](#8-8)  and verification independence [10](#8-9)  are directly applicable to learning systems - these architectural patterns are worth preserving.

Wiki pages you might want to explore:
- [Execute Stage (psi-oss/get-physics-done)](/wiki/psi-oss/get-physics-done#3.3)

### Citations

**File:** src/gpd/specs/references/verification/meta/verification-independence.md (L50-68)
```markdown
## Verification by Re-Derivation vs. Verification by Pattern Matching

There are two fundamentally different approaches to verification. GPD requires the first and forbids the second.

### Verification by Re-Derivation (REQUIRED)

The verifier independently computes or re-derives the result (or aspects of it) and compares with the artifact. This catches errors regardless of how convincing the presentation is.

**What it looks like:**

1. Read the final expression from the artifact
2. Substitute specific test parameter values and evaluate
3. Compare the result with an independently known answer
4. Take limits of the expression and compare with known limiting forms
5. Trace physical dimensions through each term and verify consistency
6. Cross-check by an alternative computational method

**Why it works:** A sign error, a missing factor of 2pi, or a wrong index contraction will produce a wrong numerical answer at a test point, a wrong limit, or an inconsistent dimension -- regardless of how the executor described their work. The computation does not lie.

```

