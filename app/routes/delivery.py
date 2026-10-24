"""Project milestones, task templates, and timesheet endpoints."""
import json
from datetime import date, datetime, time, timedelta, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import Task, Category, User
from app.enterprise_models import Project, ProjectMilestone, ProjectMember, ProjectTask, TimeEntry, TaskTemplate
from app.routes.utils import active_account_required, api_error, api_success, log_audit
from app.services.enterprise import project_for_user, can_manage_project

delivery_bp = Blueprint("delivery", __name__, url_prefix="/api/enterprise")

def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}

def _date(raw, name):
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must use YYYY-MM-DD format.")

def _datetime(raw, name):
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{name} must be an ISO datetime.")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    except ValueError:
        raise ValueError(f"{name} must be an ISO datetime.")

def _can_manage_timesheet(entry):
    return entry.user_id == current_user.id or current_user.has_role("admin", "super_admin", "hr", "team_lead")

@delivery_bp.get("/projects/<int:project_id>/milestones")
@login_required
@active_account_required
def list_milestones(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    rows = ProjectMilestone.query.filter_by(project_id=project.id).order_by(
        ProjectMilestone.due_date.asc(), ProjectMilestone.id.asc()).all()
    return api_success([r.to_dict() for r in rows])

@delivery_bp.post("/projects/<int:project_id>/milestones")
@login_required
@active_account_required
def create_milestone(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    data = _body()
    title = str(data.get("title", "")).strip()
    if not title or len(title) > 160:
        return api_error("title is required and must be at most 160 characters.", 400)
    try:
        due = _date(data.get("due_date"), "due_date")
    except ValueError as exc:
        return api_error(str(exc), 400)
    owner_id = data.get("owner_id")
    if owner_id is not None:
        try:
            owner_id = int(owner_id)
        except (ValueError, TypeError):
            return api_error("owner_id must be an integer.", 400)
        owner = db.session.get(User, owner_id)
        if not owner or owner.organization_id != project.organization_id:
            return api_error("owner_id must identify a user in this organization.", 400)
    row = ProjectMilestone(project_id=project.id, title=title,
                           description=str(data.get("description", ""))[:4000],
                           due_date=due, owner_id=owner_id, created_by=current_user.id)
    db.session.add(row)
    db.session.commit()
    log_audit("project.milestone_created", "project_milestone", row.id, {"project_id": project.id})
    return api_success(row.to_dict(), "Milestone created.", 201)

@delivery_bp.patch("/milestones/<int:milestone_id>")
@login_required
@active_account_required
def update_milestone(milestone_id):
    row = ProjectMilestone.query.get(milestone_id)
    if not row:
        return api_error("Milestone not found.", 404)
    project, error = project_for_user(row.project_id, current_user)
    if error:
        return api_error("Milestone not found.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    data = _body()
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 160:
            return api_error("title must be at most 160 characters.", 400)
        row.title = title
    if "description" in data:
        row.description = str(data["description"])[:4000]
    if "status" in data:
        if data["status"] not in {"open", "in_progress", "completed", "cancelled"}:
            return api_error("Unsupported milestone status.", 400)
        row.status = data["status"]
    if "due_date" in data:
        try:
            row.due_date = _date(data["due_date"], "due_date")
        except ValueError as exc:
            return api_error(str(exc), 400)
    db.session.commit()
    return api_success(row.to_dict(), "Milestone updated.")

@delivery_bp.delete("/milestones/<int:milestone_id>")
@login_required
@active_account_required
def delete_milestone(milestone_id):
    row = ProjectMilestone.query.get(milestone_id)
    if not row:
        return api_error("Milestone not found.", 404)
    project, error = project_for_user(row.project_id, current_user)
    if error:
        return api_error("Milestone not found.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    db.session.delete(row)
    db.session.commit()
    log_audit("project.milestone_deleted", "project_milestone", milestone_id, {})
    return api_success({"deleted": True})

@delivery_bp.get("/time-entries")
@login_required
@active_account_required
def list_time_entries():
    query = TimeEntry.query.filter_by(organization_id=current_user.organization_id)
    if not current_user.has_role("admin", "super_admin", "hr", "team_lead"):
        query = query.filter_by(user_id=current_user.id)
    else:
        if request.args.get("user_id"):
            try:
                query = query.filter_by(user_id=int(request.args["user_id"]))
            except ValueError:
                return api_error("user_id must be an integer.", 400)
    if request.args.get("status") in {"draft", "submitted", "approved", "rejected"}:
        query = query.filter_by(status=request.args["status"])
    start_raw, end_raw = request.args.get("start_date"), request.args.get("end_date")
    try:
        start_date, end_date = _date(start_raw, "start_date"), _date(end_raw, "end_date")
    except ValueError as exc:
        return api_error(str(exc), 400)
    if start_date and end_date and start_date > end_date:
        return api_error("start_date cannot be after end_date.", 400)
    if start_date:
        query = query.filter(TimeEntry.started_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(TimeEntry.started_at < datetime.combine(end_date + timedelta(days=1), time.min))
    rows = query.order_by(TimeEntry.started_at.desc()).limit(500).all()
    total_minutes = sum((r.duration_minutes or 0) for r in rows)
    return api_success({"items": [r.to_dict() for r in rows], "total_minutes": total_minutes,
                        "count": len(rows)})

@delivery_bp.post("/time-entries")
@login_required
@active_account_required
def create_time_entry():
    data = _body()
    try:
        started = _datetime(data.get("started_at"), "started_at")
        ended = _datetime(data["ended_at"], "ended_at") if data.get("ended_at") else None
    except ValueError as exc:
        return api_error(str(exc), 400)
    if ended and ended <= started:
        return api_error("ended_at must be after started_at.", 400)
    duration = int((ended - started).total_seconds() // 60) if ended else None
    if duration is not None and duration > 24 * 60:
        return api_error("A single time entry cannot exceed 24 hours.", 400)
    task_id = data.get("task_id")
    project_id = data.get("project_id")
    task = db.session.get(Task, task_id) if task_id is not None else None
    project = db.session.get(Project, project_id) if project_id is not None else None
    if task_id is not None and (not task or task.organization_id != current_user.organization_id):
        return api_error("Task not found in your organization.", 404)
    if project_id is not None and (not project or project.organization_id != current_user.organization_id):
        return api_error("Project not found in your organization.", 404)
    if task and project:
        linked = ProjectTask.query.filter_by(project_id=project.id, task_id=task.id).first()
        if not linked:
            return api_error("Task is not linked to the selected project.", 409)
    row = TimeEntry(organization_id=current_user.organization_id, task_id=task.id if task else None,
                    project_id=project.id if project else None, user_id=current_user.id,
                    started_at=started, ended_at=ended, duration_minutes=duration,
                    note=str(data.get("note", ""))[:1000], billable=bool(data.get("billable", False)),
                    status="draft")
    db.session.add(row)
    db.session.commit()
    log_audit("time_entry.created", "time_entry", row.id, {"minutes": duration})
    return api_success(row.to_dict(), "Time entry created.", 201)

@delivery_bp.patch("/time-entries/<int:entry_id>")
@login_required
@active_account_required
def update_time_entry(entry_id):
    row = TimeEntry.query.filter_by(id=entry_id, organization_id=current_user.organization_id).first()
    if not row:
        return api_error("Time entry not found.", 404)
    if row.user_id != current_user.id or row.status not in {"draft", "rejected"}:
        return api_error("Only the owner can edit a draft or rejected entry.", 403)
    data = _body()
    if "note" in data:
        row.note = str(data["note"])[:1000]
    if "billable" in data:
        row.billable = bool(data["billable"])
    try:
        started = _datetime(data["started_at"], "started_at") if "started_at" in data else row.started_at
        ended = _datetime(data["ended_at"], "ended_at") if data.get("ended_at") else (None if "ended_at" in data else row.ended_at)
    except ValueError as exc:
        return api_error(str(exc), 400)
    if ended and ended <= started:
        return api_error("ended_at must be after started_at.", 400)
    duration = int((ended - started).total_seconds() // 60) if ended else None
    if duration is not None and duration > 24 * 60:
        return api_error("A single time entry cannot exceed 24 hours.", 400)
    row.started_at, row.ended_at, row.duration_minutes = started, ended, duration
    db.session.commit()
    return api_success(row.to_dict(), "Time entry updated.")

@delivery_bp.post("/time-entries/<int:entry_id>/submit")
@login_required
@active_account_required
def submit_time_entry(entry_id):
    row = TimeEntry.query.filter_by(id=entry_id, organization_id=current_user.organization_id).first()
    if not row:
        return api_error("Time entry not found.", 404)
    if row.user_id != current_user.id:
        return api_error("Only the owner can submit this entry.", 403)
    if row.status not in {"draft", "rejected"}:
        return api_error("Only draft or rejected entries can be submitted.", 409)
    if not row.duration_minutes or row.duration_minutes < 1:
        return api_error("Complete the entry with a positive duration before submitting.", 409)
    row.status = "submitted"
    db.session.commit()
    log_audit("time_entry.submitted", "time_entry", row.id, {})
    return api_success(row.to_dict(), "Time entry submitted for approval.")

@delivery_bp.post("/time-entries/<int:entry_id>/decision")
@login_required
@active_account_required
def decide_time_entry(entry_id):
    if not current_user.has_role("admin", "super_admin", "hr", "team_lead"):
        return api_error("Timesheet approval permission required.", 403)
    row = TimeEntry.query.filter_by(id=entry_id, organization_id=current_user.organization_id).first()
    if not row:
        return api_error("Time entry not found.", 404)
    if row.status != "submitted":
        return api_error("Only submitted entries can be decided.", 409)
    decision = _body().get("decision")
    if decision not in {"approved", "rejected"}:
        return api_error("decision must be approved or rejected.", 400)
    row.status = decision
    row.approved_by = current_user.id
    row.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    log_audit(f"time_entry.{decision}", "time_entry", row.id, {"user_id": row.user_id})
    return api_success(row.to_dict(), f"Time entry {decision}.")

@delivery_bp.get("/task-templates")
@login_required
@active_account_required
def list_task_templates():
    query = TaskTemplate.query.filter_by(organization_id=current_user.organization_id, active=True)
    rows = query.filter((TaskTemplate.owner_id == current_user.id) |
                        (TaskTemplate.owner_id.is_not(None) if current_user.has_role("admin", "super_admin", "team_lead") else False)).order_by(TaskTemplate.name.asc()).all()
    return api_success([row.to_dict() for row in rows])

@delivery_bp.post("/task-templates")
@login_required
@active_account_required
def create_task_template():
    data = _body()
    name = str(data.get("name", "")).strip()
    priority = data.get("default_priority", "medium")
    checklist = data.get("checklist", [])
    if not name or len(name) > 140:
        return api_error("name is required and must be at most 140 characters.", 400)
    if priority not in {"low", "medium", "high", "urgent"}:
        return api_error("Unsupported default_priority.", 400)
    if not isinstance(checklist, list) or len(checklist) > 100 or any(not isinstance(x, str) or len(x) > 300 for x in checklist):
        return api_error("checklist must contain at most 100 text items of 300 characters.", 400)
    category_id = data.get("default_category_id")
    if category_id is not None:
        category = db.session.get(Category, category_id)
        if not category:
            return api_error("Category not found.", 404)
        if category.user_id != current_user.id and not current_user.has_role("admin", "super_admin"):
            return api_error("You cannot use a category owned by another employee.", 403)
    row = TaskTemplate(organization_id=current_user.organization_id, owner_id=current_user.id,
                       name=name, description=str(data.get("description", ""))[:4000],
                       default_priority=priority, default_category_id=category_id,
                       checklist_json=json.dumps(checklist))
    db.session.add(row)
    db.session.commit()
    log_audit("task_template.created", "task_template", row.id, {})
    return api_success(row.to_dict(), "Task template created.", 201)

@delivery_bp.patch("/task-templates/<int:template_id>")
@login_required
@active_account_required
def update_task_template(template_id):
    row = TaskTemplate.query.filter_by(id=template_id, organization_id=current_user.organization_id).first()
    if not row:
        return api_error("Task template not found.", 404)
    if row.owner_id != current_user.id and not current_user.has_role("admin", "super_admin", "team_lead"):
        return api_error("You cannot edit this template.", 403)
    data = _body()
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 140:
            return api_error("name must be at most 140 characters.", 400)
        row.name = name
    if "description" in data:
        row.description = str(data["description"])[:4000]
    if "default_priority" in data:
        if data["default_priority"] not in {"low", "medium", "high", "urgent"}:
            return api_error("Unsupported default_priority.", 400)
        row.default_priority = data["default_priority"]
    if "checklist" in data:
        checklist = data["checklist"]
        if not isinstance(checklist, list) or len(checklist) > 100 or any(not isinstance(x, str) or len(x) > 300 for x in checklist):
            return api_error("checklist must contain at most 100 text items.", 400)
        row.checklist_json = json.dumps(checklist)
    db.session.commit()
    return api_success(row.to_dict(), "Task template updated.")

@delivery_bp.delete("/task-templates/<int:template_id>")
@login_required
@active_account_required
def archive_task_template(template_id):
    row = TaskTemplate.query.filter_by(id=template_id, organization_id=current_user.organization_id).first()
    if not row:
        return api_error("Task template not found.", 404)
    if row.owner_id != current_user.id and not current_user.has_role("admin", "super_admin", "team_lead"):
        return api_error("You cannot archive this template.", 403)
    row.active = False
    db.session.commit()
    return api_success({"id": row.id, "active": False}, "Task template archived.")
