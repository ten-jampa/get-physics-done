# TODO

## Session: gpd-learn concept memory + prerequisite routing

- [x] Create feature branch `feat/learn-concept-memory-prereqs`
- [x] Migrate learn workflow path contract to concept directories (`.gpd/learning/{slug}/...`)
- [x] Add automatic move-in-place migration from legacy flat files
- [x] Add concept memory contract (`MEMORY.json`) and update policy
- [x] Add prerequisite graph contract (`concept-prereqs.json`) and soft-gate routing logic
- [x] Align `gpd:learn` success criteria with new session/memory paths
- [x] Align `gpd-tutor` and `gpd-mastery-assessor` output file paths
- [x] Add prompt-wiring regression test for learn memory/prereq contracts
- [x] Run targeted tests and lint checks

## Review

- Prompt contract test: `uv run pytest tests/core/test_prompt_wiring.py -k "learn_workflow_uses_concept_directory_memory_and_prereq_soft_gate" -v` (passed)
- CLI context tests: `uv run pytest tests/test_cli_commands.py -k "command_context_learn" -v` (passed)
- Lint: `uv run ruff check tests/core/test_prompt_wiring.py tests/test_cli_commands.py` (passed)
- Full prompt-wiring suite still has pre-existing repo graph inventory mismatches unrelated to this branch:
  - `test_repo_graph_prompt_scope_counts_match_repo_inventory`
  - `test_repo_graph_same_stem_command_inventory_matches_repo`
