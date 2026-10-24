"""Objectives and key-results API with auditable progress updates."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import User, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.domain_models import Objective, KeyResult, KeyResultUpdate
from app.enterprise_models import Project
from app.routes.utils import active_account_required, api_error, api_success, log_audit

objectives_bp = Blueprint("objectives", __name__, url_prefix="/api/objectives")
STATUSES = {"draft", "active", "at_risk", "completed", "cancelled"}
PERIODS = {"monthly", "quarterly", "half_yearly", "annual", "custom"}


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _date(value, name):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{name} must use YYYY-MM-DD format.")


def _decimal(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be numeric.")
    if not result.is_finite() or abs(result) > Decimal("9999999999999999"):
        raise ValueError(f"{name} is outside the supported range.")
    return result


def _admin():
    return current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)


def _query():
    query = Objective.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    if not _admin():
        query = query.filter(or_(Objective.owner_id == current_user.id, Objective.created_by == current_user.id))
    status = request.args.get("status")
    if status in STATUSES:
        query = query.filter_by(status=status)
    period = request.args.get("period")
    if period in PERIODS:
        query = query.filter_by(period=period)
    q = request.args.get("q", "").strip()[:100]
    if q:
        query = query.filter(Objective.title.ilike(f"%{q}%"))
    return query


def _person(user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("owner_id must be an integer.")
    user = db.session.get(User, user_id)
    if not user or (not current_user.has_role(ROLE_SUPER_ADMIN) and user.organization_id != current_user.organization_id):
        raise LookupError("Owner not found in this organization.")
    return user.id


def _objective(objective_id, writable=False):
    query = Objective.query.filter_by(id=objective_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    obj = query.first()
    if not obj:
        return None, (api_error("Objective not found.", 404))
    if writable and not _admin() and obj.owner_id != current_user.id and obj.created_by != current_user.id:
        return None, api_error("You cannot modify this objective.", 403)
    return obj, None


@objectives_bp.get("")
@login_required
@active_account_required
def list_objectives():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = _query()
    total = query.count()
    rows = query.order_by(Objective.due_date.asc().nullslast(), Objective.updated_at.desc()).offset((page - 1) * size).limit(size).all()
    return api_success({"items": [o.to_dict() for o in rows], "page": page, "page_size": size,
                        "total": total, "pages": (total + size - 1) // size})


@objectives_bp.post("")
@login_required
@active_account_required
def create_objective():
    data = _body()
    title = str(data.get("title", "")).strip()
    period = str(data.get("period", "quarterly"))
    if not title or len(title) > 180 or period not in PERIODS:
        return api_error("A valid title and period are required.", 400)
    try:
        owner_id = _person(data.get("owner_id", current_user.id))
        start = _date(data.get("start_date"), "start_date")
        due = _date(data.get("due_date"), "due_date")
        confidence = int(data.get("confidence", 3))
        if not 1 <= confidence <= 5:
            raise ValueError("confidence must be from 1 to 5.")
        if start and due and due < start:
            raise ValueError("due_date cannot be before start_date.")
    except (ValueError, LookupError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    project_id = data.get("project_id")
    if project_id:
        project = db.session.get(Project, project_id)
        if not project or (not current_user.has_role(ROLE_SUPER_ADMIN) and project.organization_id != current_user.organization_id):
            return api_error("Project not found in this organization.", 404)
    obj = Objective(organization_id=current_user.organization_id, project_id=project_id,
        owner_id=owner_id, created_by=current_user.id, title=title,
        description=str(data.get("description", ""))[:12000], period=period,
        start_date=start, due_date=due, status="draft" if data.get("draft") else "active", confidence=confidence)
    db.session.add(obj)
    db.session.commit()
    log_audit("objective.created", "objective", obj.id, {"period": period})
    return api_success(obj.to_dict(include_key_results=True), "Objective created.", 201)


@objectives_bp.get("/<int:objective_id>")
@login_required
@active_account_required
def get_objective(objective_id):
    obj, error = _objective(objective_id)
    if error:
        return error
    return api_success(obj.to_dict(include_key_results=True))


@objectives_bp.patch("/<int:objective_id>")
@login_required
@active_account_required
def update_objective(objective_id):
    obj, error = _objective(objective_id, writable=True)
    if error:
        return error
    data = _body()
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 180:
            return api_error("title must contain 1–180 characters.", 400)
        obj.title = title
    if "description" in data:
        obj.description = str(data["description"])[:12000]
    if "status" in data:
        if data["status"] not in STATUSES:
            return api_error("Unsupported objective status.", 400)
        obj.status = data["status"]
    if "period" in data:
        if data["period"] not in PERIODS:
            return api_error("Unsupported period.", 400)
        obj.period = data["period"]
    try:
        if "owner_id" in data:
            obj.owner_id = _person(data["owner_id"])
        if "start_date" in data:
            obj.start_date = _date(data["start_date"], "start_date")
        if "due_date" in data:
            obj.due_date = _date(data["due_date"], "due_date")
        if obj.start_date and obj.due_date and obj.due_date < obj.start_date:
            raise ValueError("due_date cannot be before start_date.")
        if "confidence" in data:
            value = int(data["confidence"])
            if not 1 <= value <= 5:
                raise ValueError("confidence must be from 1 to 5.")
            obj.confidence = value
    except (ValueError, LookupError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    db.session.commit()
    log_audit("objective.updated", "objective", obj.id, {"fields": sorted(data)})
    return api_success(obj.to_dict(include_key_results=True), "Objective updated.")


@objectives_bp.post("/<int:objective_id>/key-results")
@login_required
@active_account_required
def create_key_result(objective_id):
    obj, error = _objective(objective_id, writable=True)
    if error:
        return error
    data = _body()
    title = str(data.get("title", "")).strip()
    direction = str(data.get("direction", "increase"))
    metric_type = str(data.get("metric_type", "numeric"))
    if not title or len(title) > 180 or direction not in {"increase", "decrease"} or metric_type not in {"numeric", "percentage", "currency", "boolean"}:
        return api_error("A valid title, metric_type, and direction are required.", 400)
    try:
        start = _decimal(data.get("start_value", 0), "start_value")
        current = _decimal(data.get("current_value", start), "current_value")
        target = _decimal(data.get("target_value", 100), "target_value")
        owner_id = _person(data["owner_id"]) if data.get("owner_id") else obj.owner_id
    except (ValueError, LookupError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    row = KeyResult(objective_id=obj.id, title=title, metric_type=metric_type, unit=str(data.get("unit", ""))[:32],
                    start_value=start, current_value=current, target_value=target, direction=direction,
                    owner_id=owner_id, status="active")
    db.session.add(row)
    db.session.commit()
    log_audit("objective.key_result.created", "key_result", row.id, {"objective_id": obj.id})
    return api_success(row.to_dict(), "Key result created.", 201)


@objectives_bp.patch("/<int:objective_id>/key-results/<int:key_result_id>")
@login_required
@active_account_required
def update_key_result(objective_id, key_result_id):
    obj, error = _objective(objective_id, writable=True)
    if error:
        return error
    row = KeyResult.query.filter_by(id=key_result_id, objective_id=obj.id).first()
    if not row:
        return api_error("Key result not found.", 404)
    data = _body()
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 180:
            return api_error("title must contain 1–180 characters.", 400)
        row.title = title
    if "status" in data:
        if data["status"] not in {"active", "completed", "cancelled"}:
            return api_error("Unsupported key-result status.", 400)
        row.status = data["status"]
    if "target_value" in data:
        try:
            row.target_value = _decimal(data["target_value"], "target_value")
        except ValueError as exc:
            return api_error(str(exc), 400)
    if "current_value" in data:
        try:
            value = _decimal(data["current_value"], "current_value")
        except ValueError as exc:
            return api_error(str(exc), 400)
        previous = row.current_value
        note = str(data.get("note", "")).strip()[:1000]
        db.session.add(KeyResultUpdate(key_result_id=row.id, previous_value=previous,
                                       new_value=value, note=note, updated_by=current_user.id))
        row.current_value = value
    db.session.commit()
    log_audit("objective.key_result.updated", "key_result", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Key result updated.")


@objectives_bp.get("/<int:objective_id>/key-results/<int:key_result_id>/history")
@login_required
@active_account_required
def key_result_history(objective_id, key_result_id):
    obj, error = _objective(objective_id)
    if error:
        return error
    row = KeyResult.query.filter_by(id=key_result_id, objective_id=obj.id).first()
    if not row:
        return api_error("Key result not found.", 404)
    history = KeyResultUpdate.query.filter_by(key_result_id=row.id).order_by(KeyResultUpdate.created_at.desc()).limit(200).all()
    return api_success({"key_result": row.to_dict(), "history": [item.to_dict() for item in history]})


@objectives_bp.get("/summary/portfolio")
@login_required
@active_account_required
def objective_portfolio_summary():
    rows = _query().all()
    counts = {state: 0 for state in STATUSES}
    for row in rows:
        counts[row.status] += 1
    active = [row for row in rows if row.status in {"active", "at_risk"}]
    overdue = sum(1 for row in active if row.due_date and row.due_date < date.today())
    return api_success({"total": len(rows), "by_status": counts, "overdue": overdue,
                        "average_progress": round(sum(row.progress for row in rows) / len(rows), 2) if rows else 0,
                        "average_confidence": round(sum(row.confidence for row in rows) / len(rows), 2) if rows else 0})
