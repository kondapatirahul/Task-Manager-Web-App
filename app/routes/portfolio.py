"""Project portfolio, membership, task linking, and dependency graph APIs."""
from datetime import date
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import Task, User, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.enterprise_models import Project, ProjectMember, ProjectTask, TaskDependency
from app.routes.utils import active_account_required, api_error, api_success, log_audit
from app.services.enterprise import project_for_user, can_manage_project, slug_key, detect_dependency_cycle

portfolio_bp = Blueprint("portfolio", __name__, url_prefix="/api/enterprise")


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must use YYYY-MM-DD format.")


def _project_query():
    query = Project.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        member_project_ids = db.session.query(ProjectMember.project_id).filter_by(user_id=current_user.id)
        query = query.filter(or_(Project.owner_id == current_user.id, Project.id.in_(member_project_ids)))
    status = request.args.get("status")
    if status in {"active", "on_hold", "completed", "archived"}:
        query = query.filter_by(status=status)
    search = request.args.get("q", "").strip()
    if search:
        term = f"%{search[:100]}%"
        query = query.filter(or_(Project.name.ilike(term), Project.key.ilike(term), Project.description.ilike(term)))
    return query


@portfolio_bp.get("/projects")
@login_required
@active_account_required
def list_projects():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = _project_query().order_by(Project.updated_at.desc(), Project.id.desc())
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return api_success({"items": [p.to_dict() for p in rows],
                        "pagination": {"page": page, "page_size": size, "total": total,
                                       "pages": (total + size - 1) // size}})


@portfolio_bp.post("/projects")
@login_required
@active_account_required
def create_project():
    data = _body()
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 140:
        return api_error("name is required and must be at most 140 characters.", 400)
    if current_user.organization_id is None and not current_user.has_role(ROLE_SUPER_ADMIN):
        return api_error("Your account must belong to an organization.", 409)
    key = slug_key(data.get("key") or name)
    organization_id = data.get("organization_id") if current_user.has_role(ROLE_SUPER_ADMIN) else current_user.organization_id
    if organization_id is None:
        return api_error("organization_id is required for super administrators.", 400)
    if Project.query.filter_by(organization_id=organization_id, key=key).first():
        return api_error("A project with this key already exists in the organization.", 409)
    try:
        start = _date(data.get("start_date"), "start_date")
        target = _date(data.get("target_date"), "target_date")
    except ValueError as exc:
        return api_error(str(exc), 400)
    if start and target and target < start:
        return api_error("target_date cannot be before start_date.", 400)
    project = Project(organization_id=organization_id, owner_id=current_user.id,
                      name=name, key=key, description=str(data.get("description", ""))[:10000],
                      status="active", start_date=start, target_date=target)
    db.session.add(project)
    db.session.flush()
    db.session.add(ProjectMember(project_id=project.id, user_id=current_user.id,
                                 role="owner", added_by=current_user.id))
    db.session.commit()
    log_audit("project.created", "project", project.id, {"key": key})
    return api_success(project.to_dict(), "Project created.", 201)


@portfolio_bp.get("/projects/<int:project_id>")
@login_required
@active_account_required
def get_project(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found." if error == "not_found" else "You cannot access this project.", 404 if error == "not_found" else 403)
    members = ProjectMember.query.filter_by(project_id=project.id).all()
    links = ProjectTask.query.filter_by(project_id=project.id).count()
    return api_success({**project.to_dict(), "members": [m.to_dict() for m in members], "task_count": links})


@portfolio_bp.patch("/projects/<int:project_id>")
@login_required
@active_account_required
def update_project(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    data = _body()
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 140:
            return api_error("name must be between 1 and 140 characters.", 400)
        project.name = name
    if "description" in data:
        project.description = str(data["description"])[:10000]
    if "status" in data:
        if data["status"] not in {"active", "on_hold", "completed", "archived"}:
            return api_error("Unsupported project status.", 400)
        project.status = data["status"]
    if "target_date" in data or "start_date" in data:
        try:
            if "start_date" in data:
                project.start_date = _date(data["start_date"], "start_date")
            if "target_date" in data:
                project.target_date = _date(data["target_date"], "target_date")
        except ValueError as exc:
            return api_error(str(exc), 400)
        if project.start_date and project.target_date and project.target_date < project.start_date:
            return api_error("target_date cannot be before start_date.", 400)
    db.session.commit()
    log_audit("project.updated", "project", project.id, {"fields": sorted(data.keys())})
    return api_success(project.to_dict(), "Project updated.")


@portfolio_bp.delete("/projects/<int:project_id>")
@login_required
@active_account_required
def archive_project(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    project.status = "archived"
    db.session.commit()
    log_audit("project.archived", "project", project.id, {})
    return api_success({"id": project.id, "status": project.status}, "Project archived.")


@portfolio_bp.get("/projects/<int:project_id>/members")
@login_required
@active_account_required
def list_project_members(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    rows = ProjectMember.query.filter_by(project_id=project.id).order_by(ProjectMember.created_at.asc()).all()
    return api_success([m.to_dict() for m in rows])


@portfolio_bp.post("/projects/<int:project_id>/members")
@login_required
@active_account_required
def add_project_member(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    data = _body()
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return api_error("user_id must be an integer.", 400)
    user = db.session.get(User, user_id)
    if not user or (not current_user.has_role(ROLE_SUPER_ADMIN) and user.organization_id != project.organization_id):
        return api_error("User not found in this organization.", 404)
    role = data.get("role", "contributor")
    if role not in {"contributor", "manager", "viewer"}:
        return api_error("role must be contributor, manager, or viewer.", 400)
    member = ProjectMember.query.filter_by(project_id=project.id, user_id=user.id).first()
    if member:
        member.role = role
    else:
        member = ProjectMember(project_id=project.id, user_id=user.id, role=role, added_by=current_user.id)
        db.session.add(member)
    db.session.commit()
    log_audit("project.member_added", "project", project.id, {"user_id": user.id, "role": role})
    return api_success(member.to_dict(), "Project membership saved.", 201)


@portfolio_bp.delete("/projects/<int:project_id>/members/<int:user_id>")
@login_required
@active_account_required
def remove_project_member(project_id, user_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    member = ProjectMember.query.filter_by(project_id=project.id, user_id=user_id).first()
    if not member:
        return api_error("Project member not found.", 404)
    if member.role == "owner":
        return api_error("Transfer project ownership before removing the owner.", 409)
    db.session.delete(member)
    db.session.commit()
    log_audit("project.member_removed", "project", project.id, {"user_id": user_id})
    return api_success({"removed": True})


@portfolio_bp.get("/projects/<int:project_id>/tasks")
@login_required
@active_account_required
def list_project_tasks(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    from app.models import Task
    rows = (db.session.query(Task).join(ProjectTask, ProjectTask.task_id == Task.id)
            .filter(ProjectTask.project_id == project.id).order_by(Task.id.desc()).all())
    return api_success([t.to_dict() for t in rows])


@portfolio_bp.post("/projects/<int:project_id>/tasks")
@login_required
@active_account_required
def link_project_task(project_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    data = _body()
    try:
        task_id = int(data.get("task_id"))
    except (TypeError, ValueError):
        return api_error("task_id must be an integer.", 400)
    task = db.session.get(Task, task_id)
    if not task or (not current_user.has_role(ROLE_SUPER_ADMIN) and task.organization_id != project.organization_id):
        return api_error("Task not found in this organization.", 404)
    link = ProjectTask.query.filter_by(project_id=project.id, task_id=task.id).first()
    if not link:
        link = ProjectTask(project_id=project.id, task_id=task.id, linked_by=current_user.id)
        db.session.add(link)
        db.session.commit()
    return api_success({"project_id": project.id, "task_id": task.id}, "Task linked to project.", 201)


@portfolio_bp.delete("/projects/<int:project_id>/tasks/<int:task_id>")
@login_required
@active_account_required
def unlink_project_task(project_id, task_id):
    project, error = project_for_user(project_id, current_user)
    if error:
        return api_error("Project not found or inaccessible.", 404)
    if not can_manage_project(project, current_user):
        return api_error("Project manager permission required.", 403)
    link = ProjectTask.query.filter_by(project_id=project.id, task_id=task_id).first()
    if not link:
        return api_error("Project task link not found.", 404)
    db.session.delete(link)
    db.session.commit()
    return api_success({"unlinked": True})


@portfolio_bp.get("/tasks/<int:task_id>/dependencies")
@login_required
@active_account_required
def list_task_dependencies(task_id):
    task = db.session.get(Task, task_id)
    if not task or (not current_user.has_role(ROLE_SUPER_ADMIN) and task.organization_id != current_user.organization_id):
        return api_error("Task not found.", 404)
    rows = TaskDependency.query.filter_by(task_id=task.id).all()
    return api_success([r.to_dict() for r in rows])


@portfolio_bp.post("/tasks/<int:task_id>/dependencies")
@login_required
@active_account_required
def create_task_dependency(task_id):
    task = db.session.get(Task, task_id)
    if not task or (not current_user.has_role(ROLE_SUPER_ADMIN) and task.organization_id != current_user.organization_id):
        return api_error("Task not found.", 404)
    data = _body()
    try:
        prerequisite_id = int(data.get("depends_on_task_id"))
    except (TypeError, ValueError):
        return api_error("depends_on_task_id must be an integer.", 400)
    prerequisite = db.session.get(Task, prerequisite_id)
    if not prerequisite or prerequisite.organization_id != task.organization_id:
        return api_error("Prerequisite task not found in this organization.", 404)
    kind = data.get("dependency_type", "blocks")
    if kind not in {"blocks", "relates_to", "duplicates"}:
        return api_error("Unsupported dependency_type.", 400)
    if kind == "blocks" and detect_dependency_cycle(task.id, prerequisite.id):
        return api_error("This dependency would create a cycle.", 409)
    row = TaskDependency.query.filter_by(task_id=task.id, depends_on_task_id=prerequisite.id).first()
    if row:
        return api_success(row.to_dict(), "Dependency already exists.")
    row = TaskDependency(organization_id=task.organization_id, task_id=task.id,
                         depends_on_task_id=prerequisite.id, dependency_type=kind,
                         created_by=current_user.id)
    db.session.add(row)
    db.session.commit()
    log_audit("task.dependency_added", "task", task.id, {"depends_on_task_id": prerequisite.id, "type": kind})
    return api_success(row.to_dict(), "Dependency created.", 201)


@portfolio_bp.delete("/tasks/<int:task_id>/dependencies/<int:dependency_id>")
@login_required
@active_account_required
def delete_task_dependency(task_id, dependency_id):
    task = db.session.get(Task, task_id)
    if not task or (not current_user.has_role(ROLE_SUPER_ADMIN) and task.organization_id != current_user.organization_id):
        return api_error("Task not found.", 404)
    row = TaskDependency.query.filter_by(id=dependency_id, task_id=task.id).first()
    if not row:
        return api_error("Dependency not found.", 404)
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN) and row.created_by != current_user.id:
        return api_error("You cannot remove this dependency.", 403)
    db.session.delete(row)
    db.session.commit()
    return api_success({"removed": True})
