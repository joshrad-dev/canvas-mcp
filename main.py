import os
import datetime as dt
from typing import Any, Dict, List, Optional

from canvasapi import Canvas
from fastmcp import FastMCP


# Environment variables
ENV_API_URL = "CANVAS_API_URL"
ENV_API_TOKEN = "CANVAS_API_TOKEN"


_canvas: Optional[Canvas] = None
_current_user_cache: Optional[Any] = None


def _require_env() -> tuple[str, str]:
    api_url = os.getenv(ENV_API_URL)
    api_token = os.getenv(ENV_API_TOKEN)
    if not api_url or not api_token:
        missing = []
        if not api_url:
            missing.append(ENV_API_URL)
        if not api_token:
            missing.append(ENV_API_TOKEN)
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}"
        )
    return api_url, api_token


def _get_canvas() -> Canvas:
    global _canvas
    if _canvas is None:
        api_url, api_token = _require_env()
        _canvas = Canvas(api_url, api_token)
    return _canvas


def _get_current_user():
    global _current_user_cache
    if _current_user_cache is None:
        _current_user_cache = _get_canvas().get_current_user()
    return _current_user_cache


def _serialize(obj: Any, fields: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in fields:
        out[f] = getattr(obj, f, None)
    return out


def _parse_iso8601(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        # Canvas returns e.g. '2024-09-01T23:59:00Z'
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None


mcp = FastMCP("Canvas MCP (Student)")


@mcp.tool
def health() -> dict:
    """Basic health check and env validation. Returns server status and which env vars are present."""
    present = {ENV_API_URL: bool(os.getenv(ENV_API_URL)), ENV_API_TOKEN: bool(os.getenv(ENV_API_TOKEN))}
    return {"ok": all(present.values()), "env": present}


@mcp.tool
def get_current_user() -> dict:
    """Return the current Canvas user profile (id, name, email, login_id)."""
    user = _get_current_user()
    # Commonly available fields on User
    return _serialize(user, [
        "id",
        "name",
        "sortable_name",
        "short_name",
        "login_id",
        "primary_email",
        "time_zone",
        "locale",
    ])


@mcp.tool
def list_my_courses(
    enrollment_state: str = "active",
    include_concluded: bool = False,
) -> List[dict]:
    """List only the current student's favorite courses.

    Notes:
    - Returns the user's favorites via `GET /users/self/favorites/courses`.
    - `enrollment_state` is retained for backward compatibility and is applied client-side.
    - `include_concluded`: include concluded courses in results.
    """
    user = _get_current_user()

    # Retrieve only favorite courses for the current user
    courses = user.get_favorite_courses()

    results: List[dict] = []
    for c in courses:
        # Optionally filter by enrollment_state if available on the course enrollments
        if enrollment_state:
            try:
                # Some Course objects include enrollments; ensure at least one matches the desired state
                enrollments = getattr(c, "enrollments", []) or []
                if enrollments:
                    if not any(
                        (e.get("enrollment_state") or e.get("workflow_state")) == enrollment_state
                        for e in enrollments
                    ):
                        continue
            except Exception:
                # If we can't inspect enrollments, fall back to including the course
                pass

        # Skip concluded unless explicitly included
        if not include_concluded and getattr(c, "workflow_state", None) == "completed":
            continue

        results.append(
            _serialize(
                c,
                [
                    "id",
                    "name",
                    "course_code",
                    "workflow_state",
                    "start_at",
                    "end_at",
                    "enrollment_term_id",
                ],
            )
        )
    return results


@mcp.tool
def list_course_assignments(
    course_id: int,
    bucket: Optional[str] = None,
    search_term: Optional[str] = None,
) -> List[dict]:
    """List assignments for a given course.

    - bucket: filter assignments by 'upcoming', 'past', 'unsubmitted', 'graded', etc.
    - search_term: filter by name substring
    """
    canvas = _get_canvas()
    course = canvas.get_course(course_id)
    kwargs: Dict[str, Any] = {}
    if bucket:
        kwargs["bucket"] = bucket
    if search_term:
        kwargs["search_term"] = search_term
    assignments = course.get_assignments(**kwargs)
    out: List[dict] = []
    for a in assignments:
        out.append(
            _serialize(
                a,
                [
                    "id",
                    "name",
                    "due_at",
                    "points_possible",
                    "submission_types",
                    "allowed_extensions",
                    "lock_at",
                    "unlock_at",
                    "has_overrides",
                    "published",
                ],
            )
        )
    return out


@mcp.tool
def get_assignment_details(course_id: int, assignment_id: int) -> dict:
    """Get details for a specific assignment in a course."""
    canvas = _get_canvas()
    course = canvas.get_course(course_id)
    assignment = course.get_assignment(assignment_id)
    return _serialize(
        assignment,
        [
            "id",
            "name",
            "description",
            "due_at",
            "points_possible",
            "submission_types",
            "allowed_extensions",
            "grading_type",
            "lock_at",
            "unlock_at",
            "muted",
            "has_overrides",
            "published",
            "html_url",
        ],
    )


@mcp.tool
def get_my_submission(course_id: int, assignment_id: int) -> dict:
    """Get the current student's submission for an assignment (status, score, timestamps)."""
    canvas = _get_canvas()
    user = _get_current_user()
    course = canvas.get_course(course_id)
    assignment = course.get_assignment(assignment_id)
    submission = assignment.get_submission(user.id)
    return _serialize(
        submission,
        [
            "id",
            "user_id",
            "workflow_state",
            "submitted_at",
            "graded_at",
            "posted_at",
            "score",
            "grade",
            "attempt",
            "late",
            "missing",
            "excused",
            "submission_type",
            "preview_url",
            "attachments",
        ],
    )


@mcp.tool
def list_upcoming_assignments(days: int = 7, only_unsubmitted: bool = True) -> List[dict]:
    """List assignments due in the next N days across all my courses. Optionally exclude those already submitted."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now + dt.timedelta(days=max(1, days))
    canvas = _get_canvas()
    user = _get_current_user()

    results: List[dict] = []
    courses = user.get_courses(enrollment_state="active")
    for c in courses:
        try:
            for a in c.get_assignments():
                due = _parse_iso8601(getattr(a, "due_at", None))
                if not due:
                    continue
                if not (now <= due <= cutoff):
                    continue
                if only_unsubmitted:
                    try:
                        s = a.get_submission(user.id)
                        if getattr(s, "workflow_state", None) in {"submitted", "graded"} and getattr(s, "submitted_at", None):
                            continue
                    except Exception:
                        # If submission fetch fails, include the assignment anyway
                        pass
                results.append(
                    {
                        "course_id": getattr(c, "id", None),
                        "course_name": getattr(c, "name", None),
                        **_serialize(
                            a,
                            [
                                "id",
                                "name",
                                "due_at",
                                "points_possible",
                                "submission_types",
                                "html_url",
                            ],
                        ),
                    }
                )
        except Exception:
            # Skip courses we can't access fully
            continue
    # Sort by soonest due date
    results.sort(key=lambda x: _parse_iso8601(x.get("due_at")) or dt.datetime.max.replace(tzinfo=dt.timezone.utc))
    return results


@mcp.tool
def get_my_course_grade(course_id: int) -> dict:
    """Return the student's grade summary for a course (current_score, final_score, unposted_current_score)."""
    canvas = _get_canvas()
    user = _get_current_user()
    course = canvas.get_course(course_id)
    enrollments = course.get_enrollments(
        user_id=user.id,
        type=["StudentEnrollment"],
        state=["active", "completed"],
        include=["grades"],
    )
    # There should be at most one matching enrollment for the user
    for e in enrollments:
        grades = getattr(e, "grades", None) or {}
        # Return the most relevant fields
        return {
            "enrollment_id": getattr(e, "id", None),
            "course_id": getattr(e, "course_id", None),
            "user_id": getattr(e, "user_id", None),
            "grades": {
                "html_url": grades.get("html_url"),
                "current_score": grades.get("current_score"),
                "final_score": grades.get("final_score"),
                "current_grade": grades.get("current_grade"),
                "final_grade": grades.get("final_grade"),
                "unposted_current_score": grades.get("unposted_current_score"),
                "unposted_final_score": grades.get("unposted_final_score"),
            },
        }
    return {"message": "No enrollment with grades found for this course."}


@mcp.tool
def list_course_announcements(course_id: int, only_published: bool = True) -> List[dict]:
    """List announcements for a course. Announcements are discussion topics flagged as announcements."""
    canvas = _get_canvas()
    course = canvas.get_course(course_id)
    try:
        topics = course.get_discussion_topics(only_announcements=True)
    except Exception as e:
        return [{"error": f"Could not retrieve announcements: {e}"}]
    out: List[dict] = []
    for t in topics:
        if only_published and getattr(t, "workflow_state", None) != "active":
            continue
        out.append(
            _serialize(
                t,
                [
                    "id",
                    "title",
                    "message",
                    "published",
                    "posted_at",
                    "last_reply_at",
                    "html_url",
                ],
            )
        )
    return out


def main() -> None:
    mcp.run()  # default stdio transport


if __name__ == "__main__":
    main()
