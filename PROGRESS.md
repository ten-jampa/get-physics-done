# Progress Log

## Session: 2026-03-16 — Learning Engine v0: Active Recall + Mastery Assessment

### [2026-03-16 20:26 UTC] Implemented Learning Engine v0 — full Feynman learning loop
**Why**: GPD handles research workflows but has no mechanism for the user to actively learn physics. This adds a Feynman-style "what I cannot create, I do not understand" loop — challenge the user, assess their work for genuine understanding (not just correct steps), teach the specific gaps, and iterate until mastery. It's the first piece of turning GPD from a research tool into a research + learning tool.
**Status**: ✅ Complete
**Changes**:
- Created `src/gpd/agents/gpd-tutor.md` — challenge generator with 3-hint escalation, re-attempt gap focusing
- Created `src/gpd/agents/gpd-mastery-assessor.md` — mastery evaluator with 5-level scale (0-4), verification independence
- Created `src/gpd/commands/learn.md` — command entry point with `--type` and `--review` flags
- Created `src/gpd/specs/workflows/learn.md` — mastery-bounded loop (tutor → assessor → explainer → re-attempt)
- Modified `src/gpd/registry.py` — added 3 entries to `_SKILL_CATEGORY_MAP`
- Modified `src/gpd/core/config.py` — added MODEL_PROFILES and AGENT_DEFAULT_TIERS for both new agents
- Modified `src/gpd/specs/workflows/set-profile.md` — updated agent count 23 → 25
**Verification**: 125/125 tests pass (`test_cli_commands.py` + `test_metadata_consistency.py`), ruff lint clean
**Notes**: Agent count in set-profile.md needed updating — caught by `test_agent_count_matches_prompts_and_user_docs`

### [2026-03-16 21:45 UTC] Equation rendering iteration — settled on inline Unicode
**Why**: Raw LaTeX doesn't render in CLI terminals, and `utftex` 2D art breaks when passed through agent subprocesses. Needed a zero-friction equation display method for the learning engine.
**Status**: ✅ Complete
**Changes**:
- Modified `src/gpd/agents/gpd-tutor.md` — replaced utftex/LaTeX rendering with inline Unicode equation spec (ω₀, ½mẋ², etc.)
- Modified `src/gpd/agents/gpd-mastery-assessor.md` — same inline Unicode rendering rules
**Verification**: Rebuilt package, reinstalled locally (`25 agents, 62 commands`), ran first full learning loop — equations display correctly in terminal
**Notes**: Tested 3 approaches: raw LaTeX (unreadable), utftex (breaks in pipeline), inline Unicode (works). `utftex` is good standalone but whitespace alignment is destroyed through agent→orchestrator→user text pipeline. Inline Unicode is the pragmatic winner.

### [2026-03-16 21:45 UTC] First end-to-end learning loop test — classical harmonic oscillator
**Why**: Validate the full Feynman learning loop works: challenge → photo submission → transcription → assessment → gap teaching → full explanation → pause/resume.
**Status**: ✅ Complete
**Changes**:
- Created `.gpd/learning/classical-harmonic-oscillator-CHALLENGE.md` — challenge spec + transcribed handwritten attempt
- Created `.gpd/learning/classical-harmonic-oscillator-ASSESSMENT-1.md` — Level 2 MECHANICAL, 5 gaps identified
- Created `.gpd/learning/classical-harmonic-oscillator-EXPLANATION-1.md` — targeted gap teaching
- Created `.gpd/learning/classical-harmonic-oscillator-FULL-EXPLAIN.md` — comprehensive explanation (user-requested)
- Created `.gpd/learning/LEARNING-LOG.md` — session log with mastery journey
**Verification**: Full loop executed: tutor generated challenge → user submitted handwritten photo → transcribed and confirmed → assessor correctly identified Level 2 (correct math, missing physical reasoning) → explainer taught 5 specific gaps → full explanation produced on request → session paused and logged
**Notes**: UX issues surfaced: photo transcription is manual, argument passing dropped on 2/3 invocations, full explanation is a wall of text in terminal. These are v0.1 improvement targets.

## 2026-03-17 00:22:30 EDT
- Status: started
- Summary: Started README alignment for updated `gpd-learn` memory and prerequisite routing behavior.
- Context: The current README still describes only flat `.gpd/learning/` artifacts and omits the new per-concept folder + soft prerequisite guidance, which can confuse users after the recent learning-engine refactor.
- Details: Identified target section at `README.md` Learning Engine block and prepared edits for artifact paths, adaptive loop wording, and challenge type usage guidance.

## 2026-03-17 00:22:45 EDT
- Status: completed
- Summary: Updated Learning Engine README guidance to match current `gpd-learn` behavior and filesystem layout.
- Context: Users were seeing stale docs after the folder-based memory/prereq refactor; aligning README prevents mismatch between runtime behavior and onboarding instructions.
- Details: Edited `README.md` Learning Engine section to add soft prerequisite routing step, adaptive re-attempt wording, explicit challenge-type best-practice tips (`recall|derive|apply`), and new artifact layout under `.gpd/learning/{slug}/` including `MEMORY.json`; verified updates with `rg` at lines 431, 448, 454, 457, 460.
