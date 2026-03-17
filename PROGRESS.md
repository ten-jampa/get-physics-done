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

## Session: 2026-03-17 — gpd-learning MCP Server + FSRS-6 + Dual-Strength Memory

### [2026-03-17 16:25 UTC] Competitive landscape research + borrowable components report
**Why**: Needed to know if the learning engine duplicates existing work, and what we can borrow from other systems to avoid reinventing the wheel.
**Status**: ✅ Complete
**Changes**:
- Created `discussion_notes/borrowable-components-report.md` — evaluates OATutor BKT, FSRS-6, aiPlato stepwise feedback, Bjork dual-strength memory
- Committed and pushed to `origin/main` (`ca3236b`)
**Verification**: Report covers 4 systems with technical details, effort estimates, and integration points. No existing system combines challenge-first active recall + independent verification + physics conventions + CLI-native.
**Notes**: Package name is `fsrs` (not `py-fsrs`), v6.3.1, pure Python. OATutor BKT is 42 lines of JS. Vestige is AGPL — take the algorithm, not the system.

### [2026-03-17 16:25 UTC] Planned gpd-learning MCP server (8th server)
**Why**: Learning state management and spaced repetition scheduling need to be testable, runtime-accessible, and cleanly separated from research state.
**Status**: 🔄 In Progress
**Changes**:
- Plan written to `.claude/plans/elegant-waddling-reddy.md`
- 3 new files: `core/learning.py`, `mcp/servers/learning_server.py`, `tests/mcp/test_learning_server.py`
- 6 files to modify: errors.py, pyproject.toml, builtin_servers.py, __init__.py, learn.md workflow, learn.md command
- 12 MCP tools across 4 groups: session management, memory queries, spaced repetition, prerequisite graph
**Verification**: Plan reviewed against existing MCP server patterns (state_server.py, patterns_server.py). FSRS package verified on PyPI.
**Notes**: Key architectural decision: learning state stays in `.gpd/learning/`, never touches ResearchState. Lazy schema migration v1→v2 on read.

### [2026-03-17 17:00 UTC] Implemented gpd-learning MCP server — 12 tools, 45 tests
**Why**: Learning state (sessions, memory, FSRS scheduling, Bjork dual-strength, prereq graph) was managed by raw file I/O in the workflow markdown — untestable, not portable across runtimes, no long-term retention system.
**Status**: ✅ Complete
**Changes**:
- Created `src/gpd/core/learning.py` (~400 lines) — Pydantic models, I/O, FSRS-6, Bjork memory, adaptive policy, topo sort
- Created `src/gpd/mcp/servers/learning_server.py` (~300 lines) — 12 MCP tools (session, memory, review, graph)
- Created `tests/mcp/test_learning_server.py` (~500 lines) — 45 tests covering all tool groups
- Modified `src/gpd/core/errors.py` — added `LearningError(GPDError)`
- Modified `pyproject.toml` — added `fsrs>=6.0.0` dep + `gpd-mcp-learning` entry point
- Modified `src/gpd/mcp/builtin_servers.py` — registered gpd-learning in `_BUILTIN_SERVERS` + `_PUBLIC_DESCRIPTOR_METADATA`
- Modified `src/gpd/mcp/servers/__init__.py` — updated docstring to 8 servers
- Modified `src/gpd/specs/workflows/learn.md` — refactored to use MCP tools for state management
- Modified `src/gpd/commands/learn.md` — added 12 gpd-learning tools to allowed-tools
- Modified `tests/test_metadata_consistency.py` — server count 7→8
- Generated `infra/gpd-learning.json` — public descriptor
**Verification**: 45/45 learning tests pass, 19/19 metadata tests pass, 108/108 CLI tests pass, 30/30 parity tests pass, ruff lint clean, `uv build` succeeds, `npx -y get-physics-done --claude --local --reinstall` → 25 agents, 62 commands
**Notes**: fsrs 6.3.1 API returns (card, log) tuple not a named result. MCP server needed manual pip install into ~/.gpd/venv since npx --local fetched from PyPI instead of local wheel.

