# TODO

## Session: gpd-learn mastery + adaptive implementation

- [x] Create feature branch `feat/learn-mastery-adaptive-v1`
- [x] Update learn workflow contract with deterministic adaptive policy
- [x] Add session-state artifact contract (`.gpd/learning/{slug}-SESSION.json`)
- [x] Extend assessor machine-readable output contract
- [x] Extend tutor challenge calibration contract (difficulty + target gaps)
- [x] Align `gpd:learn` command success criteria
- [x] Add CLI tests for `validate command-context learn` explicit-input behavior
- [x] Run targeted tests and lint checks

## Review

- Targeted tests: `uv run pytest tests/test_cli_commands.py -k "command_context_learn" -v` (passed)
- Lint: `uv run ruff check tests/test_cli_commands.py` (passed)
- Full prompt-wiring suite has pre-existing repo graph inventory mismatches unrelated to this change:
  - `test_repo_graph_prompt_scope_counts_match_repo_inventory`
  - `test_repo_graph_same_stem_command_inventory_matches_repo`
