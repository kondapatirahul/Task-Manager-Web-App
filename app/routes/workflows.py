"""Safe, declarative workflow rules and idempotent event execution."""
import json
import secrets
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import Task, AuditLog
from app.enterprise_models import WorkflowRule, WorkflowRun
from app.routes.utils import active_account_required, api_error, api_success, log_audit, send_notification
from app.services.enterprise import (validate_workflow_definition, evaluate_conditions,
                                     queue_webhook_event, json_dump)

workflows_bp = Blueprint("workflows", __name__, url_prefix="/api/enterprise/workflows")

def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}

def _scope():
    return WorkflowRule.query.filter_by(organization_id=current_user.organization_id)

@workflows_bp.get("")
@login_required
@active_account_required
def list_rules():
    query = _scope()
    if not current_user.has_role("admin", "super_admin", "hr"):
        query = query.filter_by(creator_id=current_user.id)
    return api_success([r.to_dict() for r in query.order_by(WorkflowRule.updated_at.desc()).limit(200).all()])

@workflows_bp.post("")
@login_required
@active_account_required
def create_rule():
    if not current_user.has_role("admin", "super_admin", "hr", "team_lead"):
        return api_error("Workflow-management permission required.", 403)
    data = _body()
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 140:
        return api_error("name is required and must be at most 140 characters.", 400)
    trigger = data.get("trigger_event")
    conditions = data.get("conditions", [])
    actions = data.get("actions", [])
    error = validate_workflow_definition(trigger, conditions, actions)
    if error:
        return api_error(error, 400)
    row = WorkflowRule(organization_id=current_user.organization_id, creator_id=current_user.id,
                       name=name, description=str(data.get("description", ""))[:4000],
                       trigger_event=trigger, conditions_json=json.dumps(conditions),
                       actions_json=json.dumps(actions), enabled=bool(data.get("enabled", True)))
    db.session.add(row)
    db.session.commit()
    log_audit("workflow.created", "workflow_rule", row.id, {"trigger": trigger})
    return api_success(row.to_dict(), "Workflow rule created.", 201)

@workflows_bp.get("/<int:rule_id>")
@login_required
@active_account_required
def get_rule(rule_id):
    row = _scope().filter_by(id=rule_id).first()
    if not row:
        return api_error("Workflow rule not found.", 404)
    if row.creator_id != current_user.id and not current_user.has_role("admin", "super_admin", "hr"):
        return api_error("Workflow rule not found.", 404)
    return api_success(row.to_dict())

@workflows_bp.patch("/<int:rule_id>")
@login_required
@active_account_required
def update_rule(rule_id):
    row = _scope().filter_by(id=rule_id).first()
    if not row:
        return api_error("Workflow rule not found.", 404)
    if row.creator_id != current_user.id and not current_user.has_role("admin", "super_admin", "hr"):
        return api_error("You cannot update this workflow.", 403)
    data = _body()
    trigger = data.get("trigger_event", row.trigger_event)
    try:
        conditions = data.get("conditions", json.loads(row.conditions_json))
        actions = data.get("actions", json.loads(row.actions_json))
    except (ValueError, TypeError):
        return api_error("Stored workflow configuration is invalid; update conditions and actions together.", 409)
    error = validate_workflow_definition(trigger, conditions, actions)
    if error:
        return api_error(error, 400)
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 140:
            return api_error("name must be at most 140 characters.", 400)
        row.name = name
    if "description" in data:
        row.description = str(data["description"])[:4000]
    row.trigger_event = trigger
    row.conditions_json = json.dumps(conditions)
    row.actions_json = json.dumps(actions)
    if "enabled" in data:
        row.enabled = bool(data["enabled"])
    db.session.commit()
    log_audit("workflow.updated", "workflow_rule", row.id, {"fields": sorted(data.keys())})
    return api_success(row.to_dict(), "Workflow rule updated.")

@workflows_bp.delete("/<int:rule_id>")
@login_required
@active_account_required
def delete_rule(rule_id):
    row = _scope().filter_by(id=rule_id).first()
    if not row:
        return api_error("Workflow rule not found.", 404)
    if row.creator_id != current_user.id and not current_user.has_role("admin", "super_admin", "hr"):
        return api_error("You cannot delete this workflow.", 403)
    db.session.delete(row)
    db.session.commit()
    log_audit("workflow.deleted", "workflow_rule", rule_id, {})
    return api_success({"deleted": True})