### [2026-03-17 17:20 UTC] End-to-end manual test — unitary time evolution learning loop
**Why**: Validate the full MCP-backed learning loop works: start_session → tutor → assessor → update_session → explainer → pause → resume
**Status**: ✅ Complete
**Changes**:
- Created `.gpd/learning/unitary-time-evolution/` — SESSION.json, MEMORY.json, CHALLENGE.md, ASSESSMENT-1.md, EXPLANATION-1.md
- Created `.gpd/explanations/unitary-time-evolution-EXPLAIN.md` — full concept explanation via /gpd:explain
**Verification**: Session started fresh (resumed=false), handwritten photo transcribed, assessor returned Level 2 MECHANICAL with 5 gaps, adaptive policy applied (improving, first attempt), Bjork state updated (storage 1.0→1.3), session paused and resumed correctly, MEMORY.json has schema_version=2 with bjork fields, fsrs=null (correct — mastery not yet reached)
**Notes**: User confirmed the MCP tools load correctly after session restart. Explanation-first offer works for new concepts but not triggered on resume (correct behavior).

### [2026-03-17 17:39 UTC] Added explanation-first offer + caching + skip bibliographer for learning
**Why**: User pain points — (1) spawning explainer takes ~4 min, so repeat explanations should be cached; (2) bibliographer adds latency with no value for learning contexts; (3) new concepts should offer explanation before challenge.
**Status**: ✅ Complete
**Changes**:
- Modified `src/gpd/specs/workflows/learn.md` — explanation-first prompt for new concepts, checks cache at `.gpd/explanations/{slug}-EXPLAIN.md`, skips bibliographer
- Modified `src/gpd/specs/workflows/explain.md` — added `check_cache` step (use existing file or regenerate), added `from_learning` context detection, skip bibliographer when `from_learning=true`
**Verification**: Workflow specs updated, caching paths consistent between learn and explain (both use `.gpd/explanations/{slug}-EXPLAIN.md`)
**Notes**: Three optimizations: (1) cache check before agent spawn = instant second time, (2) bibliographer skipped for learning = saves ~1-2 min, (3) cross-workflow cache sharing = /gpd:explain then /gpd:learn (or vice versa) reuses the same file.

### [2026-03-17 17:45 UTC] Committed all changes in 4 logical commits
**Why**: Clean git history for eventual PR — each commit is a self-contained conceptual unit.
**Status**: ✅ Complete
**Changes**:
- `7619395` — Core learning engine (models, FSRS-6, Bjork, adaptive policy, graph, LearningError, fsrs dep)
- `03e89a2` — MCP server (12 tools, registration, infra descriptor, 45 tests)
- `5efad0d` — Workflow refactor (learn.md + command use MCP tools, explanation-first offer)
- `093960d` — Caching + UX (explanation cache, bibliographer skip for learning)
**Verification**: `git log --oneline -4` shows 4 clean commits on `feat/gpd-learning-mcp-server` branch

### [2026-03-17 18:00 UTC] Verified explanation caching works end-to-end
**Why**: Caching is the key UX improvement — second explanation request should be instant, not another 4-min agent spawn.
**Status**: ✅ Complete
**Changes**: No code changes — verification only
**Verification**: `/gpd:explain "unitary time evolution"` (2nd time) → detected cached file, displayed instantly with no agent spawn. `/gpd:explain "Attractors"` (new concept) → correctly detected no cache, spawned explainer, wrote to `.gpd/explanations/attractors-dynamical-systems-EXPLAIN.md`. Subsequent request would be cached.
**Notes**: Caching works across both `/gpd:explain` and `/gpd:learn` explanation-first path since they share the same file location.

### [2026-03-17 18:12 UTC] Session review — before/after comparison of learning engine v0 → v1
**Why**: Assess the impact of the MCP server implementation against the original workflow-only approach.
**Status**: ✅ Complete
**Changes**: No code changes — analysis only
**Verification**: Key improvements confirmed in practice: (1) MCP calls ~100ms vs manual file I/O in workflow, (2) 45 automated tests vs 0, (3) Bjork state tracking active (storage_strength updated after assessment), (4) FSRS card ready to initialize on mastery, (5) schema migration v1→v2 working on-read, (6) explanation caching eliminates repeat 4-min agent spawns
**Notes**: Remaining gaps: agent spawn latency still 10-100s (inherent), FSRS review loop not yet tested e2e (need Level 3 mastery), `npx --local` install flow has rough edges (manual pip install needed).
