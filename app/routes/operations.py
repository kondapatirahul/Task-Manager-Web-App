"""Enterprise operational workspaces API and page controller.

This blueprint exposes tenant-scoped APIs for incident management, change control,
QA test management, capacity planning, employee lifecycle, data governance,
procurement, portfolio baselines, and release management. Business policies live in
app.services.operations_domains; persistence is shared but the module schemas are
kept separate.
"""
import csv
import io
import json
import re
from datetime import date, datetime, timezone
from flask import Blueprint, Response, current_app, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_, false
from app import db
from app.models import ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_TEAM_LEAD, ROLE_HR, User
from app.operations_models import (OperationalRecord, OperationalEvent, OperationalChecklistItem, OperationalAttachment, OperationalApproval, OperationalSLAEvent, OperationalPolicy, OperationalLink)
from app.routes.utils import active_account_required, api_error, api_success
from app.services.operations_common import (
    add_event, can_manage, next_key, parse_due_date, serialize_page, visible_query,
)
from app.services.operations_domains import DOMAIN_POLICIES

operations_bp = Blueprint("operations", __name__)
MODULES = {
    "incidents": {"title": "Incident Management", "prefix": "INC", "icon": "alert-triangle",
                  "description": "Coordinate incident response, service impact, mitigation, and resolution."},
    "changes": {"title": "Change Control", "prefix": "CHG", "icon": "git-pull-request",
                "description": "Assess operational risk, approvals, implementation windows, and rollback plans."},
    "quality": {"title": "QA Test Management", "prefix": "QA", "icon": "check-square",
                "description": "Plan test cases, track execution, capture evidence, and manage defects."},
    "capacity": {"title": "Capacity Planning", "prefix": "CAP", "icon": "gauge",
                 "description": "Compare planned demand with available team capacity and approve allocations."},
    "lifecycle": {"title": "Employee Lifecycle", "prefix": "HRL", "icon": "users",
                   "description": "Coordinate onboarding, transfers, role changes, and offboarding checklists."},
    "data-governance": {"title": "Data Access Governance", "prefix": "DAR", "icon": "database",
                        "description": "Review data access requests, purpose, classification, expiry, and revocation."},
    "procurement": {"title": "Procurement Requests", "prefix": "PR", "icon": "shopping-cart",
                    "description": "Route purchasing requests through business, manager, and finance approvals."},
    "baselines": {"title": "Portfolio Baselines", "prefix": "BL", "icon": "target",
                  "description": "Maintain controlled scope, schedule, and cost baselines with version history."},
    "releases": {"title": "Release Management", "prefix": "REL", "icon": "package",
                 "description": "Coordinate release readiness, testing evidence, deployment, and rollback."},
}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
ADMIN_ROLES = {ROLE_ADMIN, ROLE_SUPER_ADMIN}


def _module_or_none(module_key):
    if module_key not in MODULES:
        return None
    return MODULES[module_key]


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _tenant_for_request(data=None):
    data = data or {}
    if getattr(current_user, "role", "") == ROLE_SUPER_ADMIN:
        candidate = data.get("organization_id") or request.args.get("organization_id")
        try:
            return int(candidate) if candidate else current_user.organization_id
        except (TypeError, ValueError):
            return None
    return current_user.organization_id


def _scope_record(record):
    if record is None:
        return False
    if getattr(current_user, "role", "") == ROLE_SUPER_ADMIN:
        return True
    return record.organization_id == current_user.organization_id


def _record_or_error(module_key, record_id):
    record = OperationalRecord.query.filter_by(id=record_id, module_key=module_key).first()
    if not _scope_record(record):
        return None, api_error("Record not found.", 404)
    return record, None


def _make_record(module_key, data, normalized):
    meta = MODULES[module_key]
    organization_id = _tenant_for_request(data)
    if organization_id is None:
        return None, api_error("Your account must belong to an organization.", 409)
    title = str(data.get("title") or data.get("name") or normalized.get("title") or "").strip()
    if not title:
        title = str(normalized.get("summary") or normalized.get("description") or meta["title"]).strip()[:240]
    if not title or len(title) > 240:
        return None, api_error("title is required and must be at most 240 characters.", 400)
    priority = str(data.get("priority", "medium")).lower()
    if priority not in VALID_PRIORITIES:
        return None, api_error("priority must be low, medium, high, or critical.", 400)
    try:
        due_date = parse_due_date(data.get("due_date"))
    except ValueError as exc:
        return None, api_error(str(exc), 400)
    domain_module = __import__(f"app.services.operations_domains.{module_key.replace('-', '_')}", fromlist=["ALLOWED_STATUSES"])
    initial_status = str(data.get("status", domain_module.ALLOWED_STATUSES[0])).lower()
    validate, _ = DOMAIN_POLICIES[module_key]
    if initial_status not in domain_module.ALLOWED_STATUSES:
        return None, api_error("Unsupported initial status.", 400)
    record = OperationalRecord(
        organization_id=organization_id, module_key=module_key,
        record_key=next_key(organization_id, module_key, meta["prefix"]),
        title=title, summary=str(data.get("summary", ""))[:10000],
        status=initial_status, priority=priority, owner_id=_owner_id(data.get("owner_id"), organization_id),
        created_by=current_user.id, updated_by=current_user.id, due_date=due_date,
        payload_json=normalized, version=1,
    )
    db.session.add(record)
    db.session.flush()
    add_event(record, current_user.id, "created", f"{meta['title']} record created.",
              to_status=initial_status, details={"title": title, "key": record.record_key})
    return record, None


def _owner_id(value, organization_id=None):
    if value in (None, ""):
        return None
    try:
        owner_id = int(value)
    except (ValueError, TypeError):
        raise ValueError("owner_id must be an integer.")
    owner = User.query.filter_by(id=owner_id).first()
    if owner is None:
        raise ValueError("Owner does not exist.")
    expected_organization = organization_id if organization_id is not None else current_user.organization_id
    if expected_organization is not None and owner.organization_id != expected_organization:
        raise ValueError("Owner must belong to the record's organization.")
    return owner_id


@operations_bp.get("/operations")
@login_required
@active_account_required
def operations_hub():
    return render_template("operations_hub.html", modules=MODULES, active_page="operations")


@operations_bp.get("/operations/analytics")
@login_required
@active_account_required
def operations_analytics_page():
    return render_template("operations_analytics.html", modules=MODULES, active_page="operations")


@operations_bp.get("/operations/policy-simulator")
@login_required
@active_account_required
def operations_policy_simulator_page():
    return render_template("operations_policy_simulator.html", modules=MODULES, active_page="operations")


