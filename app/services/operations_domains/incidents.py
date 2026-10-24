"""Business rules for incident management.

These policies intentionally do not perform database I/O. They can be exercised in
unit tests and reused by REST endpoints, background jobs, and administrative tools.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MODULE_KEY = 'incidents'
RECORD_PREFIX = 'INC'
ALLOWED_STATUSES = ['new', 'triaged', 'investigating', 'mitigated', 'resolved', 'closed']
TRANSITIONS = {'new': ['triaged', 'cancelled'], 'triaged': ['investigating', 'mitigated', 'cancelled'], 'investigating': ['mitigated', 'resolved'], 'mitigated': ['investigating', 'resolved'], 'resolved': ['closed', 'investigating'], 'closed': ['investigating']}
REQUIRED_FIELDS = ['impact', 'urgency', 'service', 'reported_by']
ENUM_FIELDS = {'impact': ['low', 'medium', 'high', 'critical'], 'urgency': ['low', 'medium', 'high', 'critical'], 'environment': ['development', 'test', 'staging', 'production']}


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


def validate_incidents(data, *, partial=False):
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


def transition_incidents(current_status, target_status, *, actor_role=None, payload=None):
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


def summarize_incidents(records):
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


def build_incidents_checklist(payload):
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


def normalize_incidents_search(filters):
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



def analyze_incident(payload, status="new", priority="medium", due_date=None):
    """Return incident triage guidance and service-impact indicators."""
    payload = payload or {}
    impact = payload.get("impact", "medium")
    urgency = payload.get("urgency", "medium")
    weights = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    score = weights.get(impact, 2) * weights.get(urgency, 2)
    severity = "critical" if score >= 12 else "high" if score >= 8 else "medium" if score >= 4 else "low"
    checks = {
        "service_identified": bool(payload.get("service")),
        "reporter_identified": bool(payload.get("reported_by")),
        "mitigation_documented": bool(payload.get("mitigation")),
        "root_cause_documented": bool(payload.get("root_cause")),
        "resolution_documented": bool(payload.get("resolution")) if status in {"resolved", "closed"} else True,
    }
    return {"severity": severity, "severity_score": score, "checks": checks,
            "missing_controls": [name for name, passed in checks.items() if not passed],
            "recommended_response": "incident_commander" if severity == "critical" else "service_owner" if severity == "high" else "team_triage",
            "postmortem_recommended": severity in {"critical", "high"} or bool(payload.get("postmortem_required")),
            "customer_communications": severity in {"critical", "high"}}


def incident_sla_targets(priority):
    """Map incident priority to default acknowledgement and mitigation targets."""
    return {"critical": {"acknowledge_minutes": 5, "mitigate_minutes": 60},
            "high": {"acknowledge_minutes": 15, "mitigate_minutes": 240},
            "medium": {"acknowledge_minutes": 60, "mitigate_minutes": 1440},
            "low": {"acknowledge_minutes": 240, "mitigate_minutes": 4320}}.get(priority, {"acknowledge_minutes": 60, "mitigate_minutes": 1440})


def recommendations_for_incidents(payload, status="new", priority="medium"):
    """Recommend the next safe operational actions for an incident."""
    payload = payload or {}
    actions = []
    if not payload.get("service"):
        actions.append({"key": "identify_service", "priority": "high", "action": "Identify the affected service and its owner."})
    if payload.get("impact") == "critical" or payload.get("urgency") == "critical":
        actions.append({"key": "declare", "priority": "critical", "action": "Assign an incident commander and start coordinated response."})
    if status in {"new", "triaged"} and not payload.get("mitigation"):
        actions.append({"key": "mitigate", "priority": "high", "action": "Document a reversible mitigation and its verification signal."})
    if status in {"resolved", "closed"} and not payload.get("root_cause"):
        actions.append({"key": "postmortem", "priority": "medium", "action": "Record root-cause evidence and preventive actions."})
    if not actions:
        actions.append({"key": "update_timeline", "priority": "low", "action": "Update the incident timeline and next stakeholder communication."})
    return actions
