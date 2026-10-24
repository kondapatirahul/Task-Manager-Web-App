"""Organization-scoped project risk register and mitigation action APIs."""
from datetime import date, datetime
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import User, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.domain_models import RiskRecord, RiskAction
from app.enterprise_models import Project
from app.routes.utils import active_account_required, api_error, api_success, log_audit

risks_bp = Blueprint("risks", __name__, url_prefix="/api/risks")
STATUSES = {"identified", "assessing", "mitigating", "accepted", "closed"}
STRATEGIES = {"mitigate", "avoid", "transfer", "accept"}
CATEGORIES = {"delivery", "financial", "security", "compliance", "people", "technical", "vendor", "operational", "other"}


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _admin():
    return current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)


def _date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{field} must use YYYY-MM-DD format.")


def _base_query():
    query = RiskRecord.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    if not _admin():
        query = query.filter(or_(RiskRecord.owner_id == current_user.id, RiskRecord.created_by == current_user.id))
    if request.args.get("status") in STATUSES:
        query = query.filter_by(status=request.args["status"])
    if request.args.get("severity") in {"low", "medium", "high", "critical"}:
        # Score is the product of two bounded columns. SQL CASE avoids fetching every row.
        from sqlalchemy import case
        score = RiskRecord.probability * RiskRecord.impact
        severity = request.args["severity"]
        bounds = {"low": (1, 7), "medium": (8, 14), "high": (15, 19), "critical": (20, 25)}[severity]
        query = query.filter(score >= bounds[0], score <= bounds[1])
    return query


