"""MCP server for GPD learning engine — FSRS-6 + Bjork dual-strength memory.

Thin MCP wrapper around gpd.core.learning. Exposes session management,
concept memory, spaced repetition review, and prerequisite graph tools.

Usage:
    python -m gpd.mcp.servers.learning_server
    # or via entry point:
    gpd-mcp-learning
"""

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from gpd.core.errors import GPDError
from gpd.core.learning import (
    ConceptMemory,
    LearningSession,
    append_learning_log,
    apply_adaptive_policy,
    check_prereqs,
    compute_retention,
    detect_cycle,
    get_due_concepts,
    get_review_stats,
    init_fsrs_card,
    list_concepts,
    load_memory,
    load_prereq_graph,
    load_session,
    migrate_legacy_flat_files,
    record_fsrs_review,
    save_memory,
    save_prereq_graph,
    save_session,
    slugify,
    topological_sort,
    update_bjork_on_lapse,
    update_bjork_on_success,
)
from gpd.core.observability import gpd_span

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("gpd-learning")

mcp = FastMCP("gpd-learning")


# ---------------------------------------------------------------------------
# Session tools
# ---------------------------------------------------------------------------


@mcp.tool()
def start_session(
    project_dir: str,
    concept: str,
    challenge_type: str = "derive",
) -> dict:
    """Initialize or resume a learning session for a concept.

    Handles legacy migration, prerequisite checking, and session state init/resume.

    Args:
        project_dir: Absolute path to the project root directory.
        concept: Physics concept to learn (e.g., "harmonic oscillator").
        challenge_type: Challenge type — recall, derive, or apply.
    """
    cwd = Path(project_dir)
    slug = slugify(concept)
    with gpd_span("mcp.learning.start_session", concept=concept):
        try:
            # Migrate legacy flat files if needed
            migrate_legacy_flat_files(cwd, slug)

            # Load or create session
            session = load_session(cwd, slug)
            resumed = session is not None
            if session is None:
                session = LearningSession(
                    concept=concept,
                    slug=slug,
                    current_type=challenge_type,
                )
                save_session(cwd, slug, session)

            # Load or create memory
            memory = load_memory(cwd, slug)
            if memory is None:
                memory = ConceptMemory(
                    concept=concept,
                    slug=slug,
                    last_type=challenge_type,
                    updated_at=datetime.now(UTC).isoformat(),
                )
                save_memory(cwd, slug, memory)

            # Check prerequisites
            graph = load_prereq_graph(cwd)
            weak_prereqs = check_prereqs(cwd, slug, graph)

            return {
                "slug": slug,
                "resumed": resumed,
                "session": session.model_dump(),
                "memory": memory.model_dump(),
                "weak_prereqs": weak_prereqs,
            }
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def update_session(
    project_dir: str,
    slug: str,
    mastery_level: int,
    gaps: list[str],
    misconceptions: list[str] | None = None,
    recommended_next_type: str | None = None,
) -> dict:
    """Record an assessment result, apply adaptive policy, and update Bjork state.

    Call this after each assessment. Returns the adaptive policy decision.

    Args:
        project_dir: Absolute path to the project root directory.
        slug: Concept slug.
        mastery_level: Assessed mastery level (0-4).
        gaps: List of identified gaps.
        misconceptions: List of misconceptions (optional).
        recommended_next_type: Assessor's recommended next challenge type (optional).
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.update_session", slug=slug):
        try:
            session = load_session(cwd, slug)
            if session is None:
                return {"error": f"No active session for {slug}. Call start_session first."}

            memory = load_memory(cwd, slug)
            if memory is None:
                return {"error": f"No memory found for {slug}."}

            # Apply adaptive policy
            policy = apply_adaptive_policy(
                mastery_level=mastery_level,
                previous_level=memory.last_mastery_level,
                current_type=session.current_type,
                current_difficulty=session.difficulty_level,
                plateau_count=session.plateau_count,
            )

            # Override type if assessor recommends and policy doesn't already switch
            if recommended_next_type and policy.action not in ("double_plateau",):
                policy.next_type = recommended_next_type

            # Update Bjork state
            now = datetime.now(UTC)
            if mastery_level >= (memory.last_mastery_level or 0):
                memory.bjork = update_bjork_on_success(memory.bjork, now)
            else:
                memory.bjork = update_bjork_on_lapse(memory.bjork, now)

            # Update plateau tracking
            if policy.action == "plateau":
                session.plateau_count += 1
            elif policy.action == "double_plateau":
                session.plateau_count = 0
            elif policy.action in ("improving", "mastered"):
                session.plateau_count = 0

            # Update session
            session.score_history.append(mastery_level)
            session.gap_history.append(gaps)
            session.current_type = policy.next_type
            session.difficulty_level = policy.next_difficulty
            session.attempt_number += 1
            if policy.action == "mastered":
                session.status = "mastered"
            save_session(cwd, slug, session)

            # Update memory
            memory.last_mastery_level = mastery_level
            memory.last_type = policy.next_type
            memory.last_difficulty = policy.next_difficulty
            memory.active_gaps = gaps
            if misconceptions:
                memory.misconceptions = misconceptions
            memory.updated_at = now.isoformat()
            save_memory(cwd, slug, memory)

            return {
                "policy": policy.model_dump(),
                "session": session.model_dump(),
                "bjork": memory.bjork.model_dump(),
            }
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def end_session(
    project_dir: str,
    slug: str,
    status: str = "paused",
    level_name: str = "",
    gaps_closed: list[str] | None = None,
) -> dict:
    """Finalize a learning session. Initializes FSRS card on mastery.

    Args:
        project_dir: Absolute path to the project root directory.
        slug: Concept slug.
        status: Final status — mastered, paused, or plateau.
        level_name: Human-readable mastery level name.
        gaps_closed: List of gaps closed during the session.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.end_session", slug=slug):
        try:
            session = load_session(cwd, slug)
            if session is None:
                return {"error": f"No session found for {slug}."}

            memory = load_memory(cwd, slug)
            if memory is None:
                return {"error": f"No memory found for {slug}."}

            now = datetime.now(UTC)

            # Init FSRS card on mastery if not already present
            if status == "mastered" and memory.fsrs is None:
                memory.fsrs = init_fsrs_card(now)
                memory.updated_at = now.isoformat()
                save_memory(cwd, slug, memory)

            # Update session status
            session.status = status
            save_session(cwd, slug, session)

            # Build difficulty journey from score history length
            difficulties: list[int] = []
            if session.score_history:
                difficulties = [session.difficulty_level] * len(session.score_history)

            # Append to learning log
            append_learning_log(
                cwd,
                concept=session.concept,
                challenge_type=session.current_type,
                attempts=session.attempt_number - 1,
                final_level=memory.last_mastery_level,
                level_name=level_name or status,
                score_journey=session.score_history,
                difficulty_journey=difficulties,
                gaps_closed=gaps_closed or [],
                gaps_remaining=memory.active_gaps,
                status=status,
            )

            result: dict[str, object] = {
                "status": status,
                "session": session.model_dump(),
                "memory": memory.model_dump(),
            }
            if memory.fsrs:
                result["fsrs_initialized"] = True
                result["next_review"] = memory.fsrs.next_review
            return result
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_memory(project_dir: str, slug: str) -> dict:
    """Load concept memory with computed retention score.

    Args:
        project_dir: Absolute path to the project root directory.
        slug: Concept slug.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.get_memory", slug=slug):
        try:
            memory = load_memory(cwd, slug)
            if memory is None:
                return {"error": f"No memory found for concept '{slug}'."}
            now = datetime.now(UTC)
            result = memory.model_dump()
            result["retention"] = round(compute_retention(memory, now), 3)
            return result
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def list_concepts_tool(project_dir: str) -> dict:
    """List all concepts with mastery and retention info, sorted weakest-first.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.list_concepts"):
        try:
            memories = list_concepts(cwd)
            now = datetime.now(UTC)
            concepts = []
            for mem in memories:
                concepts.append({
                    "slug": mem.slug,
                    "concept": mem.concept,
                    "mastery_level": mem.last_mastery_level,
                    "retention": round(compute_retention(mem, now), 3),
                    "has_fsrs": mem.fsrs is not None,
                    "active_gaps": mem.active_gaps,
                })
            return {"concepts": concepts, "count": len(concepts)}
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def get_prereqs(project_dir: str, slug: str) -> dict:
    """Get prerequisite concepts with mastery info.

    Args:
        project_dir: Absolute path to the project root directory.
        slug: Concept slug to get prerequisites for.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.get_prereqs", slug=slug):
        try:
            graph = load_prereq_graph(cwd)
            prereq_slugs = graph.get(slug, [])
            prereqs = []
            for ps in prereq_slugs:
                mem = load_memory(cwd, ps)
                prereqs.append({
                    "slug": ps,
                    "concept": mem.concept if mem else ps,
                    "mastery_level": mem.last_mastery_level if mem else None,
                    "retention": round(compute_retention(mem), 3) if mem else 0.0,
                })
            return {"concept": slug, "prereqs": prereqs, "count": len(prereqs)}
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


# ---------------------------------------------------------------------------
# Review tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_review_queue(project_dir: str) -> dict:
    """Get FSRS-scheduled concepts due for review, sorted most overdue first.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.get_review_queue"):
        try:
            now = datetime.now(UTC)
            due = get_due_concepts(cwd, now)
            return {"due": due, "count": len(due)}
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def record_review(project_dir: str, slug: str, rating: int) -> dict:
    """Update FSRS card and Bjork state after a review session.

    Args:
        project_dir: Absolute path to the project root directory.
        slug: Concept slug.
        rating: Review quality — 1=Again, 2=Hard, 3=Good, 4=Easy.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.record_review", slug=slug):
        try:
            if rating not in (1, 2, 3, 4):
                return {"error": f"Invalid rating {rating}. Must be 1-4 (Again/Hard/Good/Easy)."}

            memory = load_memory(cwd, slug)
            if memory is None:
                return {"error": f"No memory found for concept '{slug}'."}
            if memory.fsrs is None:
                return {"error": f"Concept '{slug}' has no FSRS card. Mastery (Level 3+) required first."}

            now = datetime.now(UTC)
            memory.fsrs = record_fsrs_review(memory.fsrs, rating, now)

            # Update Bjork based on rating
            if rating >= 3:
                memory.bjork = update_bjork_on_success(memory.bjork, now)
            else:
                memory.bjork = update_bjork_on_lapse(memory.bjork, now)

            memory.updated_at = now.isoformat()
            save_memory(cwd, slug, memory)

            return {
                "slug": slug,
                "fsrs": memory.fsrs.model_dump(),
                "bjork": memory.bjork.model_dump(),
                "next_review": memory.fsrs.next_review,
                "retention": round(compute_retention(memory, now), 3),
            }
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def get_review_stats_tool(project_dir: str) -> dict:
    """Get review dashboard stats: total cards, due now, average retention.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.get_review_stats"):
        try:
            return get_review_stats(cwd)
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


