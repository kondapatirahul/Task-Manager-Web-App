"""Business rules for employee lifecycle.

These policies intentionally do not perform database I/O. They can be exercised in
unit tests and reused by REST endpoints, background jobs, and administrative tools.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

MODULE_KEY = 'lifecycle'
RECORD_PREFIX = 'HRL'
ALLOWED_STATUSES = ['draft', 'requested', 'manager_review', 'hr_review', 'in_progress', 'completed', 'cancelled']
TRANSITIONS = {'draft': ['requested', 'cancelled'], 'requested': ['manager_review', 'cancelled'], 'manager_review': ['hr_review', 'cancelled'], 'hr_review': ['in_progress', 'manager_review'], 'in_progress': ['completed', 'hr_review']}
REQUIRED_FIELDS = ['employee_name', 'employee_email', 'event_type', 'effective_date', 'manager']
ENUM_FIELDS = {'event_type': ['onboarding', 'role_change', 'transfer', 'offboarding'], 'employment_type': ['full_time', 'part_time', 'contractor', 'intern'], 'checklist_status': ['not_started', 'in_progress', 'done', 'blocked']}


def _as_decimal(value, field, errors, *, minimum=Decimal("0"), maximum=None):
    """Parse monetary/numeric inputs without binary floating-point surprises."""
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors[field] = "Enter a valid decimal number."
        return None
    if not result.is_finite():
        errors[field] = "Number must be finite."
        return None
    if result < minimum:
        errors[field] = f"Value must be at least {minimum}."
    if maximum is not None and result > maximum:
        errors[field] = f"Value must not exceed {maximum}."
    return result


def _as_date(value, field, errors):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        errors[field] = "Use YYYY-MM-DD date format."
        return None


def validate_lifecycle(data, *, partial=False):
    """Validate user-supplied fields and return (normalized_fields, errors)."""
    if not isinstance(data, dict):
        return {}, {"body": "A JSON object is required."}
    errors = {}
    normalized = {}
    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if not partial and (value is None or (isinstance(value, str) and not value.strip())):
            errors[field] = f"{field.replace('_', ' ').capitalize()} is required."
        elif value is not None:
            normalized[field] = value.strip() if isinstance(value, str) else value
    if MODULE_KEY == "lifecycle" and data.get("employee_email"):
        email = str(data.get("employee_email")).strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors["employee_email"] = "Enter a valid email address."
        else:
            normalized["employee_email"] = email.lower()
    for field, allowed in ENUM_FIELDS.items():
        value = data.get(field)
        if value not in (None, ""):
            if value not in allowed:
                errors[field] = "Choose one of: " + ", ".join(allowed) + "."
            else:
                normalized[field] = value
    for field in ("planned_start", "planned_end", "period_start", "period_end",
                  "effective_date", "expiry_date", "planned_finish", "due_date"):
        if field in data:
            parsed = _as_date(data.get(field), field, errors)
            if parsed is not None:
                normalized[field] = parsed.isoformat()
    for field in ("quantity", "unit_cost", "planned_hours", "available_hours",
                  "cost_baseline", "estimated_impact", "actual_impact", "probability"):
        if field in data:
            value = _as_decimal(data.get(field), field, errors,
                                minimum=Decimal("0"),
                                maximum=Decimal("100") if field == "probability" else None)
            if value is not None:
                normalized[field] = str(value)
    for field in ("title", "summary", "description", "purpose", "scope", "assumptions",
                  "implementation_plan", "rollback_plan", "release_notes", "test_evidence",
                  "business_justification", "expected_result", "steps", "mitigation_plan"):
        if field in data:
            value = data.get(field)
            if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
                errors[field] = "Unsupported value type."
            elif isinstance(value, str) and len(value) > 20000:
                errors[field] = "Field exceeds 20,000 characters."
            else:
                normalized[field] = value
    for field in ("planned_start", "planned_end", "period_start", "period_end",
                  "effective_date", "expiry_date", "planned_finish"):
        if field in normalized and field in data:
            pass
    if "planned_start" in normalized and "planned_end" in normalized:
        if normalized["planned_end"] < normalized["planned_start"]:
            errors["planned_end"] = "End date cannot precede start date."
    if "period_start" in normalized and "period_end" in normalized:
        if normalized["period_end"] < normalized["period_start"]:
            errors["period_end"] = "Period end cannot precede period start."
    if MODULE_KEY == "procurement":
        quantity = Decimal(normalized.get("quantity", "0"))
        unit_cost = Decimal(normalized.get("unit_cost", "0"))
        normalized["line_total"] = str((quantity * unit_cost).quantize(Decimal("0.01")))
    if MODULE_KEY == "capacity":
        planned = Decimal(normalized.get("planned_hours", "0"))
        available = Decimal(normalized.get("available_hours", "0"))
        normalized["utilization_percent"] = (
            str((planned / available * Decimal("100")).quantize(Decimal("0.01")))
            if available > 0 else None
        )
        if available > 0 and planned > available:
            normalized["over_capacity"] = True
        else:
            normalized["over_capacity"] = False
    if MODULE_KEY == "incidents":
        impact = normalized.get("impact", data.get("impact", "medium"))
        urgency = normalized.get("urgency", data.get("urgency", "medium"))
        matrix = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        score = matrix.get(impact, 2) * matrix.get(urgency, 2)
        normalized["severity_score"] = score
        normalized["severity"] = "critical" if score >= 12 else "high" if score >= 8 else "medium" if score >= 4 else "low"
    if MODULE_KEY == "data-governance":
        expiry = normalized.get("expiry_date")
        if expiry and expiry < date.today().isoformat():
            errors["expiry_date"] = "Expiry date must be today or later."
    return normalized, errors


def transition_lifecycle(current_status, target_status, *, actor_role=None, payload=None):
    """Validate a state transition and return an explanatory error or None."""
    if target_status not in ALLOWED_STATUSES:
        return "Unknown target status."
    if target_status == current_status:
        return None
    allowed = TRANSITIONS.get(current_status, [])
    if target_status not in allowed:
        return f"Cannot move from {current_status} to {target_status}."
    elevated = {"approved", "finance_review", "security_review", "privacy_review",
                "verified", "released", "provisioned", "closed", "completed"}
    if target_status in elevated and actor_role not in {"admin", "super_admin", "hr", "team_lead"}:
        return "This transition requires a manager or administrator."
    payload = payload or {}
    if MODULE_KEY == "changes" and target_status == "approved":
        if not payload.get("rollback_plan") or not payload.get("implementation_plan"):
            return "An implementation plan and rollback plan are required before approval."
    if MODULE_KEY == "releases" and target_status == "approved" and not payload.get("test_evidence"):
        return "Test evidence is required before release approval."
    if MODULE_KEY == "procurement" and target_status == "approved":
        if not payload.get("business_justification"):
            return "Business justification is required before approval."
    if MODULE_KEY == "data-governance" and target_status == "provisioned":
        if not payload.get("expiry_date"):
            return "Access expiry must be defined before provisioning."
    return None


def summarize_lifecycle(records):
    """Return operational KPIs for a collection of normalized record dictionaries."""
    summary = {"total": len(records), "statuses": {}, "priorities": {}, "overdue": 0}
    today = date.today().isoformat()
    for item in records:
        status = item.get("status", "unknown")
        priority = item.get("priority", "medium")
        summary["statuses"][status] = summary["statuses"].get(status, 0) + 1
        summary["priorities"][priority] = summary["priorities"].get(priority, 0) + 1
        due = item.get("due_date")
        if due and due < today and status not in {"closed", "completed", "cancelled", "released"}:
            summary["overdue"] += 1
    return summary


def build_lifecycle_checklist(payload):
    """Build a deterministic readiness checklist for transition and review screens."""
    payload = payload or {}
    checklist = []
    for field in REQUIRED_FIELDS:
        value = payload.get(field)
        checklist.append({"field": field, "complete": value not in (None, "", [], {})})
    if MODULE_KEY in {"changes", "releases"}:
        for field in ("implementation_plan", "rollback_plan", "test_evidence"):
            if field in payload or MODULE_KEY == "releases":
                checklist.append({"field": field, "complete": bool(payload.get(field))})
    completed = sum(1 for item in checklist if item["complete"])
    return {
        "items": checklist,
        "complete": completed,
        "total": len(checklist),
        "percent": round(completed / len(checklist) * 100) if checklist else 100,
        "ready": completed == len(checklist),
    }


def normalize_lifecycle_search(filters):
    """Whitelist supported query filters and normalize them for repository code."""
    normalized = {}
    if filters.get("status") in ALLOWED_STATUSES:
        normalized["status"] = filters["status"]
    if filters.get("priority") in {"low", "medium", "high", "critical"}:
        normalized["priority"] = filters["priority"]
    query = str(filters.get("q", "")).strip()
    if query:
        normalized["q"] = query[:120]
    if filters.get("owner_id"):
        try:
            normalized["owner_id"] = max(1, int(filters["owner_id"]))
        except (ValueError, TypeError):
            pass
    return normalized



def analyze_lifecycle(payload, status="draft", priority="medium", due_date=None):
    """Return a lifecycle checklist plan with access-sensitive offboarding controls."""
    payload = payload or {}
    event_type = payload.get("event_type", "onboarding")
    onboarding = event_type == "onboarding"
    offboarding = event_type == "offboarding"
    common = ["manager_confirmation", "employee_communication", "hr_record_update"]
    if onboarding:
        tasks = ["identity_verification", "equipment_assignment", "least_privilege_access",
                 "security_training", "payroll_setup", "team_introduction"] + common
    elif offboarding:
        tasks = ["manager_confirmation", "access_revocation", "device_return",
                 "knowledge_transfer", "payroll_closeout", "record_retention_review"]
    else:
        tasks = ["manager_confirmation", "role_permission_review", "directory_update",
                 "employee_communication", "hr_record_update"]
    return {"event_type": event_type, "checklist_template": tasks,
            "access_review_required": offboarding or event_type in {"transfer", "role_change"},
            "effective_date_present": bool(payload.get("effective_date")),
            "manager_present": bool(payload.get("manager")),
            "sensitive_workflow": offboarding or event_type == "role_change"}


def lifecycle_access_delta(old_permissions, new_permissions):
    """Identify access additions and removals during role changes and transfers."""
    old_set, new_set = set(old_permissions or []), set(new_permissions or [])
    return {"added": sorted(new_set - old_set), "removed": sorted(old_set - new_set),
            "unchanged": sorted(old_set & new_set),
            "net_change": len(new_set - old_set) - len(old_set - new_set)}


def recommendations_for_lifecycle(payload, status="draft", priority="medium"):
    """Recommend lifecycle controls according to the employee event type."""
    payload = payload or {}
    event_type = payload.get("event_type")
    actions = []
    if not payload.get("manager"):
        actions.append({"key": "manager", "priority": "high", "action": "Assign the responsible manager."})
    if not payload.get("effective_date"):
        actions.append({"key": "effective_date", "priority": "high", "action": "Confirm the approved effective date with HR."})
    if event_type == "offboarding" and not payload.get("access_checklist"):
        actions.append({"key": "access", "priority": "critical", "action": "Define the system access revocation checklist."})
    if event_type == "onboarding" and not payload.get("training_plan"):
        actions.append({"key": "training", "priority": "medium", "action": "Assign required security and role training."})
    if event_type in {"transfer", "role_change"}:
        actions.append({"key": "access_review", "priority": "high", "action": "Compare old and new permissions and remove obsolete access."})
    return actions or [{"key": "completion", "priority": "low", "action": "Review checklist evidence and close remaining exceptions."}]
