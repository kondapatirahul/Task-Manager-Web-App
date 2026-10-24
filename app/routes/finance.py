"""Budget ledger, expense controls, purchase approvals, and financial summaries."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from app import db
from app.models import Task, ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_TEAM_LEAD
from app.domain_models import BudgetTransaction, ExpensePolicy, PurchaseRequest
from app.routes.utils import active_account_required, api_error, api_success, log_audit

finance_bp = Blueprint("finance", __name__, url_prefix="/api/finance")
MONEY = Decimal("0.01")
TRANSACTION_TYPES = {"expense", "credit", "adjustment"}
TRANSACTION_STATES = {"submitted", "approved", "rejected", "void"}
PURCHASE_STATES = {"pending", "approved", "rejected", "cancelled", "ordered", "received"}
CATEGORIES = {"travel", "equipment", "software", "training", "contractor", "operational", "other"}


def _body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _admin():
    return current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)


def _org_id():
    return current_user.organization_id


def _money(value, field="amount", allow_zero=False):
    try:
        result = Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a valid monetary amount.")
    if not result.is_finite() or result < 0 or (not allow_zero and result <= 0):
        raise ValueError(f"{field} must be {'non-negative' if allow_zero else 'greater than zero'}.")
    if result > Decimal("999999999999.99"):
        raise ValueError(f"{field} exceeds the supported limit.")
    return result


def _date(value, field="transaction_date", required=True):
    if not value and not required:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must use YYYY-MM-DD format.")


def _task_for_org(task_id):
    if task_id in (None, ""):
        return None
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        raise ValueError("task_id must be an integer.")
    task = db.session.get(Task, task_id)
    if not task:
        raise LookupError("Task not found.")
    if not current_user.has_role(ROLE_SUPER_ADMIN) and task.organization_id != _org_id():
        raise PermissionError("Task belongs to another organization.")
    return task


def _transaction_query():
    query = BudgetTransaction.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    if not _admin():
        query = query.filter(or_(BudgetTransaction.created_by == current_user.id,
                                 BudgetTransaction.status == "approved"))
    status = request.args.get("status")
    if status in TRANSACTION_STATES:
        query = query.filter_by(status=status)
    category = request.args.get("category")
    if category in CATEGORIES:
        query = query.filter_by(category=category)
    task_id = request.args.get("task_id")
    if task_id:
        try:
            query = query.filter_by(task_id=int(task_id))
        except ValueError:
            raise ValueError("task_id must be an integer.")
    start, end = request.args.get("start_date"), request.args.get("end_date")
    if start:
        query = query.filter(BudgetTransaction.transaction_date >= _date(start, "start_date"))
    if end:
        query = query.filter(BudgetTransaction.transaction_date <= _date(end, "end_date"))
    if start and end and start > end:
        raise ValueError("start_date cannot be after end_date.")
    return query


def _apply_to_task(transaction, sign=1):
    """Apply an approved ledger movement exactly once inside caller transaction."""
    if not transaction.task_id:
        return
    task = db.session.get(Task, transaction.task_id)
    if not task:
        return
    current = Decimal(str(task.spent_budget or 0))
    amount = Decimal(str(transaction.amount))
    if transaction.transaction_type == "credit":
        delta = -amount
    elif transaction.transaction_type == "adjustment":
        delta = amount if transaction.description.lower().startswith("increase:") else -amount
    else:
        delta = amount
    task.spent_budget = max(Decimal("0.00"), current + (delta * sign)).quantize(MONEY)


@finance_bp.get("/summary")
@login_required
@active_account_required
def finance_summary():
    """Organization financial roll-up based on approved transactions only."""
    if _org_id() is None and not current_user.has_role(ROLE_SUPER_ADMIN):
        return api_error("Your account must belong to an organization.", 409)
    query = BudgetTransaction.query.filter_by(status="approved")
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    start = request.args.get("start_date")
    end = request.args.get("end_date")
    try:
        if start:
            query = query.filter(BudgetTransaction.transaction_date >= _date(start, "start_date"))
        if end:
            query = query.filter(BudgetTransaction.transaction_date <= _date(end, "end_date"))
        if start and end and start > end:
            raise ValueError("start_date cannot be after end_date.")
    except ValueError as exc:
        return api_error(str(exc), 400)
    rows = query.all()
    totals = {"expense": Decimal("0.00"), "credit": Decimal("0.00"), "adjustment": Decimal("0.00")}
    by_category = {}
    by_month = {}
    for row in rows:
        amount = Decimal(str(row.amount))
        totals[row.transaction_type] += amount
        by_category[row.category] = by_category.get(row.category, Decimal("0.00")) + (amount if row.transaction_type == "expense" else -amount if row.transaction_type == "credit" else Decimal("0.00"))
        month = row.transaction_date.strftime("%Y-%m")
        by_month.setdefault(month, Decimal("0.00"))
        by_month[month] += amount if row.transaction_type == "expense" else -amount if row.transaction_type == "credit" else Decimal("0.00")
    tasks = Task.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        tasks = tasks.filter_by(organization_id=_org_id())
    budget_total = sum((Decimal(str(t.actual_budget or 0)) for t in tasks.all()), Decimal("0.00"))
    net = totals["expense"] - totals["credit"]
    return api_success({"currency": "INR", "approved_transactions": len(rows),
                        "approved_expenses": str(totals["expense"].quantize(MONEY)),
                        "credits": str(totals["credit"].quantize(MONEY)),
                        "net_expense": str(net.quantize(MONEY)),
                        "task_budget_total": str(budget_total.quantize(MONEY)),
                        "budget_remaining_against_ledger": str((budget_total - net).quantize(MONEY)),
                        "by_category": {k: str(v.quantize(MONEY)) for k, v in sorted(by_category.items())},
                        "by_month": {k: str(v.quantize(MONEY)) for k, v in sorted(by_month.items())},
                        "filters": {"start_date": start, "end_date": end}})


@finance_bp.get("/transactions")
@login_required
@active_account_required
def list_transactions():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        size = max(1, min(int(request.args.get("page_size", 25)), 100))
        query = _transaction_query()
    except ValueError as exc:
        return api_error(str(exc), 400)
    total = query.count()
    rows = query.order_by(BudgetTransaction.transaction_date.desc(), BudgetTransaction.id.desc()).offset((page - 1) * size).limit(size).all()
    return api_success({"items": [x.to_dict() for x in rows], "page": page, "page_size": size,
                        "total": total, "pages": (total + size - 1) // size})


@finance_bp.post("/transactions")
@login_required
@active_account_required
def create_transaction():
    data = _body()
    try:
        amount = _money(data.get("amount"))
        tx_date = _date(data.get("transaction_date") or date.today().isoformat())
        task = _task_for_org(data.get("task_id"))
    except (ValueError, LookupError, PermissionError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404 if isinstance(exc, LookupError) else 403)
    category = str(data.get("category", "operational"))
    tx_type = str(data.get("transaction_type", "expense"))
    if category not in CATEGORIES or tx_type not in TRANSACTION_TYPES:
        return api_error("Unsupported category or transaction_type.", 400)
    if task and not _admin() and task.creator_id != current_user.id and task.assignee_id != current_user.id:
        return api_error("You cannot submit expenses for this task.", 403)
    if not _org_id() and not current_user.has_role(ROLE_SUPER_ADMIN):
        return api_error("Your account must belong to an organization.", 409)
    tx = BudgetTransaction(organization_id=_org_id(), task_id=task.id if task else None,
        created_by=current_user.id, category=category, transaction_type=tx_type, amount=amount,
        currency=str(data.get("currency", "INR")).upper()[:3], merchant=str(data.get("merchant", "")).strip()[:160],
        reference=str(data.get("reference", "")).strip()[:100], description=str(data.get("description", "")).strip()[:2000],
        transaction_date=tx_date, status="approved" if _admin() and data.get("approve_immediately") is True else "submitted")
    db.session.add(tx)
    try:
        db.session.flush()
        if tx.status == "approved":
            tx.approved_by = current_user.id
            tx.approved_at = datetime.utcnow()
            _apply_to_task(tx)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    log_audit("finance.transaction.created", "budget_transaction", tx.id, {"amount": str(amount), "status": tx.status})
    return api_success(tx.to_dict(), "Transaction submitted." if tx.status == "submitted" else "Transaction recorded and approved.", 201)


@finance_bp.post("/transactions/<int:transaction_id>/approve")
@login_required
@active_account_required
def approve_transaction(transaction_id):
    if not _admin():
        return api_error("Administrator permission required to approve expenses.", 403)
    tx = BudgetTransaction.query.filter_by(id=transaction_id, organization_id=_org_id()).with_for_update().first()
    if not tx:
        return api_error("Transaction not found.", 404)
    if tx.status != "submitted":
        return api_error("Only submitted transactions can be approved.", 409)
    tx.status = "approved"
    tx.approved_by = current_user.id
    tx.approved_at = datetime.utcnow()
    _apply_to_task(tx)
    db.session.commit()
    log_audit("finance.transaction.approved", "budget_transaction", tx.id, {"amount": str(tx.amount)})
    return api_success(tx.to_dict(), "Transaction approved.")


@finance_bp.post("/transactions/<int:transaction_id>/reject")
@login_required
@active_account_required
def reject_transaction(transaction_id):
    if not _admin():
        return api_error("Administrator permission required to reject expenses.", 403)
    tx = BudgetTransaction.query.filter_by(id=transaction_id, organization_id=_org_id()).first()
    if not tx:
        return api_error("Transaction not found.", 404)
    if tx.status != "submitted":
        return api_error("Only submitted transactions can be rejected.", 409)
    note = str(_body().get("reason", "")).strip()[:1000]
    if not note:
        return api_error("A rejection reason is required.", 400)
    tx.status = "rejected"
    tx.rejected_reason = note
    tx.approved_by = current_user.id
    tx.approved_at = datetime.utcnow()
    db.session.commit()
    log_audit("finance.transaction.rejected", "budget_transaction", tx.id, {"reason": note})
    return api_success(tx.to_dict(), "Transaction rejected.")


@finance_bp.post("/transactions/<int:transaction_id>/void")
@login_required
@active_account_required
def void_transaction(transaction_id):
    tx = BudgetTransaction.query.filter_by(id=transaction_id).first()
    if not tx or (not current_user.has_role(ROLE_SUPER_ADMIN) and tx.organization_id != _org_id()):
        return api_error("Transaction not found.", 404)
    if tx.status == "void":
        return api_success(tx.to_dict(), "Transaction already voided.")
    if tx.status == "approved" and not _admin():
        return api_error("Only administrators can void approved transactions.", 403)
    if tx.status not in {"submitted", "approved", "rejected"}:
        return api_error("This transaction cannot be voided.", 409)
    if tx.status == "approved":
        _apply_to_task(tx, sign=-1)
    tx.status = "void"
    db.session.commit()
    log_audit("finance.transaction.voided", "budget_transaction", tx.id, {})
    return api_success(tx.to_dict(), "Transaction voided.")


@finance_bp.get("/policies")
@login_required
@active_account_required
def list_expense_policies():
    query = ExpensePolicy.query.filter_by(organization_id=_org_id())
    if request.args.get("include_inactive") != "1":
        query = query.filter_by(active=True)
    return api_success([p.to_dict() for p in query.order_by(ExpensePolicy.name.asc()).all()])


@finance_bp.post("/policies")
@login_required
@active_account_required
def create_expense_policy():
    if not _admin():
        return api_error("Administrator permission required.", 403)
    data = _body()
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "operational"))
    if not name or len(name) > 120 or category not in CATEGORIES:
        return api_error("A valid name and category are required.", 400)
    try:
        maximum = _money(data["maximum_amount"], "maximum_amount") if data.get("maximum_amount") not in (None, "") else None
        receipt = _money(data["requires_receipt_above"], "requires_receipt_above", allow_zero=True) if data.get("requires_receipt_above") not in (None, "") else None
    except ValueError as exc:
        return api_error(str(exc), 400)
    import json
    roles = data.get("allowed_roles", ["employee", "team_lead", "admin", "super_admin"])
    if not isinstance(roles, list) or not set(roles).issubset({"employee", "team_lead", "admin", "super_admin", "hr"}):
        return api_error("allowed_roles contains an unsupported role.", 400)
    policy = ExpensePolicy(organization_id=_org_id(), name=name, category=category, maximum_amount=maximum,
        requires_receipt_above=receipt, requires_approval=bool(data.get("requires_approval", True)),
        allowed_roles_json=json.dumps(sorted(set(roles))), active=bool(data.get("active", True)), created_by=current_user.id)
    db.session.add(policy)
    db.session.commit()
    log_audit("finance.policy.created", "expense_policy", policy.id, {"category": category})
    return api_success(policy.to_dict(), "Expense policy created.", 201)


@finance_bp.patch("/policies/<int:policy_id>")
@login_required
@active_account_required
def update_expense_policy(policy_id):
    if not _admin():
        return api_error("Administrator permission required.", 403)
    policy = ExpensePolicy.query.filter_by(id=policy_id, organization_id=_org_id()).first()
    if not policy:
        return api_error("Policy not found.", 404)
    data = _body()
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 120:
            return api_error("name must contain 1–120 characters.", 400)
        policy.name = name
    if "category" in data:
        if data["category"] not in CATEGORIES:
            return api_error("Unsupported category.", 400)
        policy.category = data["category"]
    try:
        if "maximum_amount" in data:
            policy.maximum_amount = _money(data["maximum_amount"], "maximum_amount") if data["maximum_amount"] not in (None, "") else None
        if "requires_receipt_above" in data:
            policy.requires_receipt_above = _money(data["requires_receipt_above"], "requires_receipt_above", allow_zero=True) if data["requires_receipt_above"] not in (None, "") else None
    except ValueError as exc:
        return api_error(str(exc), 400)
    for field in ("requires_approval", "active"):
        if field in data:
            setattr(policy, field, bool(data[field]))
    db.session.commit()
    log_audit("finance.policy.updated", "expense_policy", policy.id, {"fields": sorted(data)})
    return api_success(policy.to_dict(), "Policy updated.")


@finance_bp.get("/purchases")
@login_required
@active_account_required
def list_purchase_requests():
    query = PurchaseRequest.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    if not _admin():
        query = query.filter_by(requester_id=current_user.id)
    state = request.args.get("status")
    if state in PURCHASE_STATES:
        query = query.filter_by(status=state)
    rows = query.order_by(PurchaseRequest.created_at.desc()).limit(200).all()
    return api_success([row.to_dict() for row in rows])


@finance_bp.post("/purchases")
@login_required
@active_account_required
def create_purchase_request():
    data = _body()
    title = str(data.get("title", "")).strip()
    if not title or len(title) > 180:
        return api_error("title is required and must be at most 180 characters.", 400)
    try:
        amount = _money(data.get("amount"))
        task = _task_for_org(data.get("task_id"))
    except (ValueError, LookupError, PermissionError) as exc:
        return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404 if isinstance(exc, LookupError) else 403)
    if not _org_id() and not current_user.has_role(ROLE_SUPER_ADMIN):
        return api_error("Your account must belong to an organization.", 409)
    row = PurchaseRequest(organization_id=_org_id(), requester_id=current_user.id, task_id=task.id if task else None,
        project_id=data.get("project_id"), title=title, vendor=str(data.get("vendor", "")).strip()[:180],
        justification=str(data.get("justification", "")).strip()[:10000], amount=amount,
        currency=str(data.get("currency", "INR")).upper()[:3])
    db.session.add(row)
    db.session.commit()
    log_audit("finance.purchase.created", "purchase_request", row.id, {"amount": str(amount)})
    return api_success(row.to_dict(), "Purchase request submitted.", 201)


@finance_bp.post("/purchases/<int:request_id>/review")
@login_required
@active_account_required
def review_purchase_request(request_id):
    if not _admin():
        return api_error("Administrator permission required.", 403)
    row = PurchaseRequest.query.filter_by(id=request_id, organization_id=_org_id()).first()
    if not row:
        return api_error("Purchase request not found.", 404)
    data = _body()
    decision = data.get("decision")
    if decision not in {"approved", "rejected"}:
        return api_error("decision must be approved or rejected.", 400)
    if row.status != "pending":
        return api_error("Only pending requests can be reviewed.", 409)
    note = str(data.get("note", "")).strip()[:1000]
    if decision == "rejected" and not note:
        return api_error("A reason is required when rejecting a purchase.", 400)
    row.status = decision
    row.reviewer_id = current_user.id
    row.review_note = note
    row.reviewed_at = datetime.utcnow()
    db.session.commit()
    log_audit("finance.purchase.reviewed", "purchase_request", row.id, {"decision": decision})
    return api_success(row.to_dict(), f"Purchase request {decision}.")


@finance_bp.get("/budget-alerts")
@login_required
@active_account_required
def budget_alerts():
    """Return tasks nearing or exceeding their configured budget."""
    threshold = request.args.get("threshold", "80")
    try:
        threshold_value = int(threshold)
        if threshold_value < 1 or threshold_value > 100:
            raise ValueError
    except ValueError:
        return api_error("threshold must be an integer from 1 to 100.", 400)
    query = Task.query.filter(Task.actual_budget > 0)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    if not _admin():
        query = query.filter(or_(Task.creator_id == current_user.id, Task.assignee_id == current_user.id))
    result = []
    for task in query.all():
        actual = Decimal(str(task.actual_budget or 0))
        spent = Decimal(str(task.spent_budget or 0))
        pct = float((spent / actual) * 100) if actual else 0
        if pct >= threshold_value:
            result.append({"task_id": task.id, "title": task.title, "actual_budget": str(actual),
                           "spent_budget": str(spent), "remaining": str((actual - spent).quantize(MONEY)),
                           "utilization_percent": round(pct, 2), "over_budget": spent > actual})
    result.sort(key=lambda x: x["utilization_percent"], reverse=True)
    return api_success(result)
