# Lessons

## 2026-03-16

- `validate command-context` explicit-input guidance for project-aware commands is derived from `argument-hint`; tests should assert the exact surfaced string for stability.
- For `gpd-learn`, adaptive behavior needs machine-readable assessor fields, not only prose, to avoid orchestration ambiguity.
- Prompt-wiring full-suite failures can be unrelated to feature work; keep a targeted test gate for scoped changes and document pre-existing failures explicitly.
- Learning artifact paths should be concept-folder scoped (`.gpd/learning/{slug}/...`) to prevent filename sprawl and simplify per-concept archival.
- Legacy path migration should be move-in-place and idempotent to avoid duplicate artifacts and repeated migration churn.
- Prerequisite routing is better as a soft gate in early versions: suggest bridge work, but preserve user momentum by not hard-blocking progress.
