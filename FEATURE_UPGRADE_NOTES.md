# TaskNest feature upgrade notes

## Implemented in this update

- Added persistent leave requests with Casual, Sick, and Personal categories.
- Added employee leave submission/history and calculated annual balances (12 casual, 10 sick, 5 personal days).
- Added approval/rejection decisions with reviewer identity, decision timestamp, reviewer comment, and employee notifications.
- Rejection requires a comment. The server blocks overlapping pending/approved requests, past starts, invalid date ranges, cross-year requests, duplicate decisions, and requests that exceed the allowance.
- Reviewer authorization uses super-admin/admin organization scope, team-lead relationships (`Team.lead_id`, `User.manager_id`, and `TeamMember`), and checks server-side.
- Added leave routes to the existing application and a sidebar link; no new dashboard was created.
- Hardened meeting creation, invitee organization/team validation, RSVP, meeting detail visibility, update validation, and external URL handling.
- Added date navigation and month/week/day views to the calendar, filter-aware date cells, responsive wrapping, concise meeting-link labels, and a safe Join meeting action.
- Unsafe HTTP requests now fail CSRF validation when the token is missing or invalid. Production startup requires `SECRET_KEY`.
- Added leave and meeting authorization regression tests.

## Database

The new `leave_requests` table is created by the application's existing `db.create_all()` startup path. No existing table is altered by this feature. Test the upgrade against a copy of any production database before deployment.

## Run locally (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set a strong SECRET_KEY before using a shared or production environment.
python run.py
```

Run tests:

```powershell
python -m pytest -q
```

## Verification performed for this archive

- Python syntax compilation: passed for modified Python modules and new tests.
- JavaScript syntax check with Node.js: passed for the calendar and leave page scripts.
- Automated pytest suite: not executed successfully in the build environment because Flask is not installed there and package installation was unavailable due to network/DNS restrictions. Run it in the project's Windows virtual environment before deploying.

## LOC policy

This update adds real behavior and tests; it does not add generated filler code to meet an arbitrary line count. The archive excludes `.git`, `.venv`, `.env`, SQLite runtime databases, and uploaded user files for safety. Existing local data in your original folder is not modified.