def _next_key():
    prefix = f"R-{date.today():%y%m}-"
    rows = RiskRecord.query.filter_by(organization_id=current_user.organization_id).filter(RiskRecord.key.like(prefix + "%")).all()
    nums = []
    for row in rows:
        try:
            nums.append(int(row.key.rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return prefix + f"{max(nums, default=0) + 1:04d}"


def _validate_person(user_id):
    if user_id in (None, ""):
        return None
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("owner_id must be an integer.")
    user = db.session.get(User, user_id)
    if not user or (not current_user.has_role(ROLE_SUPER_ADMIN) and user.organization_id != current_user.organization_id):
        raise LookupError("Owner not found in this organization.")
    return user.id


@risks_bp.get("")
@login_required
@active_account_required
def list_risks():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = _base_query()
    q = request.args.get("q", "").strip()[:100]
    if q:
        term = f"%{q}%"
        query = query.filter(or_(RiskRecord.key.ilike(term), RiskRecord.title.ilike(term), RiskRecord.description.ilike(term)))
    total = query.count()
    rows = query.order_by((RiskRecord.probability * RiskRecord.impact).desc(), RiskRecord.updated_at.desc()).offset((page - 1) * size).limit(size).all()
    return api_success({"items": [r.to_dict() for r in rows], "page": page, "page_size": size,
                        "total": total, "pages": (total + size - 1) // size})


@risks_bp.post("")
@login_required
@active_account_required
def create_risk():
    data = _body()
    title = str(data.get("title", "")).strip()
    category = str(data.get("category", "delivery"))
    strategy = str(data.get("response_strategy", "mitigate"))
    if not title or len(title) > 180:
        return api_error("title is required and must be at most 180 characters.", 400)
    if category not in CATEGORIES or strategy not in STRATEGIES:
        return api_error("Unsupported category or response strategy.", 400)
    try:
        probability, impact = int(data.get("probability", 3)), int(data.get("impact", 3))
        if not 1 <= probability <= 5 or not 1 <= impact <= 5:
            raise ValueError
        owner_id = _validate_person(data.get("owner_id"))
        due = _date(data.get("due_date"), "due_date")
    except ValueError:
        return api_error("probability and impact must be integers from 1 to 5; due_date must be valid.", 400)
    except LookupError as exc:
        return api_error(str(exc), 404)
    project_id = data.get("project_id")
    if project_id:
        project = db.session.get(Project, project_id)
        if not project or (not current_user.has_role(ROLE_SUPER_ADMIN) and project.organization_id != current_user.organization_id):
            return api_error("Project not found in this organization.", 404)
    row = RiskRecord(organization_id=current_user.organization_id, project_id=project_id, owner_id=owner_id,
        created_by=current_user.id, key=_next_key(), title=title, description=str(data.get("description", ""))[:12000],
        category=category, probability=probability, impact=impact, response_strategy=strategy,
        mitigation_plan=str(data.get("mitigation_plan", ""))[:12000], due_date=due)
    db.session.add(row)
    db.session.commit()
    log_audit("risk.created", "risk", row.id, {"key": row.key, "score": row.score})
    return api_success(row.to_dict(), "Risk created.", 201)


@risks_bp.get("/<int:risk_id>")
@login_required
@active_account_required
def get_risk(risk_id):
    row = _base_query().filter_by(id=risk_id).first()
    if not row:
        return api_error("Risk not found.", 404)
    actions = RiskAction.query.filter_by(risk_id=row.id).order_by(RiskAction.created_at.desc()).all()
    return api_success({**row.to_dict(), "actions": [a.to_dict() for a in actions]})


@risks_bp.patch("/<int:risk_id>")
@login_required
@active_account_required
def update_risk(risk_id):
    row = RiskRecord.query.filter_by(id=risk_id).first()
    if not row or (not current_user.has_role(ROLE_SUPER_ADMIN) and row.organization_id != current_user.organization_id):
        return api_error("Risk not found.", 404)
    if not _admin() and row.owner_id != current_user.id and row.created_by != current_user.id:
        return api_error("You cannot update this risk.", 403)
    data = _body()
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 180:
            return api_error("title must contain 1–180 characters.", 400)
        row.title = title
    for field, maximum in (("description", 12000), ("mitigation_plan", 12000)):
        if field in data:
            setattr(row, field, str(data[field])[:maximum])
    if "category" in data:
        if data["category"] not in CATEGORIES:
            return api_error("Unsupported category.", 400)
        row.category = data["category"]
    if "response_strategy" in data:
        if data["response_strategy"] not in STRATEGIES:
            return api_error("Unsupported response strategy.", 400)
        row.response_strategy = data["response_strategy"]
    if "status" in data:
        if data["status"] not in STATUSES:
            return api_error("Unsupported risk status.", 400)
        row.status = data["status"]
        row.closed_at = datetime.utcnow() if row.status == "closed" else None
    try:
        for field in ("probability", "impact"):
            if field in data:
                value = int(data[field])
                if value < 1 or value > 5:
                    raise ValueError(f"{field} must be from 1 to 5.")
                setattr(row, field, value)
        if "owner_id" in data:
            row.owner_id = _validate_person(data["owner_id"])
        if "due_date" in data:
            row.due_date = _date(data["due_date"], "due_date")
    except (ValueError, LookupError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    db.session.commit()
    log_audit("risk.updated", "risk", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Risk updated.")


@risks_bp.post("/<int:risk_id>/actions")
@login_required
@active_account_required
def create_risk_action(risk_id):
    risk = RiskRecord.query.filter_by(id=risk_id).first()
    if not risk or (not current_user.has_role(ROLE_SUPER_ADMIN) and risk.organization_id != current_user.organization_id):
        return api_error("Risk not found.", 404)
    if not _admin() and risk.owner_id != current_user.id and risk.created_by != current_user.id:
        return api_error("You cannot manage mitigation actions for this risk.", 403)
    data = _body()
    title = str(data.get("title", "")).strip()
    if not title or len(title) > 180:
        return api_error("title is required and must be at most 180 characters.", 400)
    try:
        owner = _validate_person(data.get("owner_id"))
        due = _date(data.get("due_date"), "due_date")
    except (ValueError, LookupError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    action = RiskAction(risk_id=risk.id, title=title, owner_id=owner, due_date=due,
                        created_by=current_user.id)
    db.session.add(action)
    db.session.commit()
    log_audit("risk.action.created", "risk_action", action.id, {"risk_id": risk.id})
    return api_success(action.to_dict(), "Mitigation action created.", 201)


@risks_bp.patch("/<int:risk_id>/actions/<int:action_id>")
@login_required
@active_account_required
def update_risk_action(risk_id, action_id):
    risk = RiskRecord.query.filter_by(id=risk_id).first()
    action = RiskAction.query.filter_by(id=action_id, risk_id=risk_id).first()
    if not risk or not action or (not current_user.has_role(ROLE_SUPER_ADMIN) and risk.organization_id != current_user.organization_id):
        return api_error("Risk action not found.", 404)
    if not _admin() and risk.owner_id != current_user.id and risk.created_by != current_user.id:
        return api_error("You cannot update this mitigation action.", 403)
    data = _body()
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 180:
            return api_error("title must contain 1–180 characters.", 400)
        action.title = title
    if "status" in data:
        if data["status"] not in {"open", "in_progress", "completed", "cancelled"}:
            return api_error("Unsupported action status.", 400)
        action.status = data["status"]
        action.completed_at = datetime.utcnow() if action.status == "completed" else None
    if "completion_note" in data:
        action.completion_note = str(data["completion_note"])[:1000]
    if "due_date" in data:
        try:
            action.due_date = _date(data["due_date"], "due_date")
        except ValueError as exc:
            return api_error(str(exc), 400)
    db.session.commit()
    log_audit("risk.action.updated", "risk_action", action.id, {"fields": sorted(data)})
    return api_success(action.to_dict(), "Mitigation action updated.")


@risks_bp.get("/summary/heatmap")
@login_required
@active_account_required
def risk_heatmap():
    rows = _base_query().filter(RiskRecord.status != "closed").all()
    matrix = {str(p): {str(i): 0 for i in range(1, 6)} for p in range(1, 6)}
    severity_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for row in rows:
        matrix[str(row.probability)][str(row.impact)] += 1
        severity_counts[row.severity] += 1
    overdue = sum(1 for row in rows if row.due_date and row.due_date < date.today())
    return api_success({"matrix": matrix, "severity_counts": severity_counts,
                        "open_risks": len(rows), "overdue": overdue,
                        "average_score": round(sum(r.score for r in rows) / len(rows), 2) if rows else 0})