@operations_bp.get("/api/operations/analytics/policy-simulation")
@login_required
@active_account_required
def operations_policy_simulation():
    module_key = request.args.get("module", "")
    if module_key and module_key not in MODULES:
        return api_error("Unknown module filter.", 400)
    try:
        target = int(request.args.get("target_minutes", 240))
    except (TypeError, ValueError):
        return api_error("target_minutes must be an integer.", 400)
    if target < 0 or target > 525600:
        return api_error("target_minutes must be between 0 and 525600.", 400)
    query = OperationalSLAEvent.query.join(
        OperationalRecord, OperationalRecord.id == OperationalSLAEvent.record_id
    ).filter(OperationalRecord.archived.is_(False))
    if current_user.role != ROLE_SUPER_ADMIN:
        query = query.filter(OperationalSLAEvent.organization_id == current_user.organization_id)
    if module_key:
        query = query.filter(OperationalRecord.module_key == module_key)
    event_type = request.args.get("event_type", "resolved")
    if event_type not in {"started", "paused", "resumed", "acknowledged", "breached", "resolved", "all"}:
        return api_error("Unsupported event_type.", 400)
    if event_type != "all":
        query = query.filter(OperationalSLAEvent.event_type == event_type)
    rows = query.order_by(OperationalSLAEvent.occurred_at.desc()).limit(5000).all()
    measured = [row for row in rows if row.elapsed_minutes >= 0]
    passed = sum(1 for row in measured if row.elapsed_minutes <= target)
    failed = len(measured) - passed
    elapsed = sorted(row.elapsed_minutes for row in measured)
    median = elapsed[len(elapsed) // 2] if elapsed else None
    p90 = elapsed[min(len(elapsed) - 1, int(len(elapsed) * .9))] if elapsed else None
    by_module = {}
    for row in measured:
        key = row.record.module_key
        item = by_module.setdefault(key, {"module": key, "title": MODULES[key]["title"], "samples": 0,
                                         "within_target": 0, "outside_target": 0})
        item["samples"] += 1
        item["within_target" if row.elapsed_minutes <= target else "outside_target"] += 1
    return api_success({
        "target_minutes": target, "event_type": event_type, "module": module_key or None,
        "sample_count": len(measured), "within_target": passed, "outside_target": failed,
        "compliance_percent": round(passed / len(measured) * 100, 2) if measured else None,
        "median_elapsed_minutes": median, "p90_elapsed_minutes": p90,
        "by_module": list(by_module.values()), "sample_cap": 5000,
        "simulation_only": True,
    })


@operations_bp.get("/operations/api-catalog")
@login_required
@active_account_required
def operations_api_catalog_page():
    endpoints = [
        ("GET", "/api/operations/modules", "List modules and counts."),
        ("GET", "/api/operations/<module>", "List records with search, status, priority, and pagination."),
        ("POST", "/api/operations/<module>", "Create a validated operational record."),
        ("GET", "/api/operations/<module>/<id>", "Read record, event history, and current payload."),
        ("PATCH", "/api/operations/<module>/<id>", "Update a record using optimistic version checks."),
        ("POST", "/api/operations/<module>/<id>/transition", "Validate and apply a workflow transition."),
        ("POST", "/api/operations/<module>/<id>/comments", "Append a comment to activity history."),
        ("GET", "/api/operations/<module>/<id>/assessment", "Get domain assessment, controls, and recommended actions."),
        ("GET", "/api/operations/<module>/<id>/checklist", "List checklist items and completion metrics."),
        ("POST", "/api/operations/<module>/<id>/checklist", "Add a checklist item."),
        ("PATCH", "/api/operations/<module>/<id>/checklist/<item_id>", "Update checklist item or completion state."),
        ("GET", "/api/operations/<module>/<id>/approvals", "List approval assignments."),
        ("POST", "/api/operations/<module>/<id>/approvals", "Assign an approver."),
        ("POST", "/api/operations/<module>/<id>/approvals/<approval_id>/decision", "Record an approval decision."),
        ("GET", "/api/operations/<module>/<id>/links", "List related operational records."),
        ("POST", "/api/operations/<module>/<id>/links", "Create a typed cross-module relationship."),
        ("GET", "/api/operations/<module>/<id>/sla", "Read recorded SLA events."),
        ("POST", "/api/operations/<module>/<id>/sla", "Record an SLA clock event."),
        ("GET", "/api/operations/<module>/<id>/attachments", "List registered evidence metadata."),
        ("POST", "/api/operations/<module>/<id>/attachments", "Register evidence already stored in a private object store."),
        ("POST", "/api/operations/<module>/bulk-transition", "Atomically transition up to 100 records."),
        ("POST", "/api/operations/<module>/import.csv", "Validate and import up to 200 CSV rows."),
        ("GET", "/api/operations/<module>/export.csv", "Export organization-scoped records."),
        ("GET", "/api/operations/analytics/overview", "Cross-module workload overview."),
        ("GET", "/api/operations/analytics/controls", "Cross-module control-readiness report."),
        ("GET", "/api/operations/analytics/data-quality", "Read-only data quality report."),
        ("GET", "/api/operations/analytics/sla", "SLA event performance report."),
        ("GET", "/api/operations/analytics/policy-simulation", "Read-only historical SLA target simulation."),
        ("GET", "/api/operations/work-queue", "Prioritized cross-module work queue."),
        ("POST", "/api/operations/work-queue/assign", "Atomically assign selected work items."),
        ("GET", "/api/operations/policies", "List organization operational policies."),
        ("PUT", "/api/operations/policies/<module>", "Create or update a module policy."),
    ]
    return render_template("operations_api_catalog.html", modules=MODULES,
                           endpoints=endpoints, active_page="operations")


@operations_bp.get("/operations/sla-report")
@login_required
@active_account_required
def operations_sla_report_page():
    return render_template("operations_sla_report.html", modules=MODULES, active_page="operations")


@operations_bp.get("/api/operations/analytics/sla")
@login_required
@active_account_required
def operations_sla_report_data():
    query = OperationalSLAEvent.query.join(
        OperationalRecord, OperationalRecord.id == OperationalSLAEvent.record_id
    ).filter(OperationalRecord.archived.is_(False))
    if current_user.role != ROLE_SUPER_ADMIN:
        query = query.filter(OperationalSLAEvent.organization_id == current_user.organization_id)
    module_key = request.args.get("module", "")
    if module_key:
        if module_key not in MODULES:
            return api_error("Unknown module filter.", 400)
        query = query.filter(OperationalRecord.module_key == module_key)
    event_type = request.args.get("event_type", "")
    if event_type in {"started", "paused", "resumed", "acknowledged", "breached", "resolved"}:
        query = query.filter(OperationalSLAEvent.event_type == event_type)
    rows = query.order_by(OperationalSLAEvent.occurred_at.desc()).limit(5000).all()
    grouped = {}
    for event in rows:
        module_key = event.record.module_key
        group = grouped.setdefault(module_key, {"module": module_key, "title": MODULES[module_key]["title"],
            "events": 0, "breaches": 0, "acknowledged": 0, "resolved": 0, "target_minutes": 0,
            "elapsed_minutes": 0, "within_target": 0})
        group["events"] += 1
        group["target_minutes"] += event.target_minutes
        group["elapsed_minutes"] += event.elapsed_minutes
        if event.event_type == "breached":
            group["breaches"] += 1
        if event.event_type == "acknowledged":
            group["acknowledged"] += 1
        if event.event_type == "resolved":
            group["resolved"] += 1
        if event.target_minutes and event.elapsed_minutes <= event.target_minutes:
            group["within_target"] += 1
    from app.services.operations_controls import summarize_sla_observations
    try:
        comparison_target = max(0, min(int(request.args.get("target_minutes", 240)), 525600))
    except (TypeError, ValueError):
        comparison_target = 240
    sla_comparison = summarize_sla_observations([
        {"module": event.record.module_key, "elapsed_minutes": event.elapsed_minutes,
         "event_type": event.event_type} for event in rows
    ], comparison_target)
    summary = {
        "sla_comparison": sla_comparison,
        "events": len(rows),
        "breaches": sum(1 for event in rows if event.event_type == "breached"),
        "acknowledged": sum(1 for event in rows if event.event_type == "acknowledged"),
        "resolved": sum(1 for event in rows if event.event_type == "resolved"),
        "modules": list(grouped.values()),
        "items": [{"id": event.id, "record_id": event.record_id,
                   "record_key": event.record.record_key, "record_title": event.record.title,
                   "module": event.record.module_key, "event_type": event.event_type,
                   "target_minutes": event.target_minutes, "elapsed_minutes": event.elapsed_minutes,
                   "variance_minutes": event.elapsed_minutes - event.target_minutes,
                   "reason": event.reason, "actor_id": event.actor_id,
                   "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None}
                  for event in rows],
        "row_cap": 5000,
    }
    return api_success(summary)


@operations_bp.get("/operations/work-queue")
@login_required
@active_account_required
def operations_work_queue_page():
    return render_template("operations_work_queue.html", modules=MODULES, active_page="operations")


@operations_bp.get("/api/operations/work-queue")
@login_required
@active_account_required
def operations_work_queue_data():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        page_size = max(1, min(int(request.args.get("page_size", 50)), 200))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    module_filter = request.args.get("module", "")
    if module_filter and module_filter not in MODULES:
        return api_error("Unknown module filter.", 400)
    query = OperationalRecord.query.filter_by(archived=False)
    if current_user.role != ROLE_SUPER_ADMIN:
        if current_user.organization_id is None:
            return api_success({"items": [], "pagination": {"page": page, "page_size": page_size, "total": 0, "pages": 0}})
        query = query.filter_by(organization_id=current_user.organization_id)
    if module_filter:
        query = query.filter_by(module_key=module_filter)
    if request.args.get("unassigned") == "1":
        query = query.filter(OperationalRecord.owner_id.is_(None))
    if request.args.get("overdue") == "1":
        query = query.filter(OperationalRecord.due_date < date.today()).filter(
            OperationalRecord.status.notin_(["closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"])
        )
    priority = request.args.get("priority", "")
    if priority in VALID_PRIORITIES:
        query = query.filter_by(priority=priority)
    search = request.args.get("q", "").strip()[:120]
    if search:
        term = f"%{search}%"
        query = query.filter(or_(OperationalRecord.title.ilike(term),
                                 OperationalRecord.record_key.ilike(term),
                                 OperationalRecord.summary.ilike(term)))
    total = query.count()
    # Rank a bounded candidate window using explicit priority, age, and ownership signals.
    from app.services.operations_queue import rank_queue
    candidates = query.order_by(OperationalRecord.updated_at.asc()).limit(5000).all()
    ranked = rank_queue(candidates)
    start_index = (page - 1) * page_size
    rows = ranked[start_index:start_index + page_size]
    items = []
    for row, score in rows:
        items.append({**row.to_dict(False), "module_title": MODULES[row.module_key]["title"],
                      "overdue_days": score["overdue_days"], "queue_score": score["score"],
                      "queue_reasons": score["reasons"], "unassigned": row.owner_id is None})
    return api_success({"items": items, "pagination": {"page": page, "page_size": page_size,
                        "total": total, "pages": (total + page_size - 1) // page_size,
                        "ranked_candidate_cap": 5000}})


@operations_bp.post("/api/operations/work-queue/assign")
@login_required
@active_account_required
def assign_work_queue_records():
    if not can_manage(current_user):
        return api_error("Manager or administrator role required.", 403)
    data = _body()
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 200:
        return api_error("ids must contain between 1 and 200 record IDs.", 400)
    if any(not isinstance(item, int) or item < 1 for item in ids):
        return api_error("Record IDs must be positive integers.", 400)
    owner_value = data.get("owner_id")
    try:
        owner_id = int(owner_value) if owner_value not in (None, "") else None
    except (TypeError, ValueError):
        return api_error("owner_id must be an integer or null.", 400)
    owner = User.query.filter_by(id=owner_id, account_active=True).first() if owner_id else None
    if owner_id and owner is None:
        return api_error("Active owner not found.", 404)
    if owner and owner.organization_id != current_user.organization_id and current_user.role != ROLE_SUPER_ADMIN:
        return api_error("Owner must belong to your organization.", 403)
    query = OperationalRecord.query.filter(OperationalRecord.id.in_(set(ids)), OperationalRecord.archived.is_(False))
    if current_user.role != ROLE_SUPER_ADMIN:
        query = query.filter_by(organization_id=current_user.organization_id)
    rows = query.all()
    if len(rows) != len(set(ids)):
        return api_error("One or more records were not found in your organization.", 404)
    if owner and any(row.organization_id != owner.organization_id for row in rows):
        return api_error("The selected records and owner must belong to the same organization.", 403)
    for row in rows:
        previous_owner = row.owner_id
        row.owner_id = owner_id
        row.updated_by = current_user.id
        row.version += 1
        add_event(row, current_user.id, "owner_changed",
                  f"Owner changed from {previous_owner or 'unassigned'} to {owner_id or 'unassigned'}.",
                  details={"previous_owner_id": previous_owner, "owner_id": owner_id})
    db.session.commit()
    return api_success({"updated": len(rows), "owner_id": owner_id, "ids": ids},
                       "Work queue assignments updated.")


@operations_bp.get("/operations/governance")
@login_required
@active_account_required
def operations_governance_page():
    return render_template("operations_governance.html", modules=MODULES, active_page="operations")


@operations_bp.get("/operations/workflow-matrix")
@login_required
@active_account_required
def operations_workflow_matrix_page():
    matrix = {}
    for key, meta in MODULES.items():
        domain = __import__("app.services.operations_domains." + key.replace("-", "_"),
                            fromlist=["ALLOWED_STATUSES", "TRANSITIONS", "REQUIRED_FIELDS", "ENUM_FIELDS"])
        matrix[key] = {
            "title": meta["title"], "description": meta["description"],
            "statuses": domain.ALLOWED_STATUSES, "transitions": domain.TRANSITIONS,
            "required_fields": domain.REQUIRED_FIELDS, "enum_fields": domain.ENUM_FIELDS,
        }
    return render_template("operations_workflow_matrix.html", modules=MODULES,
                           matrix=matrix, active_page="operations")


@operations_bp.get("/operations/import-guide")
@login_required
@active_account_required
def operations_import_guide_page():
    from app.services.operations_domains import DOMAIN_POLICIES
    required_fields = {}
    for key in MODULES:
        module = __import__("app.services.operations_domains." + key.replace("-", "_"),
                            fromlist=["REQUIRED_FIELDS"])
        required_fields[key] = list(module.REQUIRED_FIELDS)
    return render_template("operations_import_guide.html", modules=MODULES,
                           required_fields=required_fields, active_page="operations")


@operations_bp.get("/operations/data-quality")
@login_required
@active_account_required
def operations_data_quality_page():
    return render_template("operations_data_quality.html", modules=MODULES, active_page="operations")


@operations_bp.get("/operations/<module_key>")
@login_required
@active_account_required
def operations_page(module_key):
    meta = _module_or_none(module_key)
    if meta is None:
        return render_template("404.html"), 404
    domain_module = __import__(
        "app.services.operations_domains." + module_key.replace("-", "_"),
        fromlist=["ALLOWED_STATUSES"]
    )
    template_name = "operations_" + module_key.replace("-", "_") + ".html"
    return render_template(template_name, module_key=module_key, module=meta,
                           modules=MODULES, status_options=domain_module.ALLOWED_STATUSES,
                           active_page="operations")


@operations_bp.get("/api/operations/modules")
@login_required
@active_account_required
def list_modules():
    result = []
    for key, meta in MODULES.items():
        query = visible_query(OperationalRecord, current_user, key)
        result.append({**meta, "key": key, "metrics": _metrics(query)})
    return api_success({"items": result})


def _metrics(query):
    records = query.with_entities(OperationalRecord.status).all()
    statuses = {}
    for row in records:
        statuses[row.status] = statuses.get(row.status, 0) + 1
    return {"total": len(records), "statuses": statuses,
            "open": sum(v for k, v in statuses.items()
                        if k not in {"closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"})}


@operations_bp.get("/api/operations/<module_key>")
@login_required
@active_account_required
def list_records(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        page_size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = visible_query(OperationalRecord, current_user, module_key)
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    if status:
        query = query.filter_by(status=status)
    if priority in VALID_PRIORITIES:
        query = query.filter_by(priority=priority)
    owner = request.args.get("owner_id")
    if owner:
        try:
            query = query.filter_by(owner_id=int(owner))
        except ValueError:
            return api_error("owner_id must be an integer.", 400)
    search = request.args.get("q", "").strip()[:120]
    if search:
        term = f"%{search}%"
        query = query.filter(or_(OperationalRecord.title.ilike(term),
                                 OperationalRecord.record_key.ilike(term),
                                 OperationalRecord.summary.ilike(term)))
    if request.args.get("overdue") == "1":
        query = query.filter(OperationalRecord.due_date < date.today()).filter(
            OperationalRecord.status.notin_(["closed", "completed", "cancelled", "released", "rejected"])
        )
    data = serialize_page(query, page, page_size)
    data["metrics"] = _metrics(visible_query(OperationalRecord, current_user, module_key))
    return api_success(data)


@operations_bp.post("/api/operations/<module_key>")
@login_required
@active_account_required
def create_record(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    data = _body()
    validate, _ = DOMAIN_POLICIES[module_key]
    normalized, errors = validate(data, partial=False)
    if errors:
        return api_error("Please correct the highlighted fields.", 422) if False else (
            {"ok": False, "error": "Please correct the highlighted fields.", "fields": errors}, 422
        )
    try:
        record, error = _make_record(module_key, data, normalized)
    except ValueError as exc:
        return api_error(str(exc), 400)
    if error:
        return error
    db.session.commit()
    return api_success(record.to_dict(), "Record created.", 201)


@operations_bp.get("/api/operations/<module_key>/<int:record_id>")
@login_required
@active_account_required
def get_record(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    events = OperationalEvent.query.filter_by(record_id=record.id).order_by(
        OperationalEvent.created_at.desc(), OperationalEvent.id.desc()
    ).limit(100).all()
    data = record.to_dict()
    data["events"] = [event.to_dict() for event in reversed(events)]
    data["checklist"] = DOMAIN_POLICIES[module_key][0](record.payload_json or {}, partial=True)[0]
    return api_success(data)


@operations_bp.patch("/api/operations/<module_key>/<int:record_id>")
@login_required
@active_account_required
def update_record(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    if not can_manage(current_user) and record.created_by != current_user.id and record.owner_id != current_user.id:
        return api_error("You cannot edit this record.", 403)
    data = _body()
    expected_version = data.pop("version", None)
    if expected_version is not None:
        try:
            if int(expected_version) != record.version:
                return api_error("This record changed since you opened it. Refresh and retry.", 409)
        except (TypeError, ValueError):
            return api_error("version must be an integer.", 400)
    validate, _ = DOMAIN_POLICIES[module_key]
    normalized, errors = validate(data, partial=True)
    if errors:
        return {"ok": False, "error": "Please correct the highlighted fields.", "fields": errors}, 422
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 240:
            return api_error("title must be 1–240 characters.", 400)
        record.title = title
    if "summary" in data:
        record.summary = str(data.get("summary") or "")[:10000]
    if "priority" in data:
        if data["priority"] not in VALID_PRIORITIES:
            return api_error("Unsupported priority.", 400)
        record.priority = data["priority"]
    if "due_date" in data:
        try:
            record.due_date = parse_due_date(data.get("due_date"))
        except ValueError as exc:
            return api_error(str(exc), 400)
    if "owner_id" in data:
        try:
            record.owner_id = _owner_id(data.get("owner_id"), record.organization_id)
        except ValueError as exc:
            return api_error(str(exc), 400)
    payload = dict(record.payload_json or {})
    payload.update(normalized)
    record.payload_json = payload
    record.updated_by = current_user.id
    record.version += 1
    add_event(record, current_user.id, "updated", "Record details updated.",
              details={"fields": sorted(data.keys()), "version": record.version})
    db.session.commit()
    return api_success(record.to_dict(), "Record updated.")


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/transition")
@login_required
@active_account_required
def transition_record(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    data = _body()
    target = str(data.get("status", "")).strip().lower()
    _, transition = DOMAIN_POLICIES[module_key]
    message = transition(record.status, target, actor_role=current_user.role,
                         payload=record.payload_json or {})
    if message:
        return api_error(message, 409)
    previous = record.status
    record.status = target
    record.updated_by = current_user.id
    record.updated_at = __import__("app.operations_models", fromlist=["operations_now"]).operations_now()
    record.version += 1
    add_event(record, current_user.id, "status_changed",
              str(data.get("comment", ""))[:2000], from_status=previous, to_status=target)
    db.session.commit()
    return api_success(record.to_dict(), f"Status changed from {previous} to {target}.")


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/comments")
@login_required
@active_account_required
def add_comment(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    data = _body()
    message = str(data.get("message", "")).strip()
    if not message:
        return api_error("Comment cannot be empty.", 400)
    if len(message) > 5000:
        return api_error("Comment must be at most 5,000 characters.", 400)
    event = add_event(record, current_user.id, "comment", message)
    db.session.commit()
    return api_success(event.to_dict(), "Comment added.", 201)


@operations_bp.get("/api/operations/<module_key>/<int:record_id>/history")
@login_required
@active_account_required
def record_history(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 250))
    except ValueError:
        return api_error("limit must be an integer.", 400)
    events = OperationalEvent.query.filter_by(record_id=record.id).order_by(
        OperationalEvent.created_at.desc(), OperationalEvent.id.desc()
    ).limit(limit).all()
    return api_success({"items": [event.to_dict() for event in events]})


@operations_bp.get("/api/operations/<module_key>/export.csv")
@login_required
@active_account_required
def export_records(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    query = visible_query(OperationalRecord, current_user, module_key).order_by(
        OperationalRecord.created_at.desc()
    ).limit(10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["key", "title", "status", "priority", "owner_id", "due_date",
                     "created_at", "updated_at", "fields_json"])
    for row in query.all():
        fields = json.dumps(row.payload_json or {}, ensure_ascii=False, sort_keys=True)
        values = [row.record_key, row.title, row.status, row.priority, row.owner_id,
                  row.due_date.isoformat() if row.due_date else "", row.created_at.isoformat(),
                  row.updated_at.isoformat(), fields]
        writer.writerow([_spreadsheet_safe(v) for v in values])
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="tasknest-{module_key}.csv"'
    response.headers["Cache-Control"] = "no-store"
    return response


def _spreadsheet_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


@operations_bp.get("/api/operations/<module_key>/dashboard")
@login_required
@active_account_required
def module_dashboard(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    query = visible_query(OperationalRecord, current_user, module_key)
    today = date.today()
    due_soon = query.filter(OperationalRecord.due_date >= today).filter(
        OperationalRecord.due_date <= date.fromordinal(today.toordinal() + 14)
    ).count()
    overdue = query.filter(OperationalRecord.due_date < today).filter(
        OperationalRecord.status.notin_(["closed", "completed", "cancelled", "released", "rejected"])
    ).count()
    recent = query.order_by(OperationalRecord.updated_at.desc()).limit(8).all()
    return api_success({
        "metrics": _metrics(query), "due_soon": due_soon, "overdue": overdue,
        "recent": [row.to_dict(False) for row in recent],
    })


@operations_bp.delete("/api/operations/<module_key>/<int:record_id>")
@login_required
@active_account_required
def archive_record(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    if not can_manage(current_user):
        return api_error("Administrator or manager role required.", 403)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    record.archived = True
    record.updated_by = current_user.id
    record.version += 1
    add_event(record, current_user.id, "archived", "Record archived.")
    db.session.commit()
    return api_success({"id": record.id, "archived": True}, "Record archived.")


@operations_bp.get("/api/operations/<module_key>/readiness")
@login_required
@active_account_required
def readiness_report(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    validate, _ = DOMAIN_POLICIES[module_key]
    rows = visible_query(OperationalRecord, current_user, module_key).limit(1000).all()
    result = []
    for row in rows:
        payload, errors = validate(row.payload_json or {}, partial=False)
        domain_module = __import__("app.services.operations_domains." + module_key.replace("-", "_"), fromlist=["REQUIRED_FIELDS"])
        required = len(domain_module.REQUIRED_FIELDS)
        result.append({
            "id": row.id, "key": row.record_key, "title": row.title, "status": row.status,
            "missing_fields": list(errors.keys()), "ready": not errors,
            "required_field_count": required,
        })
    return api_success({"items": result, "total": len(result),
                        "ready": sum(1 for item in result if item["ready"])})


@operations_bp.get("/api/operations/<module_key>/owners")
@login_required
@active_account_required
def list_owners(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    query = User.query.filter_by(account_active=True)
    if current_user.role != ROLE_SUPER_ADMIN:
        query = query.filter_by(organization_id=current_user.organization_id)
    users = query.order_by(User.first_name.asc(), User.last_name.asc()).limit(1000).all()
    return api_success({"items": [{"id": user.id, "name": user.full_name if hasattr(user, "full_name")
                                  else user.email, "email": user.email, "role": user.role}
                                 for user in users]})


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/duplicate")
@login_required
@active_account_required
def duplicate_record(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    original, error = _record_or_error(module_key, record_id)
    if error:
        return error
    if not can_manage(current_user) and original.created_by != current_user.id:
        return api_error("You cannot duplicate this record.", 403)
    meta = MODULES[module_key]
    organization_id = original.organization_id
    copy = OperationalRecord(
        organization_id=organization_id, module_key=module_key,
        record_key=next_key(organization_id, module_key, meta["prefix"]),
        title=(original.title + " (copy)")[:240], summary=original.summary,
        status="draft", priority=original.priority, owner_id=original.owner_id,
        created_by=current_user.id, updated_by=current_user.id, due_date=original.due_date,
        payload_json=dict(original.payload_json or {}), version=1,
    )
    db.session.add(copy)
    db.session.flush()
    add_event(copy, current_user.id, "duplicated", f"Copied from {original.record_key}.",
              to_status="draft", details={"source_id": original.id})
    db.session.commit()
    return api_success(copy.to_dict(), "Record duplicated.", 201)


def _checklist_for(record):
    return OperationalChecklistItem.query.filter_by(
        record_id=record.id, organization_id=record.organization_id
    ).order_by(OperationalChecklistItem.position.asc(), OperationalChecklistItem.id.asc())


@operations_bp.get("/api/operations/<module_key>/<int:record_id>/checklist")
@login_required
@active_account_required
def get_checklist(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    items = _checklist_for(record).all()
    required = [item for item in items if item.required]
    completed = [item for item in required if item.completed]
    return api_success({
        "items": [item.to_dict() for item in items],
        "summary": {"total": len(items), "completed": sum(1 for item in items if item.completed),
                    "required": len(required), "required_completed": len(completed),
                    "ready": len(required) == len(completed)},
    })


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/checklist")
@login_required
@active_account_required
def create_checklist_item(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    data = _body()
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    if not title or len(title) > 240:
        return api_error("Checklist title is required and must be at most 240 characters.", 400)
    if len(description) > 5000:
        return api_error("Checklist description is too long.", 400)
    try:
        position = max(0, min(int(data.get("position", 0)), 100000))
    except (ValueError, TypeError):
        return api_error("position must be an integer.", 400)
    item = OperationalChecklistItem(
        organization_id=record.organization_id, record_id=record.id, title=title,
        description=description, required=bool(data.get("required", True)),
        position=position, created_by=current_user.id,
    )
    db.session.add(item)
    add_event(record, current_user.id, "checklist_item_added", title,
              details={"required": item.required, "position": position})
    db.session.commit()
    return api_success(item.to_dict(), "Checklist item created.", 201)


@operations_bp.patch("/api/operations/<module_key>/<int:record_id>/checklist/<int:item_id>")
@login_required
@active_account_required
def update_checklist_item(module_key, record_id, item_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    item = OperationalChecklistItem.query.filter_by(
        id=item_id, record_id=record.id, organization_id=record.organization_id
    ).first()
    if item is None:
        return api_error("Checklist item not found.", 404)
    data = _body()
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 240:
            return api_error("Checklist title must be 1–240 characters.", 400)
        item.title = title
    if "description" in data:
        description = str(data["description"])
        if len(description) > 5000:
            return api_error("Checklist description is too long.", 400)
        item.description = description
    if "required" in data:
        item.required = bool(data["required"])
    if "position" in data:
        try:
            item.position = max(0, min(int(data["position"]), 100000))
        except (ValueError, TypeError):
            return api_error("position must be an integer.", 400)
    if "evidence_reference" in data:
        item.evidence_reference = str(data["evidence_reference"] or "")[:1000]
    if "completed" in data:
        item.completed = bool(data["completed"])
        item.completed_by = current_user.id if item.completed else None
        item.completed_at = datetime.now(timezone.utc).replace(tzinfo=None) if item.completed else None
    record.updated_by = current_user.id
    record.version += 1
    add_event(record, current_user.id, "checklist_item_updated", item.title,
              details={"completed": item.completed, "required": item.required})
    db.session.commit()
    return api_success(item.to_dict(), "Checklist item updated.")


@operations_bp.delete("/api/operations/<module_key>/<int:record_id>/checklist/<int:item_id>")
@login_required
@active_account_required
def delete_checklist_item(module_key, record_id, item_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    if not can_manage(current_user) and record.created_by != current_user.id:
        return api_error("Only the record owner or a manager can remove checklist items.", 403)
    item = OperationalChecklistItem.query.filter_by(
        id=item_id, record_id=record.id, organization_id=record.organization_id
    ).first()
    if item is None:
        return api_error("Checklist item not found.", 404)
    title = item.title
    db.session.delete(item)
    add_event(record, current_user.id, "checklist_item_removed", title)
    db.session.commit()
    return api_success({"id": item_id}, "Checklist item removed.")


@operations_bp.get("/api/operations/<module_key>/<int:record_id>/approvals")
@login_required
@active_account_required
def get_approvals(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    rows = OperationalApproval.query.filter_by(
        record_id=record.id, organization_id=record.organization_id
    ).order_by(OperationalApproval.created_at.asc()).all()
    return api_success({"items": [row.to_dict() for row in rows],
                        "summary": {state: sum(1 for row in rows if row.decision == state)
                                    for state in ("pending", "approved", "rejected", "skipped")}})


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/approvals")
@login_required
@active_account_required
def create_approval(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    if not can_manage(current_user):
        return api_error("Manager or administrator role required to assign approvals.", 403)
    data = _body()
    stage_key = str(data.get("stage_key", "")).strip().lower()
    try:
        approver_id = int(data.get("approver_id"))
    except (ValueError, TypeError):
        return api_error("approver_id must be an integer.", 400)
    if not re.fullmatch(r"[a-z0-9_-]{2,60}", stage_key):
        return api_error("stage_key must be 2–60 lowercase letters, numbers, underscores or hyphens.", 400)
    approver = User.query.filter_by(id=approver_id, account_active=True).first()
    if approver is None:
        return api_error("Active approver not found.", 404)
    if approver.organization_id != record.organization_id:
        return api_error("Approver must belong to the same organization as the record.", 403)
    existing = OperationalApproval.query.filter_by(
        record_id=record.id, stage_key=stage_key, approver_id=approver_id
    ).first()
    if existing:
        return api_error("This approver is already assigned to the stage.", 409)
    approval = OperationalApproval(
        organization_id=record.organization_id, record_id=record.id, stage_key=stage_key,
        approver_id=approver_id, decision="pending", created_by=current_user.id,
    )
    db.session.add(approval)
    add_event(record, current_user.id, "approval_assigned", f"Approval assigned for stage {stage_key}.",
              details={"stage_key": stage_key, "approver_id": approver_id})
    db.session.commit()
    return api_success(approval.to_dict(), "Approval assigned.", 201)


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/approvals/<int:approval_id>/decision")
@login_required
@active_account_required
def decide_approval(module_key, record_id, approval_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    approval = OperationalApproval.query.filter_by(
        id=approval_id, record_id=record.id, organization_id=record.organization_id
    ).first()
    if approval is None:
        return api_error("Approval assignment not found.", 404)
    if approval.approver_id != current_user.id and not can_manage(current_user):
        return api_error("Only the assigned approver or a manager can decide.", 403)
    if approval.decision != "pending":
        return api_error("This approval already has a final decision.", 409)
    data = _body()
    decision = str(data.get("decision", "")).lower()
    if decision not in {"approved", "rejected", "skipped"}:
        return api_error("decision must be approved, rejected, or skipped.", 400)
    note = str(data.get("decision_note", "")).strip()
    if decision == "rejected" and not note:
        return api_error("A rejection reason is required.", 400)
    if len(note) > 5000:
        return api_error("Decision note is too long.", 400)
    approval.decision = decision
    approval.decision_note = note
    approval.decided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    record.updated_by = current_user.id
    record.version += 1
    add_event(record, current_user.id, "approval_decided", note,
              details={"stage_key": approval.stage_key, "decision": decision})
    db.session.commit()
    return api_success(approval.to_dict(), "Approval decision recorded.")


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/sla")
@login_required
@active_account_required
def record_sla_event(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    data = _body()
    event_type = str(data.get("event_type", "")).lower()
    if event_type not in {"started", "paused", "resumed", "acknowledged", "breached", "resolved"}:
        return api_error("Unsupported SLA event type.", 400)
    try:
        target = max(0, min(int(data.get("target_minutes", 0)), 525600))
        elapsed = max(0, min(int(data.get("elapsed_minutes", 0)), 525600))
    except (TypeError, ValueError):
        return api_error("SLA minutes must be integers.", 400)
    reason = str(data.get("reason", "")).strip()
    if len(reason) > 1000:
        return api_error("Reason must be at most 1,000 characters.", 400)
    if event_type == "breached" and not reason:
        return api_error("A breach reason is required.", 400)
    event = OperationalSLAEvent(
        organization_id=record.organization_id, record_id=record.id,
        event_type=event_type, target_minutes=target, elapsed_minutes=elapsed,
        reason=reason, actor_id=current_user.id,
    )
    db.session.add(event)
    add_event(record, current_user.id, "sla_" + event_type, reason,
              details={"target_minutes": target, "elapsed_minutes": elapsed})
    db.session.commit()
    return api_success(event.to_dict(), "SLA event recorded.", 201)


@operations_bp.get("/api/operations/<module_key>/<int:record_id>/sla")
@login_required
@active_account_required
def get_sla_history(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    rows = OperationalSLAEvent.query.filter_by(
        record_id=record.id, organization_id=record.organization_id
    ).order_by(OperationalSLAEvent.occurred_at.desc()).limit(250).all()
    return api_success({"items": [row.to_dict() for row in rows],
                        "breaches": sum(1 for row in rows if row.event_type == "breached")})


@operations_bp.post("/api/operations/<module_key>/bulk-transition")
@login_required
@active_account_required
def bulk_transition(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    if not can_manage(current_user):
        return api_error("Manager or administrator role required.", 403)
    data = _body()
    ids = data.get("ids")
    target = str(data.get("status", "")).lower()
    if not isinstance(ids, list) or not ids or len(ids) > 100:
        return api_error("ids must contain between 1 and 100 record IDs.", 400)
    if any(not isinstance(item, int) or item < 1 for item in ids):
        return api_error("Every record ID must be a positive integer.", 400)
    _, transition = DOMAIN_POLICIES[module_key]
    query = visible_query(OperationalRecord, current_user, module_key).filter(OperationalRecord.id.in_(set(ids)))
    records = query.all()
    if len(records) != len(set(ids)):
        return api_error("One or more records were not found in your organization.", 404)
    errors = []
    for record in records:
        message = transition(record.status, target, actor_role=current_user.role, payload=record.payload_json or {})
        if message:
            errors.append({"id": record.id, "key": record.record_key, "error": message})
    if errors:
        return {"ok": False, "error": "No records were changed because one or more transitions are invalid.",
                "items": errors}, 409
    for record in records:
        previous = record.status
        record.status = target
        record.updated_by = current_user.id
        record.version += 1
        add_event(record, current_user.id, "status_changed", "Bulk status update.",
                  from_status=previous, to_status=target, details={"bulk": True})
    db.session.commit()
    return api_success({"updated": len(records), "ids": ids}, "Bulk transition completed.")


@operations_bp.get("/api/operations/<module_key>/playbook")
@login_required
@active_account_required
def get_module_playbook(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    from app.services.operations_playbooks import get_playbook, response_sla, summarize_playbook
    playbook = get_playbook(module_key)
    priority = request.args.get("priority", "medium")
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    return api_success({"key": module_key, **playbook,
                        "summary": summarize_playbook(playbook),
                        "default_sla": response_sla(module_key, priority)})


@operations_bp.get("/operations/playbooks")
@login_required
@active_account_required
def operations_playbooks_page():
    from app.services.operations_playbooks import list_playbooks
    return render_template("operations_playbooks.html", playbooks=list_playbooks(),
                           modules=MODULES, active_page="operations")


@operations_bp.get("/api/operations/<module_key>/<int:record_id>/links")
@login_required
@active_account_required
def get_record_links(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    rows = OperationalLink.query.filter(
        or_(OperationalLink.source_record_id == record.id,
            OperationalLink.target_record_id == record.id),
        OperationalLink.organization_id == record.organization_id
    ).order_by(OperationalLink.created_at.desc()).all()
    return api_success({"items": [row.to_dict() for row in rows]})


@operations_bp.post("/api/operations/<module_key>/<int:record_id>/links")
@login_required
@active_account_required
def create_record_link(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    source, error = _record_or_error(module_key, record_id)
    if error:
        return error
    data = _body()
    try:
        target_id = int(data.get("target_record_id"))
    except (TypeError, ValueError):
        return api_error("target_record_id must be an integer.", 400)
    target = OperationalRecord.query.filter_by(id=target_id, archived=False).first()
    if target is None or target.organization_id != source.organization_id:
        return api_error("Target record not found in the same organization.", 404)
    if target.id == source.id:
        return api_error("A record cannot be linked to itself.", 400)
    link_type = str(data.get("link_type", "relates_to")).strip().lower()
    allowed = {"relates_to", "blocks", "blocked_by", "duplicates", "caused_by",
               "causes", "implements", "tests", "depends_on", "parent_of"}
    if link_type not in allowed:
        return api_error("Unsupported link_type.", 400)
    note = str(data.get("note", "")).strip()
    if len(note) > 2000:
        return api_error("Link note is too long.", 400)
    link = OperationalLink(
        organization_id=source.organization_id, source_record_id=source.id,
        target_record_id=target.id, link_type=link_type, note=note, created_by=current_user.id,
    )
    db.session.add(link)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        return api_error("This relationship already exists.", 409)
    add_event(source, current_user.id, "linked_record", f"{link_type} {target.record_key}.",
              details={"target_id": target.id, "target_module": target.module_key})
    add_event(target, current_user.id, "linked_record", f"{link_type} from {source.record_key}.",
              details={"source_id": source.id, "source_module": source.module_key})
    db.session.commit()
    return api_success(link.to_dict(), "Records linked.", 201)


@operations_bp.delete("/api/operations/<module_key>/<int:record_id>/links/<int:link_id>")
@login_required
@active_account_required
def delete_record_link(module_key, record_id, link_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    link = OperationalLink.query.filter(
        OperationalLink.id == link_id,
        OperationalLink.organization_id == record.organization_id,
        or_(OperationalLink.source_record_id == record.id, OperationalLink.target_record_id == record.id)
    ).first()
    if link is None:
        return api_error("Relationship not found.", 404)
    if not can_manage(current_user) and link.created_by != current_user.id:
        return api_error("Only the creator or a manager can remove this relationship.", 403)
    db.session.delete(link)
    add_event(record, current_user.id, "unlinked_record", f"Removed relationship {link.link_type}.",
              details={"link_id": link_id})
    db.session.commit()
    return api_success({"id": link_id}, "Relationship removed.")


def _policy_query():
    query = OperationalPolicy.query
    if current_user.role != ROLE_SUPER_ADMIN:
        query = query.filter_by(organization_id=current_user.organization_id)
    return query


@operations_bp.get("/operations/policies")
@login_required
@active_account_required
def operations_policies_page():
    if current_user.role not in {ROLE_ADMIN, ROLE_SUPER_ADMIN}:
        return render_template("unauthorized.html"), 403
    return render_template("operations_policies.html", modules=MODULES, active_page="operations")


@operations_bp.get("/api/operations/policies")
@login_required
@active_account_required
def list_operational_policies():
    if current_user.role not in {ROLE_ADMIN, ROLE_SUPER_ADMIN}:
        return api_error("Administrator role required.", 403)
    return api_success({"items": [row.to_dict() for row in _policy_query().order_by(
        OperationalPolicy.module_key.asc()).all()]})


@operations_bp.put("/api/operations/policies/<module_key>")
@login_required
@active_account_required
def upsert_operational_policy(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    if current_user.role not in {ROLE_ADMIN, ROLE_SUPER_ADMIN}:
        return api_error("Administrator role required.", 403)
    organization_id = current_user.organization_id
    data = _body()
    if current_user.role == ROLE_SUPER_ADMIN and data.get("organization_id"):
        try:
            organization_id = int(data["organization_id"])
        except (TypeError, ValueError):
            return api_error("organization_id must be an integer.", 400)
    if organization_id is None:
        return api_error("Organization is required.", 409)
    policy = OperationalPolicy.query.filter_by(
        organization_id=organization_id, module_key=module_key
    ).first()
    if policy is None:
        policy = OperationalPolicy(organization_id=organization_id, module_key=module_key,
                                   created_by=current_user.id, updated_by=current_user.id)
        db.session.add(policy)
    numeric_fields = ("acknowledgement_minutes", "resolution_minutes", "escalation_minutes")
    for field in numeric_fields:
        if field in data:
            try:
                value = int(data[field])
            except (TypeError, ValueError):
                return api_error(f"{field} must be an integer.", 400)
            if value < 0 or value > 525600:
                return api_error(f"{field} must be between 0 and 525600.", 400)
            setattr(policy, field, value)
    boolean_fields = ("high_risk_requires_approval", "evidence_required_for_close", "active")
    for field in boolean_fields:
        if field in data:
            if not isinstance(data[field], bool):
                return api_error(f"{field} must be a boolean.", 400)
            setattr(policy, field, data[field])
    role_fields = ("default_owner_role", "escalation_role")
    allowed_roles = {"employee", "team_lead", "hr", "admin", "super_admin"}
    for field in role_fields:
        if field in data:
            if data[field] not in allowed_roles:
                return api_error(f"{field} is not a supported role.", 400)
            setattr(policy, field, data[field])
    if "policy_notes" in data:
        notes = str(data["policy_notes"] or "")
        if len(notes) > 10000:
            return api_error("policy_notes is too long.", 400)
        policy.policy_notes = notes
    policy.updated_by = current_user.id
    db.session.commit()
    return api_success(policy.to_dict(), "Operational policy saved.")


@operations_bp.get("/api/operations/policies/effective/<module_key>")
@login_required
@active_account_required
def effective_operational_policy(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    policy = OperationalPolicy.query.filter_by(
        organization_id=current_user.organization_id, module_key=module_key, active=True
    ).first()
    from app.services.operations_playbooks import response_sla
    defaults = response_sla(module_key, request.args.get("priority", "medium"))
    return api_success({"module": module_key, "custom_policy": policy.to_dict() if policy else None,
                        "default_sla": defaults, "uses_custom_policy": policy is not None})


@operations_bp.post("/api/operations/<module_key>/import.csv")
@login_required
@active_account_required
def import_records_csv(module_key):
    """Validate a bounded CSV import and create all accepted rows atomically."""
    import csv
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    if not can_manage(current_user):
        return api_error("Manager or administrator role required for bulk import.", 403)
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return api_error("Choose a CSV file.", 400)
    if not uploaded.filename.lower().endswith(".csv"):
        return api_error("Only .csv files are supported.", 400)
    raw = uploaded.stream.read(2_000_001)
    if len(raw) > 2_000_000:
        return api_error("CSV file exceeds the 2 MB import limit.", 413)
    try:
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or "title" not in reader.fieldnames:
            return api_error("CSV must contain a title column.", 400)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        return api_error("CSV could not be decoded. Save as UTF-8 CSV and retry.", 400)
    if not rows or len(rows) > 200:
        return api_error("CSV must contain between 1 and 200 data rows.", 400)
    validate, _ = DOMAIN_POLICIES[module_key]
    prepared = []
    errors = []
    for index, row in enumerate(rows, start=2):
        payload, field_errors = validate(row, partial=False)
        title = str(row.get("title", "")).strip()
        if not title or len(title) > 240:
            field_errors["title"] = "Title is required and must be at most 240 characters."
        if field_errors:
            errors.append({"row": index, "fields": field_errors})
        else:
            prepared.append((row, payload))
    if errors:
        return {"ok": False, "error": "Import validation failed; no records were created.",
                "rows": errors[:100], "error_count": len(errors)}, 422
    organization_id = current_user.organization_id
    if organization_id is None:
        return api_error("Organization is required.", 409)
    created = []
    try:
        for row, payload in prepared:
            record, error = _make_record(module_key, row, payload)
            if error:
                raise ValueError("A row could not be created under current organization policy.")
            created.append(record)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Operational CSV import failed for module %s", module_key)
        return api_error("Import failed; transaction rolled back.", 500)
    return api_success({"created": len(created), "items": [row.to_dict(False) for row in created]},
                       "CSV import completed.", 201)



@operations_bp.get("/api/operations/<module_key>/<int:record_id>/controls")
@login_required
@active_account_required
def record_control_report(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    from app.services.operations_controls import evaluate_record_controls
    policy = OperationalPolicy.query.filter_by(
        organization_id=record.organization_id, module_key=module_key, active=True
    ).first()
    assessment = evaluate_record_controls(module_key, record, policy.to_dict() if policy else {})
    return api_success(assessment)


@operations_bp.get("/api/operations/analytics/controls")
@login_required
@active_account_required
def portfolio_control_report():
    from app.services.operations_controls import evaluate_record_controls, summarize_controls
    assessments = []
    by_module = []
    for module_key in MODULES:
        rows = visible_query(OperationalRecord, current_user, module_key).limit(1000).all()
        module_assessments = []
        for record in rows:
            policy = OperationalPolicy.query.filter_by(
                organization_id=record.organization_id, module_key=module_key, active=True
            ).first()
            module_assessments.append(evaluate_record_controls(
                module_key, record, policy.to_dict() if policy else {}
            ))
        assessments.extend(module_assessments)
        by_module.append({"module": module_key, **summarize_controls(module_assessments)})
    summary = summarize_controls(assessments)
    blocked = sorted(
        [item for item in assessments if item["blocked_by_critical_control"]],
        key=lambda item: (-item["critical_failures"], item["readiness_percent"])
    )[:250]
    return api_success({"summary": summary, "by_module": by_module, "blocked_records": blocked})


@operations_bp.get("/api/operations/analytics/controls.csv")
@login_required
@active_account_required
def export_control_report():
    from app.services.operations_controls import evaluate_record_controls, build_control_export_rows
    assessments = []
    for module_key in MODULES:
        rows = visible_query(OperationalRecord, current_user, module_key).limit(1000).all()
        for record in rows:
            assessments.append(evaluate_record_controls(module_key, record))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "record_key", "module", "status", "control_key", "control_label",
        "passed", "severity", "message"
    ])
    writer.writeheader()
    for row in build_control_export_rows(assessments):
        writer.writerow({key: _spreadsheet_safe(value) for key, value in row.items()})
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="tasknest-operational-controls.csv"'
    response.headers["Cache-Control"] = "no-store"
    return response



@operations_bp.get("/api/operations/<module_key>/csv-template")
@login_required
@active_account_required
def download_csv_template(module_key):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    module = __import__("app.services.operations_domains." + module_key.replace("-", "_"),
                        fromlist=["REQUIRED_FIELDS"])
    fields = ["title", "summary", "priority", "due_date"] + list(module.REQUIRED_FIELDS)
    fields = list(dict.fromkeys(fields))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)
    sample = {field: "" for field in fields}
    sample.update({"title": f"Example {MODULES[module_key]['title']} record",
                   "summary": "Replace this sample with a real record.",
                   "priority": "medium"})
    writer.writerow([sample[field] for field in fields])
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="tasknest-{module_key}-template.csv"'
    response.headers["Cache-Control"] = "no-store"
    return response


@operations_bp.get("/api/operations/analytics/data-quality")
@login_required
@active_account_required
def operations_data_quality_report():
    """Identify records missing fields or containing values that need review."""
    from collections import Counter
    findings = []
    per_module = []
    for module_key in MODULES:
        module = __import__("app.services.operations_domains." + module_key.replace("-", "_"),
                            fromlist=["REQUIRED_FIELDS"])
        required = list(module.REQUIRED_FIELDS)
        validator, _ = DOMAIN_POLICIES[module_key]
        rows = visible_query(OperationalRecord, current_user, module_key).limit(2000).all()
        counts = Counter()
        for record in rows:
            payload = dict(record.payload_json or {})
            if not payload.get("title"):
                payload["title"] = record.title
            _, errors = validator(payload, partial=False)
            for field, message in errors.items():
                counts[field] += 1
                if len(findings) < 1000:
                    findings.append({"module": module_key, "record_id": record.id,
                                     "record_key": record.record_key, "title": record.title,
                                     "status": record.status, "field": field, "message": message})
            if not record.owner_id and len(findings) < 1000:
                findings.append({"module": module_key, "record_id": record.id,
                                 "record_key": record.record_key, "title": record.title,
                                 "status": record.status, "field": "owner_id",
                                 "message": "Assign an accountable owner."})
                counts["owner_id"] += 1
        per_module.append({"module": module_key, "title": MODULES[module_key]["title"],
                           "records_scanned": len(rows), "required_fields": required,
                           "finding_count": sum(counts.values()),
                           "top_fields": [{"field": key, "count": value} for key, value in counts.most_common(8)]})
    return api_success({"total_findings": sum(item["finding_count"] for item in per_module),
                        "modules": per_module, "findings": findings})


@operations_bp.get("/api/operations/analytics/data-quality.csv")
@login_required
@active_account_required
def export_data_quality_report():
    response_data = operations_data_quality_report()
    response, status = response_data
    if status != 200:
        return response, status
    payload = response.get_json()
    data = payload.get("data", {})
    output = io.StringIO()
    fields = ["module", "record_id", "record_key", "title", "status", "field", "message"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in data.get("findings", []):
        writer.writerow({key: _spreadsheet_safe(item.get(key)) for key in fields})
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="tasknest-data-quality.csv"'
    response.headers["Cache-Control"] = "no-store"
    return response



@operations_bp.get("/api/operations/<module_key>/<int:record_id>/assessment")
@login_required
@active_account_required
def assess_record(module_key, record_id):
    """Return domain-specific risk, readiness, control, and next-action guidance."""
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    module_name = module_key.replace("-", "_")
    domain_module = __import__("app.services.operations_domains." + module_name,
                               fromlist=["analyze_" + module_name])
    analyzer = getattr(domain_module, "analyze_" + module_name)
    result = analyzer(record.payload_json or {}, status=record.status,
                      priority=record.priority,
                      due_date=record.due_date.isoformat() if record.due_date else None)
    recommendation_builder = getattr(domain_module, "recommendations_for_" + module_name, None)
    result["recommendations"] = recommendation_builder(
        record.payload_json or {}, status=record.status, priority=record.priority
    ) if recommendation_builder else []
    from app.services.operations_controls import evaluate_record_controls
    policy = OperationalPolicy.query.filter_by(
        organization_id=record.organization_id, module_key=module_key, active=True
    ).first()
    result["controls"] = evaluate_record_controls(module_key, record, policy.to_dict() if policy else {})
    result["record"] = {"id": record.id, "key": record.record_key,
                        "status": record.status, "version": record.version}
    result["assessed_at"] = datetime.now(timezone.utc).isoformat()
    return api_success(result)



@operations_bp.get("/api/operations/work-queue/recommend-owner")
@login_required
@active_account_required
def recommend_work_queue_owner():
    if not can_manage(current_user):
        return api_error("Manager or administrator role required.", 403)
    from app.services.operations_queue import recommend_owner
    users_query = User.query.filter_by(account_active=True)
    records_query = OperationalRecord.query.filter_by(archived=False)
    if current_user.role != ROLE_SUPER_ADMIN:
        users_query = users_query.filter_by(organization_id=current_user.organization_id)
        records_query = records_query.filter_by(organization_id=current_user.organization_id)
    users = users_query.limit(1000).all()
    records = records_query.order_by(OperationalRecord.updated_at.desc()).limit(5000).all()
    result = recommend_owner(users, records)
    return api_success(result)



@operations_bp.post("/api/operations/<module_key>/bulk-update")
@login_required
@active_account_required
def bulk_update_records(module_key):
    """Atomically update a small set of shared record fields with audit events."""
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    if not can_manage(current_user):
        return api_error("Manager or administrator role required.", 403)
    data = _body()
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 100:
        return api_error("ids must contain between 1 and 100 record IDs.", 400)
    if any(not isinstance(item, int) or item < 1 for item in ids):
        return api_error("Record IDs must be positive integers.", 400)
    updates = {}
    if "priority" in data and data["priority"] not in VALID_PRIORITIES:
        return api_error("Unsupported priority.", 400)
    if "priority" in data:
        updates["priority"] = data["priority"]
    if "due_date" in data:
        try:
            updates["due_date"] = parse_due_date(data.get("due_date"))
        except ValueError as exc:
            return api_error(str(exc), 400)
    if not updates:
        return api_error("Provide at least one supported field to update.", 400)
    query = visible_query(OperationalRecord, current_user, module_key).filter(
        OperationalRecord.id.in_(set(ids))
    )
    records = query.all()
    if len(records) != len(set(ids)):
        return api_error("One or more records were not found in your organization.", 404)
    for record in records:
        before = {}
        for field, value in updates.items():
            current = getattr(record, field)
            before[field] = current.isoformat() if hasattr(current, "isoformat") and current else current
            setattr(record, field, value)
        record.updated_by = current_user.id
        record.version += 1
        add_event(record, current_user.id, "bulk_fields_updated", "Bulk field update.",
                  details={"before": before, "updated_fields": list(updates.keys())})
    db.session.commit()
    return api_success({"updated": len(records), "fields": list(updates.keys()), "ids": ids},
                       "Bulk update completed.")



@operations_bp.get("/api/operations/work-queue/summary")
@login_required
@active_account_required
def operations_work_queue_summary():
    """Summarize organization-scoped queue health without loading record payloads."""
    from collections import Counter
    query = OperationalRecord.query.filter_by(archived=False)
    if current_user.role != ROLE_SUPER_ADMIN:
        if current_user.organization_id is None:
            return api_success({"total": 0, "open": 0, "overdue": 0, "unassigned": 0,
                                "critical": 0, "by_module": []})
        query = query.filter_by(organization_id=current_user.organization_id)
    rows = query.with_entities(
        OperationalRecord.module_key, OperationalRecord.status, OperationalRecord.priority,
        OperationalRecord.owner_id, OperationalRecord.due_date
    ).all()
    today = date.today()
    terminal = {"closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"}
    module_counts = {}
    summary = Counter()
    for module_key, status, priority, owner_id, due_date in rows:
        bucket = module_counts.setdefault(module_key, Counter())
        bucket["total"] += 1
        summary["total"] += 1
        if status not in terminal:
            bucket["open"] += 1
            summary["open"] += 1
            if not owner_id:
                bucket["unassigned"] += 1
                summary["unassigned"] += 1
            if due_date and due_date < today:
                bucket["overdue"] += 1
                summary["overdue"] += 1
            if priority == "critical":
                bucket["critical"] += 1
                summary["critical"] += 1
    return api_success({
        **dict(summary),
        "by_module": [{"module": key, "title": MODULES[key]["title"], **dict(values)}
                      for key, values in sorted(module_counts.items())],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })



@operations_bp.post("/api/operations/<module_key>/<int:record_id>/attachments")
@login_required
@active_account_required
def register_attachment_metadata(module_key, record_id):
    """Register metadata for an object already uploaded through a private storage adapter."""
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    if not can_manage(current_user) and record.created_by != current_user.id and record.owner_id != current_user.id:
        return api_error("Only the record owner, assignee, or a manager can register evidence.", 403)
    data = _body()
    display_name = str(data.get("display_name", "")).strip()
    storage_key = str(data.get("storage_key", "")).strip()
    content_type = str(data.get("content_type", "application/octet-stream")).strip().lower()
    evidence_type = str(data.get("evidence_type", "supporting")).strip().lower()
    if not display_name or len(display_name) > 240:
        return api_error("display_name is required and must be at most 240 characters.", 400)
    if (not storage_key or len(storage_key) > 500 or storage_key.startswith(("/", "\\")) or
            "\\" in storage_key or ".." in storage_key.split("/")):
        return api_error("storage_key must be a safe, relative object key.", 400)
    if not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", content_type):
        return api_error("content_type must be a MIME type.", 400)
    if evidence_type not in {"supporting", "test_evidence", "approval", "invoice", "screenshot", "other"}:
        return api_error("Unsupported evidence_type.", 400)
    try:
        byte_size = max(0, min(int(data.get("byte_size", 0)), 2_147_483_647))
    except (ValueError, TypeError):
        return api_error("byte_size must be an integer.", 400)
    digest = str(data.get("sha256_digest", "")).lower()
    if digest and not re.fullmatch(r"[a-f0-9]{64}", digest):
        return api_error("sha256_digest must be a SHA-256 hex digest.", 400)
    attachment = OperationalAttachment(
        organization_id=record.organization_id, record_id=record.id,
        uploaded_by=current_user.id, display_name=display_name, storage_key=storage_key,
        content_type=content_type, byte_size=byte_size, sha256_digest=digest,
        evidence_type=evidence_type,
    )
    db.session.add(attachment)
    add_event(record, current_user.id, "evidence_registered", display_name,
              details={"evidence_type": evidence_type, "byte_size": byte_size})
    db.session.commit()
    return api_success(attachment.to_dict(), "Evidence metadata registered.", 201)


@operations_bp.get("/api/operations/<module_key>/<int:record_id>/attachments")
@login_required
@active_account_required
def list_attachment_metadata(module_key, record_id):
    if module_key not in MODULES:
        return api_error("Unknown operations module.", 404)
    record, error = _record_or_error(module_key, record_id)
    if error:
        return error
    rows = OperationalAttachment.query.filter_by(
        record_id=record.id, organization_id=record.organization_id
    ).order_by(OperationalAttachment.created_at.desc()).all()
    return api_success({"items": [row.to_dict() for row in rows], "count": len(rows)})