def _run_actions(rule, payload):
    """Execute only allow-listed, data-driven actions; never eval arbitrary code."""
    actions = json.loads(rule.actions_json or "[]")
    completed = []
    for action in actions:
        kind = action["type"]
        if kind == "create_notification":
            target = action.get("user_id", payload.get("actor_id"))
            try:
                target = int(target)
            except (TypeError, ValueError):
                completed.append({"type": kind, "status": "skipped", "reason": "no valid recipient"})
                continue
            message = str(action.get("message", "A TaskNest workflow was triggered."))[:500]
            notification = send_notification(target, str(action.get("title", rule.name))[:120],
                                             message, link=action.get("link"),
                                             notif_type="workflow",
                                             idempotency_key=f"workflow:{rule.id}:{payload.get('event_id')}:{target}")
            completed.append({"type": kind, "status": "created" if notification else "failed"})
        elif kind == "write_audit_event":
            entry = AuditLog(organization_id=rule.organization_id,
                             user_id=payload.get("actor_id"), action="workflow.action",
                             entity_type=str(payload.get("entity_type", "workflow"))[:50],
                             entity_id=payload.get("entity_id"),
                             details={"rule_id": rule.id, "label": str(action.get("label", rule.name))[:100]})
            db.session.add(entry)
            completed.append({"type": kind, "status": "queued"})
        elif kind == "set_task_priority":
            try:
                task_id = int(payload.get("entity_id"))
            except (TypeError, ValueError):
                completed.append({"type": kind, "status": "skipped", "reason": "event has no task id"})
                continue
            task = Task.query.filter_by(id=task_id, organization_id=rule.organization_id).first()
            if task and payload.get("entity_type") == "task":
                task.priority = action["priority"]
                completed.append({"type": kind, "status": "updated", "task_id": task.id})
            else:
                completed.append({"type": kind, "status": "skipped", "reason": "task not found"})
    return completed

@workflows_bp.post("/dispatch")
@login_required
@active_account_required
def dispatch_event():
    """Dispatch a domain event through matching enabled rules, with idempotent runs."""
    data = _body()
    event_type = data.get("event_type")
    payload = data.get("payload")
    if not isinstance(event_type, str) or not isinstance(payload, dict):
        return api_error("event_type and object payload are required.", 400)
    if len(json.dumps(payload, default=str)) > 20000:
        return api_error("payload cannot exceed 20 KB.", 413)
    event_id = str(data.get("event_id") or secrets.token_urlsafe(18))[:80]
    if payload.get("organization_id") != current_user.organization_id and not current_user.has_role("super_admin"):
        return api_error("Event organization does not match your organization.", 403)
    rules = WorkflowRule.query.filter_by(organization_id=current_user.organization_id,
                                         trigger_event=event_type, enabled=True).all()
    results = []
    for rule in rules:
        conditions = json.loads(rule.conditions_json or "[]")
        if not evaluate_conditions(conditions, payload):
            continue
        existing = WorkflowRun.query.filter_by(rule_id=rule.id, event_id=event_id).first()
        if existing:
            results.append(existing.to_dict())
            continue
        run = WorkflowRun(rule_id=rule.id, event_id=event_id,
                          entity_type=str(payload.get("entity_type", "unknown"))[:32],
                          entity_id=payload.get("entity_id"), status="running")
        db.session.add(run)
        db.session.flush()
        try:
            detail = _run_actions(rule, {**payload, "event_id": event_id})
            run.status = "completed"
            run.detail_json = json.dumps({"actions": detail})
            run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            results.append(run.to_dict())
        except Exception as exc:
            run.status = "failed"
            run.detail_json = json.dumps({"error": type(exc).__name__})
            run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            results.append(run.to_dict())
    queue_webhook_event(current_user.organization_id, event_type, {"event_id": event_id, "type": event_type, "data": payload}, event_id)
    db.session.commit()
    return api_success({"event_id": event_id, "matched_runs": results}, "Event dispatched.")

@workflows_bp.get("/runs")
@login_required
@active_account_required
def list_runs():
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
    except ValueError:
        return api_error("limit must be an integer.", 400)
    query = WorkflowRun.query.join(WorkflowRule, WorkflowRun.rule_id == WorkflowRule.id).filter(
        WorkflowRule.organization_id == current_user.organization_id)
    if not current_user.has_role("admin", "super_admin", "hr"):
        query = query.filter(WorkflowRule.creator_id == current_user.id)
    rows = query.order_by(WorkflowRun.started_at.desc()).limit(limit).all()
    return api_success([r.to_dict() for r in rows])
