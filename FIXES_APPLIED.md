# TaskNest fixes applied

## Changes
- Authenticated visits to `/` now redirect to the dashboard appropriate to the signed-in role.
- Login rotates the session state before establishing an authenticated session.
- Logout clears the entire Flask session and marks the response as non-cacheable.
- Non-static responses now send `Cache-Control: no-store` headers to reduce the chance of protected pages being displayed from browser cache after logout.
- Productivity reports now accept `range_days` (the reports page's query parameter) and return the `metrics`, trend, status, priority, and workload fields consumed by `templates/reports.html`.
- Report metrics and workload are computed from database task records, with task scoping for employees and team leads.

## Verification
- Python syntax compilation passed for `app/__init__.py`, `app/models.py`, and all `app/routes/*.py` files.
- Automated pytest execution could not be completed in this build environment because Flask dependencies were not installed and package installation was unavailable. Run `python -m pip install -r requirements.txt` and `python -m pytest -q` locally before deployment.

## Database and secrets
- `.env` is intentionally excluded from this ZIP. Create it from `.env.example` and set a private `SECRET_KEY`.
- The provided `instance/tasks.db` and uploads are retained for local continuity. This SQLite database may contain user records; share it only with authorized teammates. For a team or production deployment, prefer per-developer databases or a properly secured shared database.
