"""Compliance policy lifecycle, version acknowledgements, and evidence register."""
from datetime import date, datetime
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import ROLE_ADMIN, ROLE_SUPER_ADMIN, User
from app.domain_models import CompliancePolicy, PolicyAcknowledgement, ComplianceEvidence
from app.routes.utils import active_account_required, api_error, api_success, log_audit

compliance_bp = Blueprint("compliance", __name__, url_prefix="/api/compliance")
POLICY_STATUSES = {"draft", "published", "retired"}
EVIDENCE_STATUSES = {"current", "expired", "superseded", "under_review"}
EVIDENCE_TYPES = {"document", "screenshot", "report", "approval", "log", "certificate", "other"}


def _admin():
    return current_user.has_role(ROLE_ADMIN, ROLE_SUPER_ADMIN)


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _policy_query():
    query = CompliancePolicy.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    if not _admin():
        query = query.filter_by(status="published")
    status = request.args.get("status")
    if _admin() and status in POLICY_STATUSES:
        query = query.filter_by(status=status)
    term = request.args.get("q", "").strip()[:100]
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(CompliancePolicy.policy_key.ilike(pattern), CompliancePolicy.title.ilike(pattern),
                                 CompliancePolicy.summary.ilike(pattern), CompliancePolicy.body.ilike(pattern)))
    return query


