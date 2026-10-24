"""Business rules for data access governance.

These policies intentionally do not perform database I/O. They can be exercised in
unit tests and reused by REST endpoints, background jobs, and administrative tools.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MODULE_KEY = 'data-governance'
RECORD_PREFIX = 'DAR'
ALLOWED_STATUSES = ['draft', 'submitted', 'privacy_review', 'security_review', 'approved', 'provisioned', 'expired', 'rejected', 'revoked']
TRANSITIONS = {'draft': ['submitted', 'cancelled'], 'submitted': ['privacy_review', 'rejected'], 'privacy_review': ['security_review', 'rejected'], 'security_review': ['approved', 'rejected'], 'approved': ['provisioned', 'revoked'], 'provisioned': ['expired', 'revoked'], 'expired': ['submitted'], 'rejected': ['draft']}
REQUIRED_FIELDS = ['requester', 'dataset', 'purpose', 'data_classification', 'access_level', 'expiry_date']
ENUM_FIELDS = {'data_classification': ['public', 'internal', 'confidential', 'restricted'], 'access_level': ['read', 'write', 'admin'], 'legal_basis': ['contract', 'consent', 'legitimate_interest', 'legal_obligation', 'other']}


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


def validate_data_governance(data, *, partial=False):
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


def transition_data_governance(current_status, target_status, *, actor_role=None, payload=None):
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


def summarize_data_governance(records):
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


def build_data_governance_checklist(payload):
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


def normalize_data_governance_search(filters):
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



def analyze_data_request(payload, status="draft", priority="medium", due_date=None):
    """Calculate a coarse access-risk indicator and review-control checklist."""
    payload = payload or {}
    sensitivity = {"public": 1, "internal": 2, "confidential": 3, "restricted": 4}
    privilege = {"read": 1, "write": 2, "admin": 4}
    score = sensitivity.get(payload.get("data_classification"), 2) * privilege.get(payload.get("access_level"), 1)
    checks = {
        "requester": bool(payload.get("requester")),
        "dataset": bool(payload.get("dataset")),
        "purpose": bool(payload.get("purpose")),
        "classification": bool(payload.get("data_classification")),
        "legal_basis": bool(payload.get("legal_basis")),
        "expiry": bool(payload.get("expiry_date")),
        "approver": bool(payload.get("approver")),
    }
    level = "critical" if score >= 12 else "high" if score >= 8 else "medium" if score >= 4 else "low"
    return {"risk_score": score, "risk_level": level, "checks": checks,
            "missing_controls": [key for key, passed in checks.items() if not passed],
            "requires_security_review": level in {"high", "critical"},
            "least_privilege_recommendation": "read" if payload.get("access_level") in {"write", "admin"} else None}


def retention_review_due(last_review, interval_days=365, today=None):
    """Return a deterministic retention-review status for a date string."""
    from datetime import date, timedelta
    today = today or date.today()
    try:
        reviewed = date.fromisoformat(last_review) if last_review else None
    except ValueError:
        reviewed = None
    if reviewed is None:
        return {"due": True, "next_review": None, "reason": "no_valid_review_date"}
    next_review = reviewed + timedelta(days=max(1, min(int(interval_days), 3650)))
    return {"due": next_review <= today, "next_review": next_review.isoformat(),
            "days_remaining": (next_review - today).days}


def recommendations_for_data_governance(payload, status="draft", priority="medium"):
    """Recommend least-privilege data access controls and revalidation."""
    payload = payload or {}
    actions = []
    if not payload.get("purpose"):
        actions.append({"key": "purpose", "priority": "critical", "action": "Write a specific business purpose for the access."})
    if payload.get("access_level") in {"write", "admin"} and not payload.get("approver"):
        actions.append({"key": "approver", "priority": "critical", "action": "Name the data owner and obtain elevated-access approval."})
    if not payload.get("expiry_date"):
        actions.append({"key": "expiry", "priority": "high", "action": "Set an expiry date and review owner."})
    if payload.get("data_classification") in {"confidential", "restricted"}:
        actions.append({"key": "controls", "priority": "high", "action": "Confirm audit logging, data handling, and approved storage controls."})
    if not payload.get("legal_basis"):
        actions.append({"key": "legal_basis", "priority": "high", "action": "Record the applicable legal basis or approved policy reference."})
    return actions or [{"key": "review", "priority": "low", "action": "Schedule revalidation before access expiry."}]
