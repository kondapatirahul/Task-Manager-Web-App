"""Vendor directory and contract renewal management APIs."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_, false
from app import db
from app.models import ROLE_ADMIN, ROLE_SUPER_ADMIN, User
from app.domain_models import VendorRecord, VendorContract
from app.routes.utils import active_account_required, api_error, api_success, log_audit

vendors_bp = Blueprint("vendors", __name__, url_prefix="/api/vendors")
VENDOR_STATUSES = {"active", "pending", "suspended", "inactive"}
RISK_TIERS = {"low", "medium", "high", "critical"}
CONTRACT_STATUSES = {"draft", "active", "expired", "terminated", "renewed"}


def _admin():
    return current_user.has_role(ROLE_ADMIN, ROLE_SUPER_ADMIN)


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _vendor_query():
    query = VendorRecord.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    if request.args.get("status") in VENDOR_STATUSES:
        query = query.filter_by(status=request.args["status"])
    if request.args.get("risk_tier") in RISK_TIERS:
        query = query.filter_by(risk_tier=request.args["risk_tier"])
    term = request.args.get("q", "").strip()[:100]
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(VendorRecord.name.ilike(pattern), VendorRecord.vendor_code.ilike(pattern),
                                 VendorRecord.category.ilike(pattern), VendorRecord.contact_email.ilike(pattern)))
    return query


def _vendor(vendor_id):
    query = VendorRecord.query.filter_by(id=vendor_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    return query.first()


def _money(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("value must be a valid monetary amount.")
    if not amount.is_finite() or amount < 0:
        raise ValueError("value must be non-negative.")
    return amount


def _parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must use YYYY-MM-DD format.")


@vendors_bp.get("")
@login_required
@active_account_required
def list_vendors():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = _vendor_query()
    total = query.count()
    rows = query.order_by(VendorRecord.name.asc()).offset((page - 1) * size).limit(size).all()
    return api_success({"items": [row.to_dict() for row in rows], "page": page, "page_size": size,
                        "total": total, "pages": (total + size - 1) // size})


@vendors_bp.post("")
@login_required
@active_account_required
def create_vendor():
    if not _admin():
        return api_error("Administrator permission required to manage vendors.", 403)
    if not current_user.organization_id:
        return api_error("An organization must be assigned before creating vendors.", 409)
    data = _body()
    name = str(data.get("name", "")).strip()
    code = str(data.get("vendor_code", "")).strip().upper()
    risk = str(data.get("risk_tier", "medium"))
    if not name or len(name) > 180 or not code or len(code) > 32 or risk not in RISK_TIERS:
        return api_error("Valid name, vendor_code, and risk_tier are required.", 400)
    if VendorRecord.query.filter_by(organization_id=current_user.organization_id, vendor_code=code).first():
        return api_error("vendor_code already exists in this organization.", 409)
    if VendorRecord.query.filter_by(organization_id=current_user.organization_id, name=name).first():
        return api_error("A vendor with this name already exists in this organization.", 409)
    status = str(data.get("status", "pending"))
    if status not in VENDOR_STATUSES:
        return api_error("Unsupported vendor status.", 400)
    row = VendorRecord(organization_id=current_user.organization_id, vendor_code=code, name=name,
        category=str(data.get("category", "general")).strip()[:64] or "general",
        contact_name=str(data.get("contact_name", "")).strip()[:120],
        contact_email=str(data.get("contact_email", "")).strip()[:180],
        contact_phone=str(data.get("contact_phone", "")).strip()[:48],
        website=str(data.get("website", "")).strip()[:500], status=status, risk_tier=risk,
        payment_terms=str(data.get("payment_terms", "")).strip()[:120],
        tax_reference=str(data.get("tax_reference", "")).strip()[:100], notes=str(data.get("notes", ""))[:12000],
        created_by=current_user.id)
    db.session.add(row)
    db.session.commit()
    log_audit("vendor.created", "vendor", row.id, {"vendor_code": code})
    return api_success(row.to_dict(), "Vendor created.", 201)


@vendors_bp.get("/<int:vendor_id>")
@login_required
@active_account_required
def get_vendor(vendor_id):
    row = _vendor(vendor_id)
    if not row:
        return api_error("Vendor not found.", 404)
    contracts = VendorContract.query.filter_by(vendor_id=row.id).order_by(VendorContract.end_date.asc()).all()
    return api_success({**row.to_dict(), "contracts": [contract.to_dict() for contract in contracts]})


@vendors_bp.patch("/<int:vendor_id>")
@login_required
@active_account_required
def update_vendor(vendor_id):
    if not _admin():
        return api_error("Administrator permission required to manage vendors.", 403)
    row = _vendor(vendor_id)
    if not row:
        return api_error("Vendor not found.", 404)
    data = _body()
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 180:
            return api_error("name must contain 1–180 characters.", 400)
        duplicate = VendorRecord.query.filter(VendorRecord.organization_id == row.organization_id,
            VendorRecord.name == name, VendorRecord.id != row.id).first()
        if duplicate:
            return api_error("A vendor with this name already exists.", 409)
        row.name = name
    for field, maximum in (("category", 64), ("contact_name", 120), ("contact_email", 180),
                           ("contact_phone", 48), ("website", 500), ("payment_terms", 120),
                           ("tax_reference", 100), ("notes", 12000)):
        if field in data:
            setattr(row, field, str(data[field]).strip()[:maximum])
    if "status" in data:
        if data["status"] not in VENDOR_STATUSES:
            return api_error("Unsupported vendor status.", 400)
        row.status = data["status"]
    if "risk_tier" in data:
        if data["risk_tier"] not in RISK_TIERS:
            return api_error("Unsupported risk tier.", 400)
        row.risk_tier = data["risk_tier"]
    db.session.commit()
    log_audit("vendor.updated", "vendor", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Vendor updated.")


@vendors_bp.post("/<int:vendor_id>/contracts")
@login_required
@active_account_required
def create_contract(vendor_id):
    if not _admin():
        return api_error("Administrator permission required to manage vendor contracts.", 403)
    vendor = _vendor(vendor_id)
    if not vendor:
        return api_error("Vendor not found.", 404)
    data = _body()
    number = str(data.get("contract_number", "")).strip().upper()
    title = str(data.get("title", "")).strip()
    if not number or len(number) > 80 or not title or len(title) > 180:
        return api_error("contract_number and title are required.", 400)
    try:
        start, end = _parse_date(data.get("start_date"), "start_date"), _parse_date(data.get("end_date"), "end_date")
        value = _money(data.get("value", 0))
        notice_days = int(data.get("notice_days", 30))
        if end < start or not 0 <= notice_days <= 365:
            raise ValueError("end_date must be on or after start_date and notice_days must be from 0 to 365.")
    except (ValueError, TypeError) as exc:
        return api_error(str(exc), 400)
    if VendorContract.query.filter_by(organization_id=vendor.organization_id, contract_number=number).first():
        return api_error("contract_number already exists in this organization.", 409)
    owner_id = data.get("owner_id")
    if owner_id not in (None, ""):
        try:
            owner_id = int(owner_id)
        except (TypeError, ValueError):
            return api_error("owner_id must be an integer.", 400)
        owner = db.session.get(User, owner_id)
        if not owner or (not current_user.has_role(ROLE_SUPER_ADMIN) and owner.organization_id != vendor.organization_id):
            return api_error("Contract owner not found in this organization.", 404)
    else:
        owner_id = None
    status = str(data.get("status", "draft"))
    if status not in CONTRACT_STATUSES:
        return api_error("Unsupported contract status.", 400)
    contract = VendorContract(organization_id=vendor.organization_id, vendor_id=vendor.id,
        contract_number=number, title=title, start_date=start, end_date=end, value=value,
        currency=str(data.get("currency", "INR")).upper()[:3], auto_renew=bool(data.get("auto_renew", False)),
        notice_days=notice_days, owner_id=owner_id, status=status, notes=str(data.get("notes", ""))[:12000],
        created_by=current_user.id)
    db.session.add(contract)
    db.session.commit()
    log_audit("vendor_contract.created", "vendor_contract", contract.id, {"vendor_id": vendor.id, "status": status})
    return api_success(contract.to_dict(), "Vendor contract created.", 201)


@vendors_bp.patch("/contracts/<int:contract_id>")
@login_required
@active_account_required
def update_contract(contract_id):
    if not _admin():
        return api_error("Administrator permission required to manage vendor contracts.", 403)
    query = VendorContract.query.filter_by(id=contract_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    row = query.first()
    if not row:
        return api_error("Vendor contract not found.", 404)
    data = _body()
    if "status" in data:
        if data["status"] not in CONTRACT_STATUSES:
            return api_error("Unsupported contract status.", 400)
        row.status = data["status"]
    if "end_date" in data:
        try:
            row.end_date = _parse_date(data["end_date"], "end_date")
        except ValueError as exc:
            return api_error(str(exc), 400)
        if row.end_date < row.start_date:
            return api_error("end_date must be on or after start_date.", 400)
    if "value" in data:
        try:
            row.value = _money(data["value"])
        except ValueError as exc:
            return api_error(str(exc), 400)
    if "auto_renew" in data:
        row.auto_renew = bool(data["auto_renew"])
    if "notice_days" in data:
        try:
            days = int(data["notice_days"])
            if not 0 <= days <= 365:
                raise ValueError
            row.notice_days = days
        except (TypeError, ValueError):
            return api_error("notice_days must be from 0 to 365.", 400)
    if "notes" in data:
        row.notes = str(data["notes"])[:12000]
    db.session.commit()
    log_audit("vendor_contract.updated", "vendor_contract", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Vendor contract updated.")


@vendors_bp.get("/contracts/renewals")
@login_required
@active_account_required
def contract_renewals():
    try:
        horizon = max(0, min(int(request.args.get("days", 90)), 730))
    except ValueError:
        return api_error("days must be an integer from 0 to 730.", 400)
    query = VendorContract.query.filter(VendorContract.end_date <= date.today() + timedelta(days=horizon),
                                        VendorContract.status == "active")
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
    rows = query.order_by(VendorContract.end_date.asc()).all()
    return api_success({"items": [row.to_dict() for row in rows], "total": len(rows),
                        "horizon_days": horizon, "expired": sum(row.end_date < date.today() for row in rows)})


@vendors_bp.get("/summary")
@login_required
@active_account_required
def vendor_summary():
    query = VendorRecord.query
    contracts = VendorContract.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=current_user.organization_id)
        contracts = contracts.filter_by(organization_id=current_user.organization_id)
    vendors = query.all()
    contract_rows = contracts.all()
    today = date.today()
    return api_success({"vendors": len(vendors), "active_vendors": sum(v.status == "active" for v in vendors),
        "high_risk_vendors": sum(v.risk_tier in {"high", "critical"} for v in vendors),
        "contracts": len(contract_rows), "active_contracts": sum(c.status == "active" for c in contract_rows),
        "renewals_due_30_days": sum(c.status == "active" and today <= c.end_date <= today + timedelta(days=30) for c in contract_rows),
        "contract_value": str(sum((c.value for c in contract_rows if c.status == "active"), Decimal("0.00")))})
