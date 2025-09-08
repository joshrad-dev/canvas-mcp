Canvas MCP (Student)

Overview
- MCP server exposing student-focused Canvas LMS tools using `canvasapi` and `fastmcp`.
- Transport: stdio (default). Configure via environment variables.

Environment
- `CANVAS_API_URL`: Base URL of your Canvas instance (e.g., `https://school.instructure.com`).
- `CANVAS_API_TOKEN`: Canvas access token for the student account.

Run
- With uv: `uv run python main.py`
- With venv: `python main.py`

Tools
- `health()`: Health check and env presence.
- `get_current_user()`: Current user profile (id, name, email, etc.).
- `list_my_courses(enrollment_state="active", include_concluded=False)`: List enrolled courses.
- `list_course_assignments(course_id, bucket=None, search_term=None)`: List assignments for a course.
- `get_assignment_details(course_id, assignment_id)`: Assignment details.
- `get_my_submission(course_id, assignment_id)`: Current student submission status.
- `list_upcoming_assignments(days=7, only_unsubmitted=True)`: Upcoming assignments across courses.
- `get_my_course_grade(course_id)`: Course grade summary for the student.
- `list_course_announcements(course_id, only_published=True)`: Course announcements.

Notes
- This server intentionally excludes non-student/admin features.
- Ensure the token has access to the courses/resources you wish to read.