# ---------------------------------------------------------------------------
# Graph tools
# ---------------------------------------------------------------------------


@mcp.tool()
def add_prereq(project_dir: str, concept_slug: str, prereq_slug: str) -> dict:
    """Add a prerequisite edge with cycle detection.

    Args:
        project_dir: Absolute path to the project root directory.
        concept_slug: The concept that requires the prerequisite.
        prereq_slug: The prerequisite concept.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.add_prereq", concept=concept_slug, prereq=prereq_slug):
        try:
            graph = load_prereq_graph(cwd)

            # Check for self-loop
            if concept_slug == prereq_slug:
                return {"error": "A concept cannot be its own prerequisite."}

            # Check for duplicate
            if prereq_slug in graph.get(concept_slug, []):
                return {"error": f"'{prereq_slug}' is already a prerequisite of '{concept_slug}'."}

            # Check for cycle
            if detect_cycle(graph, concept_slug, prereq_slug):
                return {"error": f"Adding '{prereq_slug}' → '{concept_slug}' would create a cycle."}

            # Add edge
            if concept_slug not in graph:
                graph[concept_slug] = []
            graph[concept_slug].append(prereq_slug)
            save_prereq_graph(cwd, graph)

            return {
                "added": True,
                "concept": concept_slug,
                "prereq": prereq_slug,
                "total_prereqs": len(graph[concept_slug]),
            }
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def remove_prereq(project_dir: str, concept_slug: str, prereq_slug: str) -> dict:
    """Remove a prerequisite edge.

    Args:
        project_dir: Absolute path to the project root directory.
        concept_slug: The concept to remove the prerequisite from.
        prereq_slug: The prerequisite to remove.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.remove_prereq", concept=concept_slug, prereq=prereq_slug):
        try:
            graph = load_prereq_graph(cwd)
            prereqs = graph.get(concept_slug, [])
            if prereq_slug not in prereqs:
                return {"error": f"'{prereq_slug}' is not a prerequisite of '{concept_slug}'."}
            prereqs.remove(prereq_slug)
            if not prereqs:
                del graph[concept_slug]
            else:
                graph[concept_slug] = prereqs
            save_prereq_graph(cwd, graph)
            return {"removed": True, "concept": concept_slug, "prereq": prereq_slug}
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


@mcp.tool()
def get_learning_path(project_dir: str) -> dict:
    """Topological sort of prerequisites with mastery info.

    Returns concepts in dependency order (learn prerequisites first).

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = Path(project_dir)
    with gpd_span("mcp.learning.get_learning_path"):
        try:
            graph = load_prereq_graph(cwd)
            if not graph:
                return {"path": [], "count": 0}

            ordered = topological_sort(graph)
            path = []
            for slug in ordered:
                mem = load_memory(cwd, slug)
                path.append({
                    "slug": slug,
                    "concept": mem.concept if mem else slug,
                    "mastery_level": mem.last_mastery_level if mem else None,
                    "retention": round(compute_retention(mem), 3) if mem else 0.0,
                })
            return {"path": path, "count": len(path)}
        except (GPDError, OSError, ValueError, TimeoutError) as e:
            return {"error": str(e)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the gpd-learning MCP server."""
    from gpd.mcp.servers import run_mcp_server

    run_mcp_server(mcp, "GPD Learning MCP Server")


if __name__ == "__main__":
    main()
