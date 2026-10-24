"""Enterprise asset inventory, assignment lifecycle, and maintenance tracking."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import User, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.domain_models import AssetRecord, AssetAssignment, AssetMaintenance
from app.routes.utils import active_account_required, api_error, api_success, log_audit

assets_bp = Blueprint("assets", __name__, url_prefix="/api/assets")
ASSET_STATUSES = {"available", "assigned", "maintenance", "retired", "lost"}
ASSET_CATEGORIES = {"laptop", "desktop", "mobile", "equipment", "license", "furniture", "vehicle", "other"}
MAINTENANCE_STATUSES = {"open", "in_progress", "waiting_parts", "completed", "cancelled"}


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _admin():
    return current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)


def _date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{field} must use YYYY-MM-DD format.")


def _money(value, field="cost", required=False):
    if value in (None, "") and not required:
        return None
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a valid monetary amount.")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be non-negative.")
    return result


def _asset_query():
    query = AssetRecord.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    status = request.args.get("status")
    if status in ASSET_STATUSES:
        query = query.filter_by(status=status)
    category = request.args.get("category")
    if category in ASSET_CATEGORIES:
        query = query.filter_by(category=category)
    q = request.args.get("q", "").strip()[:100]
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(AssetRecord.asset_tag.ilike(pattern), AssetRecord.name.ilike(pattern),
                                 AssetRecord.serial_number.ilike(pattern), AssetRecord.vendor.ilike(pattern)))
    return query


def _asset_or_404(asset_id):
    query = AssetRecord.query.filter_by(id=asset_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    return query.first()


def _user_in_org(user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("user_id must be an integer.")
    user = db.session.get(User, user_id)
    if not user or (not current_user.has_role(ROLE_SUPER_ADMIN) and user.organization_id != current_user.organization_id):
        raise LookupError("Employee not found in this organization.")
    return user


@assets_bp.get("")
@login_required
@active_account_required
def list_assets():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = _asset_query()
    total = query.count()
    rows = query.order_by(AssetRecord.updated_at.desc()).offset((page - 1) * size).limit(size).all()
    return api_success({"items": [a.to_dict() for a in rows], "page": page, "page_size": size,
                        "total": total, "pages": (total + size - 1) // size})


@assets_bp.post("")
@login_required
@active_account_required
def create_asset():
    if not _admin():
        return api_error("Administrator permission required to register assets.", 403)
    data = _body()
    tag = str(data.get("asset_tag", "")).strip().upper()
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "equipment"))
    if not tag or len(tag) > 64 or not name or len(name) > 180 or category not in ASSET_CATEGORIES:
        return api_error("Valid asset_tag, name, and category are required.", 400)
    if AssetRecord.query.filter_by(organization_id=current_user.organization_id, asset_tag=tag).first():
        return api_error("asset_tag already exists in this organization.", 409)
    try:
        purchase_date = _date(data.get("purchase_date"), "purchase_date")
        warranty = _date(data.get("warranty_until"), "warranty_until")
        cost = _money(data.get("purchase_cost"), "purchase_cost")
    except ValueError as exc:
        return api_error(str(exc), 400)
    row = AssetRecord(organization_id=current_user.organization_id, asset_tag=tag, name=name, category=category,
        serial_number=str(data.get("serial_number", "")).strip()[:120], purchase_date=purchase_date,
        purchase_cost=cost, currency=str(data.get("currency", "INR")).upper()[:3],
        status="available", location=str(data.get("location", "")).strip()[:180],
        vendor=str(data.get("vendor", "")).strip()[:180], warranty_until=warranty,
        notes=str(data.get("notes", ""))[:12000], created_by=current_user.id)
    db.session.add(row)
    db.session.commit()
    log_audit("asset.created", "asset", row.id, {"asset_tag": tag})
    return api_success(row.to_dict(), "Asset registered.", 201)


@assets_bp.get("/<int:asset_id>")
@login_required
@active_account_required
def get_asset(asset_id):
    row = _asset_or_404(asset_id)
    if not row:
        return api_error("Asset not found.", 404)
    assignment_rows = AssetAssignment.query.filter_by(asset_id=row.id).order_by(AssetAssignment.assigned_at.desc()).limit(50).all()
    maintenance_rows = AssetMaintenance.query.filter_by(asset_id=row.id).order_by(AssetMaintenance.created_at.desc()).limit(50).all()
    return api_success({**row.to_dict(), "assignments": [x.to_dict() for x in assignment_rows],
                        "maintenance": [x.to_dict() for x in maintenance_rows]})


@assets_bp.patch("/<int:asset_id>")
@login_required
@active_account_required
def update_asset(asset_id):
    if not _admin():
        return api_error("Administrator permission required.", 403)
    row = _asset_or_404(asset_id)
    if not row:
        return api_error("Asset not found.", 404)
    data = _body()
    for field, maximum in (("name", 180), ("serial_number", 120), ("location", 180), ("vendor", 180), ("notes", 12000)):
        if field in data:
            value = str(data[field]).strip()
            if field == "name" and not value:
                return api_error("name cannot be empty.", 400)
            setattr(row, field, value[:maximum])
    if "category" in data:
        if data["category"] not in ASSET_CATEGORIES:
            return api_error("Unsupported asset category.", 400)
        row.category = data["category"]
    if "status" in data:
        if data["status"] not in ASSET_STATUSES:
            return api_error("Unsupported asset status.", 400)
        if data["status"] == "available" and AssetAssignment.query.filter_by(asset_id=row.id, returned_at=None).first():
            return api_error("Return the active assignment before marking the asset available.", 409)
        row.status = data["status"]
    try:
        if "purchase_date" in data:
            row.purchase_date = _date(data["purchase_date"], "purchase_date")
        if "warranty_until" in data:
            row.warranty_until = _date(data["warranty_until"], "warranty_until")
        if "purchase_cost" in data:
            row.purchase_cost = _money(data["purchase_cost"], "purchase_cost")
    except ValueError as exc:
        return api_error(str(exc), 400)
    db.session.commit()
    log_audit("asset.updated", "asset", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Asset updated.")


@assets_bp.post("/<int:asset_id>/assignments")
@login_required
@active_account_required
def assign_asset(asset_id):
    if not _admin():
        return api_error("Administrator permission required to assign assets.", 403)
    asset = _asset_or_404(asset_id)
    if not asset:
        return api_error("Asset not found.", 404)
    if asset.status != "available":
        return api_error("Only available assets can be assigned.", 409)
    data = _body()
    try:
        user = _user_in_org(data.get("user_id"))
    except (ValueError, LookupError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    assignment = AssetAssignment(asset_id=asset.id, user_id=user.id, assigned_by=current_user.id,
        condition_out=str(data.get("condition_out", ""))[:500], notes=str(data.get("notes", ""))[:1000])
    asset.status = "assigned"
    db.session.add(assignment)
    db.session.commit()
    log_audit("asset.assigned", "asset_assignment", assignment.id, {"asset_id": asset.id, "user_id": user.id})
    return api_success(assignment.to_dict(), "Asset assigned.", 201)


@assets_bp.post("/<int:asset_id>/return")
@login_required
@active_account_required
def return_asset(asset_id):
    if not _admin():
        return api_error("Administrator permission required to process returns.", 403)
    asset = _asset_or_404(asset_id)
    if not asset:
        return api_error("Asset not found.", 404)
    assignment = AssetAssignment.query.filter_by(asset_id=asset.id, returned_at=None).order_by(AssetAssignment.assigned_at.desc()).first()
    if not assignment:
        return api_error("No active assignment exists for this asset.", 409)
    data = _body()
    assignment.returned_at = datetime.utcnow()
    assignment.condition_in = str(data.get("condition_in", ""))[:500]
    assignment.notes = (assignment.notes + "\n" + str(data.get("notes", "")).strip()).strip()[:1000]
    asset.status = "available"
    db.session.commit()
    log_audit("asset.returned", "asset_assignment", assignment.id, {"asset_id": asset.id})
    return api_success({"assignment": assignment.to_dict(), "asset": asset.to_dict()}, "Asset returned.")


@assets_bp.get("/<int:asset_id>/maintenance")
@login_required
@active_account_required
def list_maintenance(asset_id):
    asset = _asset_or_404(asset_id)
    if not asset:
        return api_error("Asset not found.", 404)
    rows = AssetMaintenance.query.filter_by(asset_id=asset.id).order_by(AssetMaintenance.created_at.desc()).all()
    return api_success([row.to_dict() for row in rows])


@assets_bp.post("/<int:asset_id>/maintenance")
@login_required
@active_account_required
def create_maintenance(asset_id):
    if not _admin():
        return api_error("Administrator permission required.", 403)
    asset = _asset_or_404(asset_id)
    if not asset:
        return api_error("Asset not found.", 404)
    data = _body()
    title = str(data.get("title", "")).strip()
    priority = str(data.get("priority", "normal"))
    if not title or len(title) > 180 or priority not in {"low", "normal", "high", "urgent"}:
        return api_error("Valid title and priority are required.", 400)
    try:
        due = _date(data.get("due_date"), "due_date")
        cost = _money(data.get("cost", 0), "cost", required=True)
        assigned = _user_in_org(data["assigned_to"]).id if data.get("assigned_to") else None
    except (ValueError, LookupError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    row = AssetMaintenance(asset_id=asset.id, requested_by=current_user.id, assigned_to=assigned,
        title=title, description=str(data.get("description", ""))[:12000], priority=priority, cost=cost, due_date=due)
    asset.status = "maintenance"
    db.session.add(row)
    db.session.commit()
    log_audit("asset.maintenance.created", "asset_maintenance", row.id, {"asset_id": asset.id})
    return api_success(row.to_dict(), "Maintenance request created.", 201)


@assets_bp.patch("/<int:asset_id>/maintenance/<int:maintenance_id>")
@login_required
@active_account_required
def update_maintenance(asset_id, maintenance_id):
    if not _admin():
        return api_error("Administrator permission required.", 403)
    asset = _asset_or_404(asset_id)
    row = AssetMaintenance.query.filter_by(id=maintenance_id, asset_id=asset_id).first()
    if not asset or not row:
        return api_error("Maintenance request not found.", 404)
    data = _body()
    if "status" in data:
        if data["status"] not in MAINTENANCE_STATUSES:
            return api_error("Unsupported maintenance status.", 400)
        row.status = data["status"]
        row.completed_at = datetime.utcnow() if row.status == "completed" else None
        if row.status == "completed" and not AssetAssignment.query.filter_by(asset_id=asset.id, returned_at=None).first():
            asset.status = "available"
        elif row.status not in {"completed", "cancelled"}:
            asset.status = "maintenance"
    if "priority" in data:
        if data["priority"] not in {"low", "normal", "high", "urgent"}:
            return api_error("Unsupported priority.", 400)
        row.priority = data["priority"]
    if "description" in data:
        row.description = str(data["description"])[:12000]
    if "cost" in data:
        try:
            row.cost = _money(data["cost"], "cost", required=True)
        except ValueError as exc:
            return api_error(str(exc), 400)
    db.session.commit()
    log_audit("asset.maintenance.updated", "asset_maintenance", row.id, {"fields": sorted(data)})
    return api_success({"maintenance": row.to_dict(), "asset": asset.to_dict()}, "Maintenance request updated.")


@assets_bp.get("/summary/inventory")
@login_required
@active_account_required
def asset_inventory_summary():
    rows = _asset_query().all()
    status_counts = {status: 0 for status in ASSET_STATUSES}
    category_counts = {category: 0 for category in ASSET_CATEGORIES}
    total_value = Decimal("0.00")
    expiring = 0
    soon = date.today().toordinal() + 60
    for row in rows:
        status_counts[row.status] += 1
        category_counts[row.category] += 1
        total_value += Decimal(str(row.purchase_cost or 0))
        if row.warranty_until and date.today() <= row.warranty_until <= date.fromordinal(soon):
            expiring += 1
    return api_success({"total_assets": len(rows), "by_status": status_counts,
                        "by_category": category_counts, "purchase_value": str(total_value.quantize(Decimal("0.01"))),
                        "warranties_expiring_60_days": expiring})
