"""Time tracking, timesheet submission, review, and utilization APIs."""
from datetime import date, datetime, timedelta
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import func, false
from app import db
from app.models import User, ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_TEAM_LEAD
from app.domain_models import TimeEntry
from app.enterprise_models import Project
from app.routes.utils import active_account_required, api_error, api_success, log_audit

time_tracking_bp = Blueprint("time_tracking", __name__, url_prefix="/api/time-tracking")
ENTRY_STATUSES = {"draft", "submitted", "approved", "rejected"}


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _admin():
    return current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD)


def _date(value, name="work_date"):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must use YYYY-MM-DD format.")


def _entry_query():
    query = TimeEntry.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    if not _admin():
        query = query.filter_by(user_id=current_user.id)
    if request.args.get("status") in ENTRY_STATUSES:
        query = query.filter_by(status=request.args["status"])
    if request.args.get("user_id") and _admin():
        try:
            query = query.filter_by(user_id=int(request.args["user_id"]))
        except ValueError:
            query = query.filter(false())
    if request.args.get("from"):
        try:
            query = query.filter(TimeEntry.work_date >= _date(request.args["from"], "from"))
        except ValueError:
            query = query.filter(false())
    if request.args.get("to"):
        try:
            query = query.filter(TimeEntry.work_date <= _date(request.args["to"], "to"))
        except ValueError:
            query = query.filter(false())
    return query


def _person_in_org(user_id):
    user = db.session.get(User, user_id)
    if not user or (not current_user.has_role(ROLE_SUPER_ADMIN) and user.organization_id != current_user.organization_id):
        raise LookupError("Employee not found in this organization.")
    return user


