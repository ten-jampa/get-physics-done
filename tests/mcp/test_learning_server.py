"""Tests for the gpd-learning MCP server (core/learning.py + servers/learning_server.py).

Tests call MCP tool functions directly with tmp_path fixtures (same pattern as test_servers.py).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_learning_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".gpd" / "learning"
    d.mkdir(parents=True)
    return d


def _write_memory(tmp_path: Path, slug: str, data: dict) -> None:
    concept_dir = tmp_path / ".gpd" / "learning" / slug
    concept_dir.mkdir(parents=True, exist_ok=True)
    (concept_dir / "MEMORY.json").write_text(json.dumps(data))


def _write_session(tmp_path: Path, slug: str, data: dict) -> None:
    concept_dir = tmp_path / ".gpd" / "learning" / slug
    concept_dir.mkdir(parents=True, exist_ok=True)
    (concept_dir / "SESSION.json").write_text(json.dumps(data))


def _write_prereqs(tmp_path: Path, graph: dict) -> None:
    d = tmp_path / ".gpd" / "learning"
    d.mkdir(parents=True, exist_ok=True)
    (d / "concept-prereqs.json").write_text(json.dumps(graph))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ===========================================================================
# Session tests
# ===========================================================================


class TestStartSession:
    def test_fresh_start(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session

        _make_learning_dir(tmp_path)
        result = start_session(str(tmp_path), "harmonic oscillator")

        assert "error" not in result
        assert result["slug"] == "harmonic-oscillator"
        assert result["resumed"] is False
        assert result["session"]["status"] == "active"
        assert result["session"]["attempt_number"] == 1
        assert result["memory"]["concept"] == "harmonic oscillator"
        assert result["memory"]["schema_version"] == 2
        assert result["memory"]["bjork"]["storage_strength"] == 1.0
        assert result["weak_prereqs"] == []

    def test_resume_existing(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session

        _make_learning_dir(tmp_path)
        _write_session(tmp_path, "ward-identity", {
            "concept": "Ward identity",
            "slug": "ward-identity",
            "current_type": "derive",
            "difficulty_level": 3,
            "attempt_number": 2,
            "score_history": [1],
            "gap_history": [["sign error"]],
            "plateau_count": 0,
            "status": "active",
        })
        _write_memory(tmp_path, "ward-identity", {
            "concept": "Ward identity",
            "slug": "ward-identity",
            "last_mastery_level": 1,
            "last_type": "derive",
            "last_difficulty": 3,
            "active_gaps": ["sign error"],
            "misconceptions": [],
            "updated_at": "2026-03-16T00:00:00Z",
        })

        result = start_session(str(tmp_path), "Ward identity")
        assert result["resumed"] is True
        assert result["session"]["attempt_number"] == 2
        assert result["memory"]["last_mastery_level"] == 1

    def test_legacy_migration(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session

        ld = _make_learning_dir(tmp_path)
        # Create legacy flat files
        (ld / "berry-phase-SESSION.json").write_text(json.dumps({
            "concept": "Berry phase",
            "slug": "berry-phase",
            "current_type": "recall",
            "difficulty_level": 2,
            "attempt_number": 1,
            "score_history": [],
            "gap_history": [],
            "plateau_count": 0,
            "status": "active",
        }))

        result = start_session(str(tmp_path), "Berry phase")
        assert result["resumed"] is True
        # Legacy file should have been migrated
        assert (ld / "berry-phase" / "SESSION.json").exists()
        assert not (ld / "berry-phase-SESSION.json").exists()

    def test_weak_prereqs(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session

        _make_learning_dir(tmp_path)
        _write_prereqs(tmp_path, {"ward-identity": ["noether-theorem"]})
        # noether-theorem has no memory → weak prereq

        result = start_session(str(tmp_path), "Ward identity")
        assert len(result["weak_prereqs"]) == 1
        assert result["weak_prereqs"][0]["slug"] == "noether-theorem"


class TestUpdateSession:
    def test_improvement(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "harmonic oscillator")

        result = update_session(
            str(tmp_path),
            slug="harmonic-oscillator",
            mastery_level=2,
            gaps=["boundary conditions"],
        )
        assert "error" not in result
        assert result["policy"]["action"] == "improving"
        assert result["session"]["score_history"] == [2]
        assert result["session"]["attempt_number"] == 2

    def test_mastery(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "simple pendulum")
        # Simulate reaching level 3
        result = update_session(
            str(tmp_path),
            slug="simple-pendulum",
            mastery_level=3,
            gaps=[],
        )
        assert result["policy"]["action"] == "mastered"
        assert result["session"]["status"] == "mastered"

    def test_plateau(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "berry phase")

        # First assessment: level 1
        update_session(str(tmp_path), slug="berry-phase", mastery_level=1, gaps=["sign"])
        # Second assessment: still level 1 → single plateau
        result = update_session(str(tmp_path), slug="berry-phase", mastery_level=1, gaps=["sign"])
        assert result["policy"]["action"] == "plateau"

    def test_double_plateau(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "berry phase")

        # 1st assessment: level 1 (first attempt, previous=None → improving, plateau_count=0)
        update_session(str(tmp_path), slug="berry-phase", mastery_level=1, gaps=["g1"])
        # 2nd: same level → plateau, plateau_count becomes 1
        update_session(str(tmp_path), slug="berry-phase", mastery_level=1, gaps=["g1"])
        # 3rd: same level, plateau_count=1 → plateau, plateau_count becomes 2
        update_session(str(tmp_path), slug="berry-phase", mastery_level=1, gaps=["g1"])
        # 4th: same level, plateau_count=2 → double_plateau
        result = update_session(str(tmp_path), slug="berry-phase", mastery_level=1, gaps=["g1"])
        assert result["policy"]["action"] == "double_plateau"
        assert result["policy"]["next_type"] == "apply"  # switched from derive

    def test_regression(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "path integral")

        # Level 2 first
        update_session(str(tmp_path), slug="path-integral", mastery_level=2, gaps=[])
        # Then regress to level 1
        result = update_session(str(tmp_path), slug="path-integral", mastery_level=1, gaps=["measure"])
        assert result["policy"]["action"] == "regression"
        assert result["policy"]["challenge_focus"] == "single-gap"

    def test_no_session_error(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import update_session

        _make_learning_dir(tmp_path)
        result = update_session(str(tmp_path), slug="nonexistent", mastery_level=1, gaps=[])
        assert "error" in result


class TestEndSession:
    def test_mastered_inits_fsrs(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import end_session, start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "oscillator")
        update_session(str(tmp_path), slug="oscillator", mastery_level=3, gaps=[])

        result = end_session(str(tmp_path), slug="oscillator", status="mastered", level_name="Proficient")
        assert "error" not in result
        assert result["fsrs_initialized"] is True
        assert result["next_review"] is not None
        assert result["status"] == "mastered"

        # Verify MEMORY.json has fsrs field
        mem_data = _read_json(tmp_path / ".gpd" / "learning" / "oscillator" / "MEMORY.json")
        assert mem_data["fsrs"] is not None
        assert mem_data["fsrs"]["stability"] is not None

    def test_paused_no_fsrs(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import end_session, start_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "oscillator")

        result = end_session(str(tmp_path), slug="oscillator", status="paused")
        assert result["status"] == "paused"
        assert "fsrs_initialized" not in result

    def test_learning_log_created(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import end_session, start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "oscillator")
        update_session(str(tmp_path), slug="oscillator", mastery_level=2, gaps=["damping"])
        end_session(str(tmp_path), slug="oscillator", status="paused")

        log_path = tmp_path / ".gpd" / "learning" / "LEARNING-LOG.md"
        assert log_path.exists()
        content = log_path.read_text()
        assert "oscillator" in content
        assert "paused" in content


# ===========================================================================
# Memory tests
# ===========================================================================


class TestGetMemory:
    def test_exists(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import get_memory

        _make_learning_dir(tmp_path)
        _write_memory(tmp_path, "harmonic-oscillator", {
            "schema_version": 2,
            "concept": "harmonic oscillator",
            "slug": "harmonic-oscillator",
            "last_mastery_level": 3,
            "last_type": "derive",
            "last_difficulty": 3,
            "active_gaps": [],
            "misconceptions": [],
            "updated_at": "2026-03-16T20:00:00Z",
            "fsrs": None,
            "bjork": {"storage_strength": 2.0, "retrieval_strength": 0.9, "last_recall_at": None},
        })

        result = get_memory(str(tmp_path), "harmonic-oscillator")
        assert "error" not in result
        assert result["concept"] == "harmonic oscillator"
        assert result["last_mastery_level"] == 3
        assert "retention" in result

    def test_not_found(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import get_memory

        _make_learning_dir(tmp_path)
        result = get_memory(str(tmp_path), "nonexistent")
        assert "error" in result

    def test_v1_migration(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import get_memory

        _make_learning_dir(tmp_path)
        # V1 memory (no schema_version, no fsrs, no bjork)
        _write_memory(tmp_path, "noether", {
            "concept": "Noether theorem",
            "slug": "noether",
            "last_mastery_level": 2,
            "last_type": "recall",
            "last_difficulty": 2,
            "active_gaps": ["continuous symmetries"],
            "misconceptions": [],
            "updated_at": "2026-03-15T00:00:00Z",
        })

        result = get_memory(str(tmp_path), "noether")
        assert "error" not in result
        assert result["schema_version"] == 2
        assert result["fsrs"] is None
        assert result["bjork"]["storage_strength"] == 1.0


class TestListConcepts:
    def test_multiple_concepts(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import list_concepts_tool

        _make_learning_dir(tmp_path)
        _write_memory(tmp_path, "concept-a", {
            "concept": "Concept A", "slug": "concept-a",
            "last_mastery_level": 3, "last_type": "derive", "last_difficulty": 3,
            "active_gaps": [], "misconceptions": [], "updated_at": "2026-03-16T00:00:00Z",
        })
        _write_memory(tmp_path, "concept-b", {
            "concept": "Concept B", "slug": "concept-b",
            "last_mastery_level": 1, "last_type": "recall", "last_difficulty": 2,
            "active_gaps": ["gap1"], "misconceptions": [], "updated_at": "2026-03-16T00:00:00Z",
        })

        result = list_concepts_tool(str(tmp_path))
        assert result["count"] == 2
        # Weakest first
        assert result["concepts"][0]["slug"] == "concept-b"
        assert result["concepts"][1]["slug"] == "concept-a"

    def test_empty(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import list_concepts_tool

        _make_learning_dir(tmp_path)
        result = list_concepts_tool(str(tmp_path))
        assert result["count"] == 0


# ===========================================================================
# FSRS tests
# ===========================================================================


class TestFSRS:
    def test_card_init_on_mastery(self, tmp_path: Path) -> None:
        from gpd.core.learning import init_fsrs_card

        now = datetime(2026, 3, 17, tzinfo=UTC)
        state = init_fsrs_card(now)
        assert state.stability is not None
        assert state.difficulty is not None
        assert state.reps == 2  # Two Good reviews to graduate from Learning → Review
        assert state.lapses == 0
        assert state.state == 2  # Review state (graduated from Learning)
        assert state.next_review is not None
        # Next review should be days away, not minutes
        next_dt = datetime.fromisoformat(state.next_review)
        hours_until = (next_dt - now).total_seconds() / 3600
        assert hours_until > 12, f"Expected days-scale interval, got {hours_until:.1f} hours"

    def test_no_card_below_mastery(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import end_session, start_session, update_session

        _make_learning_dir(tmp_path)
        start_session(str(tmp_path), "test concept")
        update_session(str(tmp_path), slug="test-concept", mastery_level=2, gaps=["gap"])

        result = end_session(str(tmp_path), slug="test-concept", status="paused")
        assert "fsrs_initialized" not in result

        mem = _read_json(tmp_path / ".gpd" / "learning" / "test-concept" / "MEMORY.json")
        assert mem["fsrs"] is None

    def test_review_updates(self, tmp_path: Path) -> None:
        from gpd.core.learning import init_fsrs_card, record_fsrs_review

        now = datetime(2026, 3, 17, tzinfo=UTC)
        state = init_fsrs_card(now)
        # Good review
        later = now + timedelta(days=2)
        updated = record_fsrs_review(state, rating=3, now=later)
        assert updated.reps == state.reps + 1
        assert updated.lapses == 0
        assert updated.last_review is not None

        # Again review (lapse)
        even_later = later + timedelta(days=1)
        lapsed = record_fsrs_review(updated, rating=1, now=even_later)
        assert lapsed.lapses == 1

    def test_queue_ordering(self, tmp_path: Path) -> None:
        from gpd.core.learning import get_due_concepts

        _make_learning_dir(tmp_path)
        now = datetime(2026, 3, 20, tzinfo=UTC)

        # Concept A: due 2 days ago
        _write_memory(tmp_path, "concept-a", {
            "schema_version": 2, "concept": "A", "slug": "concept-a",
            "last_mastery_level": 3, "last_type": "derive", "last_difficulty": 3,
            "active_gaps": [], "misconceptions": [], "updated_at": "2026-03-16T00:00:00Z",
            "fsrs": {
                "state": 2, "stability": 5.0, "difficulty": 4.0, "step": None,
                "reps": 3, "lapses": 0,
                "last_review": "2026-03-15T00:00:00+00:00",
                "next_review": "2026-03-18T00:00:00+00:00",
                "elapsed_days": 0, "scheduled_days": 3,
            },
            "bjork": {"storage_strength": 2.0, "retrieval_strength": 0.8, "last_recall_at": "2026-03-15T00:00:00+00:00"},
        })
        # Concept B: due 5 days ago (more overdue)
        _write_memory(tmp_path, "concept-b", {
            "schema_version": 2, "concept": "B", "slug": "concept-b",
            "last_mastery_level": 3, "last_type": "derive", "last_difficulty": 3,
            "active_gaps": [], "misconceptions": [], "updated_at": "2026-03-10T00:00:00Z",
            "fsrs": {
                "state": 2, "stability": 3.0, "difficulty": 5.0, "step": None,
                "reps": 2, "lapses": 1,
                "last_review": "2026-03-10T00:00:00+00:00",
                "next_review": "2026-03-15T00:00:00+00:00",
                "elapsed_days": 0, "scheduled_days": 5,
            },
            "bjork": {"storage_strength": 1.5, "retrieval_strength": 0.6, "last_recall_at": "2026-03-10T00:00:00+00:00"},
        })
        # Concept C: not due yet
        _write_memory(tmp_path, "concept-c", {
            "schema_version": 2, "concept": "C", "slug": "concept-c",
            "last_mastery_level": 4, "last_type": "apply", "last_difficulty": 4,
            "active_gaps": [], "misconceptions": [], "updated_at": "2026-03-19T00:00:00Z",
            "fsrs": {
                "state": 2, "stability": 10.0, "difficulty": 2.0, "step": None,
                "reps": 5, "lapses": 0,
                "last_review": "2026-03-19T00:00:00+00:00",
                "next_review": "2026-03-30T00:00:00+00:00",
                "elapsed_days": 0, "scheduled_days": 11,
            },
            "bjork": {"storage_strength": 5.0, "retrieval_strength": 1.0, "last_recall_at": "2026-03-19T00:00:00+00:00"},
        })

        due = get_due_concepts(tmp_path, now)
        assert len(due) == 2  # C is not due
        # Most overdue first
        assert due[0]["slug"] == "concept-b"  # 5 days overdue
        assert due[1]["slug"] == "concept-a"  # 2 days overdue


# ===========================================================================
# Bjork tests
# ===========================================================================


class TestBjork:
    def test_decay_formula(self) -> None:
        from gpd.core.learning import BjorkState, compute_retrieval_decay

        bjork = BjorkState(
            storage_strength=2.0,
            retrieval_strength=1.0,
            last_recall_at="2026-03-15T00:00:00+00:00",
        )
        now = datetime(2026, 3, 17, tzinfo=UTC)  # 2 days later
        r = compute_retrieval_decay(bjork, now)
        # Expected: 1.0 * exp(-0.2/2.0 * 2) = exp(-0.2) ≈ 0.8187
        assert 0.80 < r < 0.83

    def test_success_update(self) -> None:
        from gpd.core.learning import BjorkState, update_bjork_on_success

        bjork = BjorkState(storage_strength=1.0, retrieval_strength=0.8, last_recall_at=None)
        now = datetime(2026, 3, 17, tzinfo=UTC)
        updated = update_bjork_on_success(bjork, now)
        assert updated.storage_strength == 1.3  # +0.3
        assert updated.last_recall_at is not None

    def test_lapse_update(self) -> None:
        from gpd.core.learning import BjorkState, update_bjork_on_lapse

        bjork = BjorkState(storage_strength=2.0, retrieval_strength=0.8, last_recall_at=None)
        now = datetime(2026, 3, 17, tzinfo=UTC)
        updated = update_bjork_on_lapse(bjork, now)
        assert updated.storage_strength == 1.9  # -0.1
        assert abs(updated.retrieval_strength - 0.6) < 1e-10  # 0.8 - 0.2

    def test_retention_score(self) -> None:
        from gpd.core.learning import ConceptMemory, compute_retention

        mem = ConceptMemory(
            concept="test", slug="test",
            last_mastery_level=4,
            bjork={"storage_strength": 5.0, "retrieval_strength": 1.0, "last_recall_at": None},
        )
        ret = compute_retention(mem)
        # 0.6 * (4/4) + 0.4 * 1.0 = 1.0
        assert ret == 1.0

    def test_retention_no_mastery(self) -> None:
        from gpd.core.learning import ConceptMemory, compute_retention

        mem = ConceptMemory(concept="test", slug="test", last_mastery_level=None)
        assert compute_retention(mem) == 0.0


# ===========================================================================
# Graph tests
# ===========================================================================


class TestGraph:
    def test_add_prereq(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import add_prereq

        _make_learning_dir(tmp_path)
        result = add_prereq(str(tmp_path), "ward-identity", "noether-theorem")
        assert result["added"] is True
        assert result["total_prereqs"] == 1

        # Verify file
        graph = _read_json(tmp_path / ".gpd" / "learning" / "concept-prereqs.json")
        assert "noether-theorem" in graph["ward-identity"]

    def test_cycle_detection(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import add_prereq

        _make_learning_dir(tmp_path)
        add_prereq(str(tmp_path), "A", "B")
        add_prereq(str(tmp_path), "B", "C")
        result = add_prereq(str(tmp_path), "C", "A")
        assert "error" in result
        assert "cycle" in result["error"]

    def test_self_loop_rejected(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import add_prereq

        _make_learning_dir(tmp_path)
        result = add_prereq(str(tmp_path), "A", "A")
        assert "error" in result

    def test_remove_prereq(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import add_prereq, remove_prereq

        _make_learning_dir(tmp_path)
        add_prereq(str(tmp_path), "A", "B")
        result = remove_prereq(str(tmp_path), "A", "B")
        assert result["removed"] is True

        graph = _read_json(tmp_path / ".gpd" / "learning" / "concept-prereqs.json")
        assert "A" not in graph

    def test_topological_sort(self) -> None:
        from gpd.core.learning import topological_sort

        graph = {"C": ["B", "A"], "B": ["A"]}
        order = topological_sort(graph)
        # A must come before B, B before C
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_cycle_raises(self) -> None:
        from gpd.core.learning import LearningError, topological_sort

        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        with pytest.raises(LearningError, match="cycle"):
            topological_sort(graph)

    def test_learning_path(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import add_prereq, get_learning_path

        _make_learning_dir(tmp_path)
        add_prereq(str(tmp_path), "ward-identity", "noether-theorem")
        add_prereq(str(tmp_path), "ward-identity", "gauge-invariance")

        result = get_learning_path(str(tmp_path))
        assert "error" not in result
        assert result["count"] == 3
        slugs = [p["slug"] for p in result["path"]]
        assert slugs.index("ward-identity") > slugs.index("noether-theorem")
        assert slugs.index("ward-identity") > slugs.index("gauge-invariance")


# ===========================================================================
# Policy tests
# ===========================================================================


class TestAdaptivePolicy:
    def test_mastery_achieved(self) -> None:
        from gpd.core.learning import apply_adaptive_policy

        p = apply_adaptive_policy(mastery_level=3, previous_level=2, current_type="derive", current_difficulty=3, plateau_count=0)
        assert p.action == "mastered"

    def test_improvement(self) -> None:
        from gpd.core.learning import apply_adaptive_policy

        p = apply_adaptive_policy(mastery_level=2, previous_level=1, current_type="derive", current_difficulty=2, plateau_count=0)
        assert p.action == "improving"
        assert p.next_difficulty == 3  # bumped

    def test_single_plateau(self) -> None:
        from gpd.core.learning import apply_adaptive_policy

        p = apply_adaptive_policy(mastery_level=2, previous_level=2, current_type="derive", current_difficulty=3, plateau_count=1)
        assert p.action == "plateau"
        assert p.next_difficulty == 3  # unchanged

    def test_double_plateau(self) -> None:
        from gpd.core.learning import apply_adaptive_policy

        p = apply_adaptive_policy(mastery_level=2, previous_level=2, current_type="derive", current_difficulty=3, plateau_count=2)
        assert p.action == "double_plateau"
        assert p.next_type == "apply"  # type switch
        assert p.next_difficulty == 2  # reduced

    def test_regression(self) -> None:
        from gpd.core.learning import apply_adaptive_policy

        p = apply_adaptive_policy(mastery_level=1, previous_level=2, current_type="derive", current_difficulty=3, plateau_count=0)
        assert p.action == "regression"
        assert p.next_difficulty == 2
        assert p.challenge_focus == "single-gap"

    def test_first_attempt(self) -> None:
        from gpd.core.learning import apply_adaptive_policy

        p = apply_adaptive_policy(mastery_level=1, previous_level=None, current_type="derive", current_difficulty=2, plateau_count=0)
        assert p.action == "improving"


# ===========================================================================
# Slugify tests
# ===========================================================================


class TestSlugify:
    def test_basic(self) -> None:
        from gpd.core.learning import slugify

        assert slugify("Ward identity") == "ward-identity"
        assert slugify("Noether's Theorem") == "noethers-theorem"
        assert slugify("  Berry Phase  ") == "berry-phase"
        assert slugify("QFT: basics") == "qft-basics"


# ===========================================================================
# Review tools integration
# ===========================================================================


class TestReviewTools:
    def test_record_review(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import record_review

        _make_learning_dir(tmp_path)
        _write_memory(tmp_path, "test-concept", {
            "schema_version": 2, "concept": "test", "slug": "test-concept",
            "last_mastery_level": 3, "last_type": "derive", "last_difficulty": 3,
            "active_gaps": [], "misconceptions": [], "updated_at": "2026-03-16T00:00:00Z",
            "fsrs": {
                "state": 2, "stability": 5.0, "difficulty": 4.0, "step": None,
                "reps": 3, "lapses": 0,
                "last_review": "2026-03-15T00:00:00+00:00",
                "next_review": "2026-03-18T00:00:00+00:00",
                "elapsed_days": 0, "scheduled_days": 3,
            },
            "bjork": {"storage_strength": 2.0, "retrieval_strength": 0.9, "last_recall_at": "2026-03-15T00:00:00+00:00"},
        })

        result = record_review(str(tmp_path), "test-concept", rating=3)
        assert "error" not in result
        assert result["next_review"] is not None
        assert result["fsrs"]["reps"] == 4

    def test_record_review_no_fsrs(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import record_review

        _make_learning_dir(tmp_path)
        _write_memory(tmp_path, "test-concept", {
            "schema_version": 2, "concept": "test", "slug": "test-concept",
            "last_mastery_level": 1, "last_type": "derive", "last_difficulty": 2,
            "active_gaps": [], "misconceptions": [], "updated_at": "2026-03-16T00:00:00Z",
            "fsrs": None,
            "bjork": {"storage_strength": 1.0, "retrieval_strength": 1.0, "last_recall_at": None},
        })

        result = record_review(str(tmp_path), "test-concept", rating=3)
        assert "error" in result
        assert "FSRS card" in result["error"]

    def test_invalid_rating(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import record_review

        _make_learning_dir(tmp_path)
        result = record_review(str(tmp_path), "test", rating=5)
        assert "error" in result

    def test_review_stats(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.learning_server import get_review_stats_tool

        _make_learning_dir(tmp_path)
        _write_memory(tmp_path, "concept-a", {
            "schema_version": 2, "concept": "A", "slug": "concept-a",
            "last_mastery_level": 3, "last_type": "derive", "last_difficulty": 3,
            "active_gaps": [], "misconceptions": [], "updated_at": "2026-03-16T00:00:00Z",
            "fsrs": {
                "state": 2, "stability": 5.0, "difficulty": 4.0, "step": None,
                "reps": 3, "lapses": 0,
                "last_review": "2026-03-15T00:00:00+00:00",
                "next_review": "2026-03-10T00:00:00+00:00",
                "elapsed_days": 0, "scheduled_days": 5,
            },
            "bjork": {"storage_strength": 2.0, "retrieval_strength": 0.9, "last_recall_at": "2026-03-15T00:00:00+00:00"},
        })

        result = get_review_stats_tool(str(tmp_path))
        assert result["total_cards"] == 1
        assert result["total_concepts"] == 1
