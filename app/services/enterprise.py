"""Reusable domain services for enterprise TaskNest modules."""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse
from app import db
from app.enterprise_models import (
    Project, ProjectMember, ProjectTask, TaskDependency, SavedView,
    CustomFieldDefinition, CustomFieldValue, WorkflowRule, WorkflowRun,
    WebhookEndpoint, WebhookDelivery,
)

def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def parse_json_value(value, fallback=None):
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list, bool, int, float)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback

def json_dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def slug_key(value, maximum=16):
    value = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip()).strip("-").upper()
    return (value or "PRJ")[:maximum]

def valid_public_https_url(value):
    """Reject non-HTTP schemes and local/private hostnames for webhook targets."""
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return False
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    if host in {"127.0.0.1", "::1", "0.0.0.0"}:
        return False
    return True

def project_for_user(project_id, user):
    project = db.session.get(Project, project_id)
    if not project:
        return None, "not_found"
    if not getattr(user, "is_authenticated", False):
        return None, "unauthorized"
    if not user.has_role("super_admin") and project.organization_id != user.organization_id:
        return None, "not_found"
    if user.has_role("super_admin") or user.has_role("admin") or project.owner_id == user.id:
        return project, None
    member = ProjectMember.query.filter_by(project_id=project.id, user_id=user.id).first()
    if member:
        return project, None
    return None, "forbidden"

def can_manage_project(project, user):
    if user.has_role("super_admin", "admin"):
        return True
    if project.owner_id == user.id:
        return True
    membership = ProjectMember.query.filter_by(project_id=project.id, user_id=user.id).first()
    return bool(membership and membership.role in {"manager", "owner"})

def detect_dependency_cycle(task_id, depends_on_id):
    """Return True when adding task -> prerequisite would close a dependency cycle."""
    if task_id == depends_on_id:
        return True
    graph = {}
    for row in TaskDependency.query.filter_by(organization_id=_org_for_task(task_id)).all():
        graph.setdefault(row.task_id, set()).add(row.depends_on_task_id)
    graph.setdefault(task_id, set()).add(depends_on_id)
    pending, visited = [depends_on_id], set()
    while pending:
        current = pending.pop()
        if current == task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(graph.get(current, ()))
    return False

def _org_for_task(task_id):
    from app.models import Task
    task = db.session.get(Task, task_id)
    return getattr(task, "organization_id", None) if task else None

def validate_custom_field(field_type, value, options=None):
    """Validate typed custom-field values and return (valid, normalized, error)."""
    options = options or []
    if value is None:
        return True, None, None
    if field_type == "text":
        if not isinstance(value, str) or len(value) > 4000:
            return False, None, "Value must be text up to 4000 characters."
        return True, value, None
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, None, "Value must be a number."
        return True, value, None
    if field_type == "boolean":
        if not isinstance(value, bool):
            return False, None, "Value must be true or false."
        return True, value, None
    if field_type == "date":
        if not isinstance(value, str):
            return False, None, "Value must be an ISO date string."
        try:
            normalized = datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return False, None, "Value must use YYYY-MM-DD format."
        return True, normalized, None
    if field_type == "select":
        if not isinstance(value, str) or value not in options:
            return False, None, "Value must match one of the configured options."
        return True, value, None
    if field_type == "multi_select":
        if not isinstance(value, list) or any(not isinstance(v, str) or v not in options for v in value):
            return False, None, "Value must be a list of configured options."
        if len(set(value)) != len(value):
            return False, None, "Duplicate options are not allowed."
        return True, value, None
    if field_type == "url":
        if not isinstance(value, str) or len(value) > 2048:
            return False, None, "Value must be a URL string."
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False, None, "URL must begin with http:// or https://."
        return True, value, None
    return False, None, "Unsupported custom-field type."

def validate_workflow_definition(trigger, conditions, actions):
    triggers = {"task.created", "task.status_changed", "task.assigned", "leave.submitted",
                "leave.approved", "meeting.created", "project.created"}
    allowed_conditions = {"equals", "not_equals", "contains", "in", "is_empty", "is_not_empty"}
    allowed_actions = {"create_notification", "write_audit_event", "set_task_priority"}
    if trigger not in triggers:
        return "Unsupported trigger event."
    if not isinstance(conditions, list) or len(conditions) > 20:
        return "Conditions must be a list containing at most 20 items."
    if not isinstance(actions, list) or not actions or len(actions) > 10:
        return "Actions must be a non-empty list containing at most 10 items."
    for condition in conditions:
        if not isinstance(condition, dict) or condition.get("operator") not in allowed_conditions:
            return "Each condition must use a supported operator."
        if not isinstance(condition.get("field"), str) or len(condition["field"]) > 80:
            return "Each condition needs a valid field name."
    for action in actions:
        if not isinstance(action, dict) or action.get("type") not in allowed_actions:
            return "Each action must use a supported, safe action type."
        if action["type"] == "set_task_priority" and action.get("priority") not in {"low", "medium", "high", "urgent"}:
            return "Task priority action must specify a valid priority."
    return None

def evaluate_conditions(conditions, payload):
    for condition in conditions:
        actual = payload
        for part in condition["field"].split("."):
            actual = actual.get(part) if isinstance(actual, dict) else None
        expected = condition.get("value")
        operator = condition["operator"]
        if operator == "equals" and actual != expected:
            return False
        if operator == "not_equals" and actual == expected:
            return False
        if operator == "contains" and (not isinstance(actual, (str, list)) or expected not in actual):
            return False
        if operator == "in" and actual not in (expected if isinstance(expected, list) else []):
            return False
        if operator == "is_empty" and actual not in (None, "", [], {}):
            return False
        if operator == "is_not_empty" and actual in (None, "", [], {}):
            return False
    return True

def queue_webhook_event(organization_id, event_type, payload, event_id=None):
    """Queue webhook deliveries transactionally; network I/O is intentionally external."""
    event_id = event_id or secrets.token_urlsafe(18)
    endpoints = WebhookEndpoint.query.filter_by(organization_id=organization_id, active=True).all()
    created = []
    for endpoint in endpoints:
        subscriptions = parse_json_value(endpoint.events_json, [])
        if event_type not in subscriptions and "*" not in subscriptions:
            continue
        existing = WebhookDelivery.query.filter_by(endpoint_id=endpoint.id, event_id=event_id).first()
        if existing:
            created.append(existing)
            continue
        delivery = WebhookDelivery(endpoint_id=endpoint.id, event_id=event_id,
                                   event_type=event_type, payload_json=json_dump(payload),
                                   status="pending", attempts=0)
        db.session.add(delivery)
        created.append(delivery)
    return created

def webhook_signature(secret, body):
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

def safe_webhook_events():
    return {"task.created", "task.updated", "task.status_changed", "leave.submitted",
            "leave.approved", "meeting.created", "project.created"}