def _entry_or_none(entry_id):
    query = TimeEntry.query.filter_by(id=entry_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    entry = query.first()
    if entry and not _admin() and entry.user_id != current_user.id:
        return None
    return entry


@time_tracking_bp.get("/entries")
@login_required
@active_account_required
def list_entries():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = _entry_query()
    total = query.count()
    rows = query.order_by(TimeEntry.work_date.desc(), TimeEntry.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return api_success({"items": [row.to_dict() for row in rows], "page": page, "page_size": size,
                        "total": total, "pages": (total + size - 1) // size})


@time_tracking_bp.post("/entries")
@login_required
@active_account_required
def create_entry():
    data = _body()
    if not current_user.organization_id:
        return api_error("An organization must be assigned before logging time.", 409)
    try:
        work_date = _date(data.get("work_date"))
        minutes = int(data.get("minutes"))
        if minutes < 1 or minutes > 1440:
            raise ValueError("minutes must be between 1 and 1440.")
    except (TypeError, ValueError) as exc:
        return api_error(str(exc) or "minutes must be an integer.", 400)
    if work_date > date.today() + timedelta(days=1):
        return api_error("Time cannot be logged more than one day in the future.", 400)
    description = str(data.get("description", "")).strip()
    if len(description) > 1200:
        return api_error("description must be at most 1,200 characters.", 400)
    task_id = data.get("task_id")
    if task_id not in (None, ""):
        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            return api_error("task_id must be an integer.", 400)
        from app.models import Task
        task_query = Task.query.filter_by(id=task_id)
        if not current_user.has_role(ROLE_SUPER_ADMIN):
            task_query = task_query.filter_by(organization_id=current_user.organization_id)
        if not task_query.first():
            return api_error("Task not found in this organization.", 404)
    else:
        task_id = None
    project_id = data.get("project_id")
    if project_id not in (None, ""):
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            return api_error("project_id must be an integer.", 400)
        project = Project.query.filter_by(id=project_id).first()
        if not project or (not current_user.has_role(ROLE_SUPER_ADMIN) and project.organization_id != current_user.organization_id):
            return api_error("Project not found in this organization.", 404)
    else:
        project_id = None
    row = TimeEntry(organization_id=current_user.organization_id, user_id=current_user.id,
                    task_id=task_id, project_id=project_id, work_date=work_date, minutes=minutes,
                    description=description, billable=bool(data.get("billable", False)), status="draft")
    db.session.add(row)
    db.session.commit()
    log_audit("time_entry.created", "time_entry", row.id, {"minutes": minutes, "work_date": work_date.isoformat()})
    return api_success(row.to_dict(), "Time entry created.", 201)


@time_tracking_bp.patch("/entries/<int:entry_id>")
@login_required
@active_account_required
def update_entry(entry_id):
    row = _entry_or_none(entry_id)
    if not row:
        return api_error("Time entry not found.", 404)
    if row.status not in {"draft", "rejected"}:
        return api_error("Only draft or rejected entries can be edited.", 409)
    data = _body()
    try:
        if "work_date" in data:
            row.work_date = _date(data["work_date"])
        if "minutes" in data:
            minutes = int(data["minutes"])
            if not 1 <= minutes <= 1440:
                raise ValueError("minutes must be between 1 and 1440.")
            row.minutes = minutes
    except (TypeError, ValueError) as exc:
        return api_error(str(exc), 400)
    if "description" in data:
        description = str(data["description"]).strip()
        if len(description) > 1200:
            return api_error("description must be at most 1,200 characters.", 400)
        row.description = description
    if "billable" in data:
        row.billable = bool(data["billable"])
    row.status = "draft"
    row.review_note = ""
    db.session.commit()
    log_audit("time_entry.updated", "time_entry", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Time entry updated.")


@time_tracking_bp.post("/entries/<int:entry_id>/submit")
@login_required
@active_account_required
def submit_entry(entry_id):
    row = _entry_or_none(entry_id)
    if not row:
        return api_error("Time entry not found.", 404)
    if row.status not in {"draft", "rejected"}:
        return api_error("Only draft or rejected entries can be submitted.", 409)
    row.status = "submitted"
    row.submitted_at = datetime.utcnow()
    row.review_note = ""
    db.session.commit()
    log_audit("time_entry.submitted", "time_entry", row.id, {})
    return api_success(row.to_dict(), "Time entry submitted for approval.")


@time_tracking_bp.post("/entries/<int:entry_id>/review")
@login_required
@active_account_required
def review_entry(entry_id):
    if not _admin():
        return api_error("Team lead or administrator permission required.", 403)
    row = TimeEntry.query.filter_by(id=entry_id).first()
    if not row or (not current_user.has_role(ROLE_SUPER_ADMIN) and row.organization_id != current_user.organization_id):
        return api_error("Time entry not found.", 404)
    if row.status != "submitted":
        return api_error("Only submitted time entries can be reviewed.", 409)
    data = _body()
    decision = data.get("decision")
    if decision not in {"approve", "reject"}:
        return api_error("decision must be approve or reject.", 400)
    note = str(data.get("note", "")).strip()
    if decision == "reject" and not note:
        return api_error("A rejection note is required.", 400)
    row.status = "approved" if decision == "approve" else "rejected"
    row.reviewed_by = current_user.id
    row.reviewed_at = datetime.utcnow()
    row.review_note = note[:1000]
    db.session.commit()
    log_audit("time_entry.reviewed", "time_entry", row.id, {"decision": decision})
    return api_success(row.to_dict(), f"Time entry {row.status}.")


@time_tracking_bp.get("/summary")
@login_required
@active_account_required
def time_summary():
    query = _entry_query()
    grouped = db.session.query(TimeEntry.status, func.sum(TimeEntry.minutes)).filter(TimeEntry.id.in_(query.with_entities(TimeEntry.id))).group_by(TimeEntry.status).all()
    by_status = {status: int(minutes or 0) for status, minutes in grouped}
    total_approved = by_status.get("approved", 0)
    total_billable_query = query.filter_by(status="approved", billable=True)
    billable_minutes = db.session.query(func.sum(TimeEntry.minutes)).filter(TimeEntry.id.in_(total_billable_query.with_entities(TimeEntry.id))).scalar() or 0
    return api_success({"minutes_by_status": by_status, "hours_by_status": {key: round(value / 60, 2) for key, value in by_status.items()},
                        "approved_minutes": total_approved, "approved_hours": round(total_approved / 60, 2),
                        "billable_approved_minutes": int(billable_minutes), "billable_approved_hours": round(int(billable_minutes) / 60, 2)})
