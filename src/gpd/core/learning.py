"""Core learning engine — FSRS-6 spaced repetition + Bjork dual-strength memory.

Pure functions, Pydantic models, and I/O helpers for the gpd-learning MCP server.
No MCP dependency. Separated from gpd-state so learning state never pollutes
research state.

State lives under ``.gpd/learning/``:
- ``{slug}/SESSION.json``  — current loop state
- ``{slug}/MEMORY.json``   — persistent concept memory (schema v2)
- ``concept-prereqs.json`` — prerequisite graph
- ``LEARNING-LOG.md``      — append-only session log
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import fsrs
from pydantic import BaseModel, Field

from gpd.core.errors import LearningError
from gpd.core.utils import atomic_write

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 2
LEARNING_DIR = ".gpd/learning"
PREREQ_FILE = "concept-prereqs.json"
LOG_FILE = "LEARNING-LOG.md"
MASTERY_THRESHOLD = 3  # Level 3+ triggers FSRS card init

# Bjork model defaults
_BJORK_INITIAL_STORAGE = 1.0
_BJORK_INITIAL_RETRIEVAL = 1.0
_BJORK_STORAGE_INCREMENT = 0.3
_BJORK_STORAGE_LAPSE_PENALTY = 0.1
_BJORK_DECAY_RATE = 0.2  # retrieval decay per day


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class FSRSState(BaseModel):
    """FSRS-6 card state persisted in MEMORY.json."""

    state: int = 1  # fsrs.State enum value (1=Learning, 2=Review, 3=Relearning)
    stability: float | None = None
    difficulty: float | None = None
    step: int | None = 0
    reps: int = 0
    lapses: int = 0
    last_review: str | None = None  # ISO datetime
    next_review: str | None = None  # ISO datetime (due)
    elapsed_days: float = 0.0
    scheduled_days: float = 0.0


class BjorkState(BaseModel):
    """Bjork dual-strength memory model state."""

    storage_strength: float = _BJORK_INITIAL_STORAGE
    retrieval_strength: float = _BJORK_INITIAL_RETRIEVAL
    last_recall_at: str | None = None  # ISO datetime


class ConceptMemory(BaseModel):
    """Persistent concept memory — schema v2 with FSRS + Bjork fields."""

    schema_version: int = SCHEMA_VERSION
    concept: str
    slug: str
    last_mastery_level: int | None = None
    last_type: str = "derive"
    last_difficulty: int = 2
    active_gaps: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    updated_at: str = ""
    fsrs: FSRSState | None = None
    bjork: BjorkState = Field(default_factory=BjorkState)


class LearningSession(BaseModel):
    """Active learning session state."""

    concept: str
    slug: str = ""
    current_type: str = "derive"
    difficulty_level: int = 2
    attempt_number: int = 1
    score_history: list[int] = Field(default_factory=list)
    gap_history: list[list[str]] = Field(default_factory=list)
    plateau_count: int = 0
    status: str = "active"  # active | mastered | paused | plateau


class AdaptivePolicy(BaseModel):
    """Result of applying adaptive policy after an assessment."""

    action: str  # mastered | improving | plateau | double_plateau | regression
    next_type: str
    next_difficulty: int
    challenge_focus: str = "multi-gap"  # multi-gap | single-gap
    message: str = ""


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def slugify(concept: str) -> str:
    """Convert concept name to filesystem-safe slug."""
    s = concept.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _learning_dir(project_dir: Path) -> Path:
    return project_dir / LEARNING_DIR


def _concept_dir(project_dir: Path, slug: str) -> Path:
    return _learning_dir(project_dir) / slug


def _prereq_path(project_dir: Path) -> Path:
    return _learning_dir(project_dir) / PREREQ_FILE


def _log_path(project_dir: Path) -> Path:
    return _learning_dir(project_dir) / LOG_FILE


# ---------------------------------------------------------------------------
# I/O: Session
# ---------------------------------------------------------------------------


def load_session(project_dir: Path, slug: str) -> LearningSession | None:
    """Load session state, returning None if not found."""
    path = _concept_dir(project_dir, slug) / "SESSION.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LearningSession(**data)
    except (json.JSONDecodeError, ValueError) as e:
        raise LearningError(f"Corrupt SESSION.json for {slug}: {e}") from e


def save_session(project_dir: Path, slug: str, session: LearningSession) -> None:
    """Write session state atomically."""
    path = _concept_dir(project_dir, slug) / "SESSION.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, session.model_dump_json(indent=2) + "\n")


# ---------------------------------------------------------------------------
# I/O: Memory
# ---------------------------------------------------------------------------


def load_memory(project_dir: Path, slug: str) -> ConceptMemory | None:
    """Load concept memory, auto-migrating v1→v2 on read. Returns None if not found."""
    path = _concept_dir(project_dir, slug) / "MEMORY.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as e:
        raise LearningError(f"Corrupt MEMORY.json for {slug}: {e}") from e
    return migrate_memory_schema(data)


def save_memory(project_dir: Path, slug: str, memory: ConceptMemory) -> None:
    """Write concept memory atomically."""
    path = _concept_dir(project_dir, slug) / "MEMORY.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, memory.model_dump_json(indent=2) + "\n")


def migrate_memory_schema(data: dict) -> ConceptMemory:
    """Migrate MEMORY.json from v1 (no schema_version/fsrs/bjork) to v2 on-read."""
    if data.get("schema_version", 1) < SCHEMA_VERSION:
        data["schema_version"] = SCHEMA_VERSION
        if "fsrs" not in data:
            data["fsrs"] = None
        if "bjork" not in data:
            data["bjork"] = {
                "storage_strength": _BJORK_INITIAL_STORAGE,
                "retrieval_strength": _BJORK_INITIAL_RETRIEVAL,
                "last_recall_at": None,
            }
    return ConceptMemory(**data)


def migrate_legacy_flat_files(project_dir: Path, slug: str) -> bool:
    """Move legacy flat files (.gpd/learning/{slug}-*.ext) into concept folder.

    Returns True if any files were migrated.
    """
    learning_dir = _learning_dir(project_dir)
    concept_dir = _concept_dir(project_dir, slug)
    concept_dir.mkdir(parents=True, exist_ok=True)
    migrated = False

    for legacy in learning_dir.glob(f"{slug}-*"):
        if legacy.is_file() and legacy.parent == learning_dir:
            new_name = legacy.name[len(slug) + 1 :]  # strip "{slug}-" prefix
            target = concept_dir / new_name
            if not target.exists():
                legacy.rename(target)
                migrated = True
    return migrated


def list_concepts(project_dir: Path) -> list[ConceptMemory]:
    """List all concepts with memory files, sorted weakest-first."""
    learning_dir = _learning_dir(project_dir)
    if not learning_dir.exists():
        return []
    memories: list[ConceptMemory] = []
    for concept_dir in sorted(learning_dir.iterdir()):
        mem_file = concept_dir / "MEMORY.json"
        if concept_dir.is_dir() and mem_file.exists():
            try:
                data = json.loads(mem_file.read_text(encoding="utf-8"))
                mem = migrate_memory_schema(data)
                memories.append(mem)
            except (json.JSONDecodeError, ValueError):
                continue
    # Sort: weakest first (None mastery level treated as -1)
    memories.sort(key=lambda m: m.last_mastery_level if m.last_mastery_level is not None else -1)
    return memories


# ---------------------------------------------------------------------------
# I/O: Prerequisite graph
# ---------------------------------------------------------------------------


def load_prereq_graph(project_dir: Path) -> dict[str, list[str]]:
    """Load the prerequisite graph. Returns empty dict if not found."""
    path = _prereq_path(project_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    except (json.JSONDecodeError, ValueError):
        return {}


def save_prereq_graph(project_dir: Path, graph: dict[str, list[str]]) -> None:
    """Write prerequisite graph atomically."""
    path = _prereq_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(graph, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Graph operations
# ---------------------------------------------------------------------------


def check_prereqs(
    project_dir: Path, slug: str, graph: dict[str, list[str]]
) -> list[dict[str, object]]:
    """Return list of weak prerequisites for a concept.

    A prereq is weak if its MEMORY.json is missing or last_mastery_level < 2.
    """
    prereq_slugs = graph.get(slug, [])
    weak: list[dict[str, object]] = []
    for ps in prereq_slugs:
        mem = load_memory(project_dir, ps)
        level = mem.last_mastery_level if mem else None
        if level is None or level < 2:
            weak.append({"slug": ps, "concept": mem.concept if mem else ps, "level": level})
    return weak


def detect_cycle(graph: dict[str, list[str]], source: str, target: str) -> bool:
    """Check if adding edge source→target would create a cycle.

    Returns True if a cycle would be created (target can already reach source).
    """
    visited: set[str] = set()
    stack = [target]
    while stack:
        node = stack.pop()
        if node == source:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph.get(node, []))
    return False


def topological_sort(graph: dict[str, list[str]]) -> list[str]:
    """Topological sort of the prerequisite graph (Kahn's algorithm).

    Returns concepts in dependency order (prerequisites first).
    Raises LearningError if the graph contains a cycle.
    """
    # Build in-degree map over all nodes
    all_nodes: set[str] = set(graph.keys())
    for deps in graph.values():
        all_nodes.update(deps)

    # graph[A] = [B, C] means A requires B, C → forward edges: B→A, C→A
    forward: dict[str, list[str]] = defaultdict(list)
    for node, deps in graph.items():
        for dep in deps:
            forward[dep].append(node)

    in_degree = dict.fromkeys(all_nodes, 0)
    for _src, targets in forward.items():
        for t in targets:
            in_degree[t] += 1

    queue = sorted(n for n in all_nodes if in_degree[n] == 0)
    result: list[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in sorted(forward.get(node, [])):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(all_nodes):
        raise LearningError("Prerequisite graph contains a cycle")

    return result


# ---------------------------------------------------------------------------
# Bjork dual-strength memory
# ---------------------------------------------------------------------------


def compute_retrieval_decay(bjork: BjorkState, now: datetime | None = None) -> float:
    """Compute current retrieval strength given time since last recall.

    Uses exponential decay: R(t) = R_0 * exp(-decay_rate * days / S)
    where S is storage strength (higher storage = slower decay).
    """
    if bjork.last_recall_at is None:
        return bjork.retrieval_strength

    if now is None:
        now = datetime.now(UTC)

    last = datetime.fromisoformat(bjork.last_recall_at)
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)

    days_elapsed = max(0.0, (now - last).total_seconds() / 86400.0)
    effective_decay = _BJORK_DECAY_RATE / max(bjork.storage_strength, 0.1)
    return bjork.retrieval_strength * math.exp(-effective_decay * days_elapsed)


def compute_retention(memory: ConceptMemory, now: datetime | None = None) -> float:
    """Compute overall retention score (0.0-1.0) combining mastery level and Bjork state."""
    if memory.last_mastery_level is None:
        return 0.0

    # Base from mastery level (0-4 mapped to 0.0-1.0)
    mastery_fraction = min(memory.last_mastery_level / 4.0, 1.0)

    # Bjork retrieval decay
    retrieval = compute_retrieval_decay(memory.bjork, now)

    # Weighted combination: 60% mastery, 40% retrieval
    return 0.6 * mastery_fraction + 0.4 * retrieval


def update_bjork_on_success(bjork: BjorkState, now: datetime | None = None) -> BjorkState:
    """Update Bjork state after a successful recall/mastery."""
    if now is None:
        now = datetime.now(UTC)
    return BjorkState(
        storage_strength=min(10.0, bjork.storage_strength + _BJORK_STORAGE_INCREMENT),
        retrieval_strength=min(1.0, compute_retrieval_decay(bjork, now) + 0.3),
        last_recall_at=now.isoformat(),
    )


def update_bjork_on_lapse(bjork: BjorkState, now: datetime | None = None) -> BjorkState:
    """Update Bjork state after a failed recall (regression/lapse)."""
    if now is None:
        now = datetime.now(UTC)
    return BjorkState(
        storage_strength=max(0.1, bjork.storage_strength - _BJORK_STORAGE_LAPSE_PENALTY),
        retrieval_strength=max(0.0, compute_retrieval_decay(bjork, now) - 0.2),
        last_recall_at=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# FSRS-6 integration
# ---------------------------------------------------------------------------

_scheduler = fsrs.Scheduler()


def _card_from_state(state: FSRSState) -> fsrs.Card:
    """Reconstruct an fsrs.Card from persisted FSRSState."""
    card = fsrs.Card()
    card.state = fsrs.State(state.state)
    card.stability = state.stability
    card.difficulty = state.difficulty
    card.step = state.step
    if state.next_review:
        card.due = datetime.fromisoformat(state.next_review)
    if state.last_review:
        card.last_review = datetime.fromisoformat(state.last_review)
    return card


def _state_from_card(card: fsrs.Card, reps: int, lapses: int) -> FSRSState:
    """Convert an fsrs.Card back to persisted FSRSState."""
    last_review = card.last_review.isoformat() if card.last_review else None
    due = card.due.isoformat() if card.due else None
    elapsed = 0.0
    scheduled = 0.0
    if card.last_review and card.due:
        scheduled = (card.due - card.last_review).total_seconds() / 86400.0
    return FSRSState(
        state=card.state.value,
        stability=card.stability,
        difficulty=card.difficulty,
        step=card.step,
        reps=reps,
        lapses=lapses,
        last_review=last_review,
        next_review=due,
        elapsed_days=elapsed,
        scheduled_days=scheduled,
    )


def init_fsrs_card(now: datetime | None = None) -> FSRSState:
    """Initialize a new FSRS card (called when concept reaches Level 3+).

    Does two Good reviews to graduate the card from Learning → Review state.
    A single review leaves the card in Learning with a ~10 minute interval,
    which makes sense for flashcards but not for mastery-loop concepts where
    the user just spent 30+ minutes demonstrating understanding.
    """
    if now is None:
        now = datetime.now(UTC)
    card = fsrs.Card()
    # Two Good reviews: Learning(step 0) → Learning(step 1) → Review
    card, _log = _scheduler.review_card(card, fsrs.Rating.Good, now)
    card, _log = _scheduler.review_card(card, fsrs.Rating.Good, now)
    return _state_from_card(card, reps=2, lapses=0)


def record_fsrs_review(
    state: FSRSState, rating: int, now: datetime | None = None
) -> FSRSState:
    """Record a review and return updated FSRS state.

    Args:
        state: Current FSRS state.
        rating: 1=Again, 2=Hard, 3=Good, 4=Easy (maps to fsrs.Rating).
        now: Review timestamp.
    """
    if now is None:
        now = datetime.now(UTC)
    card = _card_from_state(state)
    fsrs_rating = fsrs.Rating(rating)
    card, _log = _scheduler.review_card(card, fsrs_rating, now)
    new_reps = state.reps + 1
    new_lapses = state.lapses + (1 if rating == 1 else 0)
    return _state_from_card(card, new_reps, new_lapses)


def get_due_concepts(
    project_dir: Path, now: datetime | None = None
) -> list[dict[str, object]]:
    """Get all concepts with FSRS cards that are due for review.

    Returns list sorted by due date (most overdue first).
    """
    if now is None:
        now = datetime.now(UTC)

    memories = list_concepts(project_dir)
    due: list[dict[str, object]] = []
    for mem in memories:
        if mem.fsrs is None:
            continue
        if mem.fsrs.next_review is None:
            continue
        next_dt = datetime.fromisoformat(mem.fsrs.next_review)
        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=UTC)
        if next_dt <= now:
            overdue_days = (now - next_dt).total_seconds() / 86400.0
            due.append({
                "slug": mem.slug,
                "concept": mem.concept,
                "last_mastery_level": mem.last_mastery_level,
                "next_review": mem.fsrs.next_review,
                "overdue_days": round(overdue_days, 1),
                "retention": round(compute_retention(mem, now), 3),
            })
    # Sort most overdue first
    due.sort(key=lambda d: d.get("overdue_days", 0), reverse=True)
    return due


def get_review_stats(project_dir: Path, now: datetime | None = None) -> dict[str, object]:
    """Compute review dashboard statistics."""
    if now is None:
        now = datetime.now(UTC)

    memories = list_concepts(project_dir)
    total_cards = 0
    due_now = 0
    retention_sum = 0.0

    for mem in memories:
        if mem.fsrs is not None:
            total_cards += 1
            ret = compute_retention(mem, now)
            retention_sum += ret
            if mem.fsrs.next_review:
                next_dt = datetime.fromisoformat(mem.fsrs.next_review)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=UTC)
                if next_dt <= now:
                    due_now += 1

    avg_retention = (retention_sum / total_cards) if total_cards > 0 else 0.0
    return {
        "total_cards": total_cards,
        "due_now": due_now,
        "avg_retention": round(avg_retention, 3),
        "total_concepts": len(memories),
    }


# ---------------------------------------------------------------------------
# Adaptive policy
# ---------------------------------------------------------------------------


def apply_adaptive_policy(
    mastery_level: int,
    previous_level: int | None,
    current_type: str,
    current_difficulty: int,
    plateau_count: int,
) -> AdaptivePolicy:
    """Determine next action based on assessment result and session history."""

    # Mastery achieved
    if mastery_level >= MASTERY_THRESHOLD:
        return AdaptivePolicy(
            action="mastered",
            next_type=current_type,
            next_difficulty=current_difficulty,
            message=f"Mastery achieved at Level {mastery_level}!",
        )

    # First attempt — no comparison possible
    if previous_level is None:
        return AdaptivePolicy(
            action="improving",
            next_type=current_type,
            next_difficulty=current_difficulty,
            message=f"First attempt: Level {mastery_level}. Let's improve.",
        )

    # Improving
    if mastery_level > previous_level:
        new_diff = min(5, current_difficulty + 1)
        return AdaptivePolicy(
            action="improving",
            next_type=current_type,
            next_difficulty=new_diff,
            message=(
                f"Improving! Level {previous_level} → {mastery_level}. "
                f"Increasing difficulty to {new_diff}."
            ),
        )

    # Regression
    if mastery_level < previous_level:
        new_diff = max(1, current_difficulty - 1)
        return AdaptivePolicy(
            action="regression",
            next_type=current_type,
            next_difficulty=new_diff,
            challenge_focus="single-gap",
            message=(
                f"Level dropped from {previous_level} to {mastery_level}. "
                f"Reducing difficulty to {new_diff} and isolating one gap."
            ),
        )

    # Plateau (same level)
    if plateau_count >= 2:
        # Double plateau → switch type, reduce difficulty
        new_diff = max(1, current_difficulty - 1)
        type_rotation = {"derive": "apply", "apply": "derive", "recall": "derive"}
        new_type = type_rotation.get(current_type, "derive")
        return AdaptivePolicy(
            action="double_plateau",
            next_type=new_type,
            next_difficulty=new_diff,
            message=(
                f"Plateau detected — switching challenge type to {new_type} "
                f"and reducing difficulty to {new_diff}."
            ),
        )

    # Single plateau
    return AdaptivePolicy(
        action="plateau",
        next_type=current_type,
        next_difficulty=current_difficulty,
        message=f"Same level as last attempt ({mastery_level}). Refocusing on primary gap.",
    )


# ---------------------------------------------------------------------------
# Learning log
# ---------------------------------------------------------------------------

_LOG_HEADER = """\
# Learning Log

Feynman learning loop sessions. Each entry records a mastery journey.

---

"""


def append_learning_log(
    project_dir: Path,
    *,
    concept: str,
    challenge_type: str,
    attempts: int,
    final_level: int | None,
    level_name: str,
    score_journey: list[int],
    difficulty_journey: list[int],
    gaps_closed: list[str],
    gaps_remaining: list[str],
    status: str,
) -> None:
    """Append a session summary to LEARNING-LOG.md."""
    log_path = _log_path(project_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    journey_str = " → ".join(f"Level {s}" for s in score_journey) if score_journey else "—"
    diff_str = " → ".join(str(d) for d in difficulty_journey) if difficulty_journey else "—"

    entry = f"""\
## {now} — {concept}
- **Challenge type:** {challenge_type}
- **Attempts:** {attempts}
- **Final mastery level:** {final_level} ({level_name})
- **Journey:** {journey_str}
- **Gaps closed:** {', '.join(gaps_closed) if gaps_closed else 'none'}
- **Gaps remaining:** {', '.join(gaps_remaining) if gaps_remaining else 'none'}
- **Status:** {status}
- **Difficulty journey:** {diff_str}

"""

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        atomic_write(log_path, existing + entry)
    else:
        atomic_write(log_path, _LOG_HEADER + entry)