def _policy(policy_id):
    query = CompliancePolicy.query.filter_by(id=policy_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    row = query.first()
    if row and row.status != "published" and not _admin():
        return None
    return row


def _parse_date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{field} must use YYYY-MM-DD format.")


@compliance_bp.get("/policies")
@login_required
@active_account_required
def list_policies():
    rows = _policy_query().order_by(CompliancePolicy.category.asc(), CompliancePolicy.title.asc()).limit(200).all()
    items = []
    for row in rows:
        payload = row.to_dict()
        payload["acknowledged"] = PolicyAcknowledgement.query.filter_by(policy_id=row.id, user_id=current_user.id,
                                                                         policy_version=row.version).first() is not None
        items.append(payload)
    return api_success({"items": items, "total": len(items)})


@compliance_bp.post("/policies")
@login_required
@active_account_required
def create_policy():
    if not _admin():
        return api_error("Administrator permission required to create policies.", 403)
    if not current_user.organization_id:
        return api_error("An organization must be assigned before creating policies.", 409)
    data = _body()
    key = str(data.get("policy_key", "")).strip().upper()
    title, body = str(data.get("title", "")).strip(), str(data.get("body", "")).strip()
    if not key or len(key) > 48 or not title or len(title) > 180 or not body or len(body) > 40000:
        return api_error("policy_key, title, and body are required and must fit the documented limits.", 400)
    try:
        effective = _parse_date(data.get("effective_date"), "effective_date")
        review = _parse_date(data.get("review_date"), "review_date")
        if effective and review and review < effective:
            raise ValueError("review_date cannot be before effective_date.")
    except ValueError as exc:
        return api_error(str(exc), 400)
    if CompliancePolicy.query.filter_by(organization_id=current_user.organization_id, policy_key=key, version=1).first():
        return api_error("policy_key already exists; create a new version instead.", 409)
    status = str(data.get("status", "draft"))
    if status not in POLICY_STATUSES:
        return api_error("Unsupported policy status.", 400)
    row = CompliancePolicy(organization_id=current_user.organization_id, policy_key=key, title=title,
        summary=str(data.get("summary", ""))[:600], body=body,
        category=str(data.get("category", "general")).strip()[:64] or "general", version=1, status=status,
        effective_date=effective, review_date=review, requires_acknowledgement=bool(data.get("requires_acknowledgement", True)),
        owner_id=current_user.id, created_by=current_user.id,
        published_at=datetime.utcnow() if status == "published" else None)
    db.session.add(row)
    db.session.commit()
    log_audit("compliance.policy.created", "compliance_policy", row.id, {"policy_key": key, "version": 1})
    return api_success(row.to_dict(), "Policy created.", 201)


@compliance_bp.patch("/policies/<int:policy_id>")
@login_required
@active_account_required
def update_policy(policy_id):
    if not _admin():
        return api_error("Administrator permission required to update policies.", 403)
    row = _policy(policy_id)
    if not row:
        return api_error("Policy not found.", 404)
    data = _body()
    if "status" in data:
        if data["status"] not in POLICY_STATUSES:
            return api_error("Unsupported policy status.", 400)
        row.status = data["status"]
        row.published_at = (row.published_at or datetime.utcnow()) if row.status == "published" else None
    for field, maximum in (("title", 180), ("summary", 600), ("category", 64), ("body", 40000)):
        if field in data:
            value = str(data[field]).strip()
            if field in {"title", "body"} and not value:
                return api_error(f"{field} cannot be empty.", 400)
            if len(value) > maximum:
                return api_error(f"{field} exceeds {maximum} characters.", 400)
            setattr(row, field, value)
    try:
        if "effective_date" in data:
            row.effective_date = _parse_date(data["effective_date"], "effective_date")
        if "review_date" in data:
            row.review_date = _parse_date(data["review_date"], "review_date")
        if row.effective_date and row.review_date and row.review_date < row.effective_date:
            raise ValueError("review_date cannot be before effective_date.")
    except ValueError as exc:
        return api_error(str(exc), 400)
    if "requires_acknowledgement" in data:
        row.requires_acknowledgement = bool(data["requires_acknowledgement"])
    db.session.commit()
    log_audit("compliance.policy.updated", "compliance_policy", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Policy updated.")


@compliance_bp.post("/policies/<int:policy_id>/new-version")
@login_required
@active_account_required
def new_policy_version(policy_id):
    if not _admin():
        return api_error("Administrator permission required to version policies.", 403)
    source = _policy(policy_id)
    if not source:
        return api_error("Policy not found.", 404)
    if source.status != "published":
        return api_error("Only a published policy can be versioned.", 409)
    version = CompliancePolicy(organization_id=source.organization_id, policy_key=source.policy_key,
        title=source.title, summary=source.summary, body=source.body, category=source.category,
        version=source.version + 1, status="draft", effective_date=source.effective_date,
        review_date=source.review_date, requires_acknowledgement=source.requires_acknowledgement,
        owner_id=source.owner_id, created_by=current_user.id)
    source.status = "retired"
    db.session.add(version)
    db.session.commit()
    log_audit("compliance.policy.versioned", "compliance_policy", version.id,
              {"source_policy_id": source.id, "version": version.version})
    return api_success(version.to_dict(), "New draft policy version created.", 201)


@compliance_bp.post("/policies/<int:policy_id>/acknowledge")
@login_required
@active_account_required
def acknowledge_policy(policy_id):
    row = _policy(policy_id)
    if not row or row.status != "published":
        return api_error("Published policy not found.", 404)
    if not row.requires_acknowledgement:
        return api_error("This policy does not require acknowledgement.", 409)
    existing = PolicyAcknowledgement.query.filter_by(policy_id=row.id, user_id=current_user.id,
                                                       policy_version=row.version).first()
    if existing:
        return api_success(existing.to_dict(), "Policy was already acknowledged.")
    acknowledgement = PolicyAcknowledgement(policy_id=row.id, user_id=current_user.id,
        policy_version=row.version,
        acknowledgement_text=str(_body().get("acknowledgement_text", "I have read and understood this policy."))[:500],
        ip_address=(request.remote_addr or "")[:64])
    db.session.add(acknowledgement)
    db.session.commit()
    log_audit("compliance.policy.acknowledged", "compliance_policy", row.id, {"version": row.version})
    return api_success(acknowledgement.to_dict(), "Policy acknowledgement recorded.", 201)


@compliance_bp.get("/policies/<int:policy_id>/acknowledgements")
@login_required
@active_account_required
def list_acknowledgements(policy_id):
    if not _admin():
        return api_error("Administrator permission required to view acknowledgement records.", 403)
    row = _policy(policy_id)
    if not row:
        return api_error("Policy not found.", 404)
    rows = PolicyAcknowledgement.query.filter_by(policy_id=row.id, policy_version=row.version).order_by(PolicyAcknowledgement.acknowledged_at.desc()).all()
    return api_success({"items": [item.to_dict() for item in rows], "total": len(rows), "policy_version": row.version})


@compliance_bp.get("/evidence")
@login_required
@active_account_required
def list_evidence():
    query = ComplianceEvidence.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    status = request.args.get("status")
    if status in EVIDENCE_STATUSES:
        query = query.filter_by(status=status)
    rows = query.order_by(ComplianceEvidence.collected_on.desc()).limit(200).all()
    return api_success({"items": [row.to_dict() for row in rows], "total": len(rows)})


@compliance_bp.post("/evidence")
@login_required
@active_account_required
def create_evidence():
    if not _admin():
        return api_error("Administrator permission required to register compliance evidence.", 403)
    if not current_user.organization_id:
        return api_error("An organization must be assigned before registering evidence.", 409)
    data = _body()
    title = str(data.get("title", "")).strip()
    evidence_type = str(data.get("evidence_type", "document"))
    if not title or len(title) > 180 or evidence_type not in EVIDENCE_TYPES:
        return api_error("Valid title and evidence_type are required.", 400)
    try:
        collected = _parse_date(data.get("collected_on") or date.today().isoformat(), "collected_on")
        expires = _parse_date(data.get("expires_on"), "expires_on")
        if expires and expires < collected:
            raise ValueError("expires_on cannot be before collected_on.")
    except ValueError as exc:
        return api_error(str(exc), 400)
    policy_id = data.get("policy_id")
    if policy_id not in (None, ""):
        try:
            policy_id = int(policy_id)
        except (TypeError, ValueError):
            return api_error("policy_id must be an integer.", 400)
        policy = _policy(policy_id)
        if not policy:
            return api_error("Policy not found.", 404)
    else:
        policy_id = None
    row = ComplianceEvidence(organization_id=current_user.organization_id, policy_id=policy_id,
        title=title, evidence_type=evidence_type, reference_uri=str(data.get("reference_uri", ""))[:1000],
        description=str(data.get("description", ""))[:3000], collected_on=collected, expires_on=expires,
        status=str(data.get("status", "current")), uploaded_by=current_user.id)
    if row.status not in EVIDENCE_STATUSES:
        return api_error("Unsupported evidence status.", 400)
    db.session.add(row)
    db.session.commit()
    log_audit("compliance.evidence.created", "compliance_evidence", row.id, {"policy_id": policy_id})
    return api_success(row.to_dict(), "Compliance evidence registered.", 201)


@compliance_bp.get("/summary")
@login_required
@active_account_required
def compliance_summary():
    policies = CompliancePolicy.query
    evidence = ComplianceEvidence.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        policies = policies.filter_by(organization_id=current_user.organization_id)
        evidence = evidence.filter_by(organization_id=current_user.organization_id)
    policy_rows = policies.all()
    evidence_rows = evidence.all()
    published = [row for row in policy_rows if row.status == "published"]
    pending_ack = 0
    for row in published:
        if row.requires_acknowledgement:
            acknowledged = PolicyAcknowledgement.query.filter_by(policy_id=row.id, policy_version=row.version).count()
            employees = User.query.filter_by(organization_id=row.organization_id, account_active=True).count()
            pending_ack += max(0, employees - acknowledged)
    today = date.today()
    overdue_reviews = sum(row.review_date is not None and row.review_date < today for row in published)
    expired_evidence = sum(row.expires_on is not None and row.expires_on < today for row in evidence_rows)
    return api_success({"policies": len(policy_rows), "published_policies": len(published),
        "draft_policies": sum(row.status == "draft" for row in policy_rows), "pending_acknowledgements": pending_ack,
        "overdue_policy_reviews": overdue_reviews, "evidence_records": len(evidence_rows),
        "expired_evidence": expired_evidence})
