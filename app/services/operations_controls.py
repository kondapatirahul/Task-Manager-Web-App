"""Operational control evaluation and reporting helpers.

The module converts saved records into explainable policy checks. It does not make
approval decisions automatically: it reports missing controls and leaves authorization
to the route-level workflow policy and a named human approver.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

TERMINAL_STATES = {"closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"}
HIGH_RISK_PRIORITIES = {"high", "critical"}


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _parse_day(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _number(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def evaluate_due_date(due_date, status, today=None):
    """Classify a record's due-date state without mutating the record."""
    today = today or date.today()
    due = _parse_day(due_date)
    if status in TERMINAL_STATES:
        return {"state": "terminal", "days": None, "overdue": False}
    if due is None:
        return {"state": "unscheduled", "days": None, "overdue": False}
    days = (due - today).days
    if days < 0:
        return {"state": "overdue", "days": days, "overdue": True}
    if days == 0:
        return {"state": "due_today", "days": 0, "overdue": False}
    if days <= 7:
        return {"state": "due_soon", "days": days, "overdue": False}
    return {"state": "scheduled", "days": days, "overdue": False}


def evaluate_record_controls(module_key, record, policy=None, today=None):
    """Build explainable controls for a record, its status, and its tenant policy."""
    payload = getattr(record, "payload_json", None) or {}
    policy = policy or {}
    today = today or date.today()
    due = evaluate_due_date(getattr(record, "due_date", None), getattr(record, "status", ""), today)
    controls = []
    def add(key, label, passed, severity="warning", message=""):
        controls.append({"key": key, "label": label, "passed": bool(passed),
                         "severity": severity, "message": message})
    add("owner", "Named owner", bool(getattr(record, "owner_id", None)),
        message="Assign a directly responsible owner." if not getattr(record, "owner_id", None) else "")
    add("due_date", "Due date", due["state"] != "unscheduled",
        message="Add a due date for accountable follow-up." if due["state"] == "unscheduled" else "")
    add("not_overdue", "Due-date health", not due["overdue"], "critical" if due["overdue"] else "info",
        message=f"Record is {abs(due['days'])} day(s) overdue." if due["overdue"] else "")
    if module_key == "incidents":
        add("service", "Affected service", _has_value(payload.get("service")))
        add("impact", "Impact assessment", _has_value(payload.get("impact")))
        add("mitigation", "Mitigation documented", _has_value(payload.get("mitigation")),
            message="Capture mitigation actions before resolving.")
        if payload.get("impact") == "critical" or payload.get("urgency") == "critical":
            add("incident_commander", "Incident commander", _has_value(payload.get("incident_commander")),
                "critical", "Critical incidents need a named incident commander.")
    elif module_key == "changes":
        add("implementation", "Implementation plan", _has_value(payload.get("implementation_plan")))
        add("rollback", "Rollback plan", _has_value(payload.get("rollback_plan")), "critical",
            "Do not approve without a recovery path.")
        add("test_evidence", "Test evidence", _has_value(payload.get("test_evidence")),
            message="Attach evidence before execution.")
        add("approval", "Approval policy", not policy.get("high_risk_requires_approval", True)
            or getattr(record, "priority", "medium") not in HIGH_RISK_PRIORITIES
            or getattr(record, "status", "") in {"approved", "scheduled", "implementing", "verified", "closed"},
            "critical", "High-risk work needs an explicit approval before implementation.")
    elif module_key == "quality":
        add("steps", "Reproducible test steps", _has_value(payload.get("steps")))
        add("expected", "Expected result", _has_value(payload.get("expected_result")))
        if getattr(record, "status", "") in {"passed", "failed"}:
            add("actual", "Actual result", _has_value(payload.get("actual_result")))
        if getattr(record, "status", "") == "failed":
            add("defect", "Linked defect", _has_value(payload.get("defect_id")), "critical",
                "Failed tests should link to a defect or documented exception.")
    elif module_key == "capacity":
        planned, available = _number(payload.get("planned_hours")), _number(payload.get("available_hours"))
        add("hours", "Hours are numeric", planned is not None and available is not None)
        if planned is not None and available is not None:
            add("utilization", "Capacity not exceeded", available > 0 and planned <= available,
                "critical", "Re-plan work or explicitly document the capacity exception.")
    elif module_key == "lifecycle":
        add("effective_date", "Effective date", _parse_day(payload.get("effective_date")) is not None)
        add("manager", "Manager identified", _has_value(payload.get("manager")))
        if payload.get("event_type") == "offboarding":
            add("access_revocation", "Access revocation plan", _has_value(payload.get("access_checklist")),
                "critical", "Offboarding must include a verifiable access-removal plan.")
    elif module_key == "data-governance":
        add("purpose", "Business purpose", _has_value(payload.get("purpose")), "critical")
        add("classification", "Data classification", _has_value(payload.get("data_classification")), "critical")
        add("expiry", "Expiry date", _parse_day(payload.get("expiry_date")) is not None, "critical")
        if payload.get("access_level") in {"write", "admin"}:
            add("elevated_access_approval", "Elevated access approval", _has_value(payload.get("approver")),
                "critical", "Write/admin access needs a named approver.")
    elif module_key == "procurement":
        quantity, unit_cost = _number(payload.get("quantity")), _number(payload.get("unit_cost"))
        valid_amount = quantity is not None and unit_cost is not None and quantity > 0 and unit_cost >= 0
        add("amount", "Valid estimated amount", valid_amount, "critical")
        add("justification", "Business justification", _has_value(payload.get("business_justification")))
        total = quantity * unit_cost if valid_amount else None
        if total is not None and total >= Decimal("100000"):
            add("quote", "Competitive quote", _has_value(payload.get("quote_reference")), "warning",
                "High-value procurement should include quote evidence under policy.")
    elif module_key == "baselines":
        start, finish = _parse_day(payload.get("planned_start")), _parse_day(payload.get("planned_finish"))
        add("schedule", "Valid schedule", bool(start and finish and finish >= start), "critical")
        add("scope", "Baseline scope", _has_value(payload.get("scope")), "critical")
        add("assumptions", "Planning assumptions", _has_value(payload.get("assumptions")))
        add("acceptance", "Acceptance criteria", _has_value(payload.get("acceptance_criteria")))
    elif module_key == "releases":
        add("version", "Release version", _has_value(payload.get("version")), "critical")
        add("tests", "Test evidence", _has_value(payload.get("test_evidence")), "critical")
        add("rollback", "Rollback plan", _has_value(payload.get("rollback_plan")), "critical")
        add("monitoring", "Monitoring plan", _has_value(payload.get("monitoring_plan")), "warning")
        if payload.get("target_environment") == "production":
            add("change_reference", "Approved change reference", _has_value(payload.get("change_reference")),
                "critical", "Production release must reference its approved change.")
    failed = [item for item in controls if not item["passed"]]
    critical = [item for item in failed if item["severity"] == "critical"]
    return {
        "module": module_key, "record_id": getattr(record, "id", None),
        "record_key": getattr(record, "record_key", None),
        "status": getattr(record, "status", None), "due": due,
        "controls": controls, "failed_count": len(failed),
        "critical_failures": len(critical),
        "readiness_percent": round((len(controls) - len(failed)) / len(controls) * 100) if controls else 100,
        "ready_for_review": not failed,
        "blocked_by_critical_control": bool(critical),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def summarize_controls(assessments):
    """Aggregate record control evaluations for a module or portfolio report."""
    records = list(assessments)
    total_controls = sum(len(item.get("controls", [])) for item in records)
    passed_controls = sum(sum(1 for control in item.get("controls", []) if control["passed"]) for item in records)
    critical = sum(item.get("critical_failures", 0) for item in records)
    overdue = sum(1 for item in records if item.get("due", {}).get("overdue"))
    blocked = sum(1 for item in records if item.get("blocked_by_critical_control"))
    return {
        "records": len(records), "controls": total_controls, "passed_controls": passed_controls,
        "control_pass_rate": round(passed_controls / total_controls * 100, 2) if total_controls else 100,
        "critical_failures": critical, "overdue_records": overdue, "blocked_records": blocked,
        "review_ready_records": sum(1 for item in records if item.get("ready_for_review")),
    }


def compare_control_assessments(previous, current):
    """Describe control changes between two assessments for a human reviewer."""
    previous_map = {item["key"]: item for item in (previous or {}).get("controls", [])}
    current_map = {item["key"]: item for item in (current or {}).get("controls", [])}
    added = sorted(set(current_map) - set(previous_map))
    removed = sorted(set(previous_map) - set(current_map))
    newly_failed = sorted(key for key in set(previous_map) & set(current_map)
                          if previous_map[key]["passed"] and not current_map[key]["passed"])
    newly_passed = sorted(key for key in set(previous_map) & set(current_map)
                          if not previous_map[key]["passed"] and current_map[key]["passed"])
    return {"added_controls": added, "removed_controls": removed,
            "newly_failed": newly_failed, "newly_passed": newly_passed,
            "changed": bool(added or removed or newly_failed or newly_passed)}


def build_control_export_rows(assessments):
    """Flatten controls for CSV export without exposing arbitrary payload JSON."""
    rows = []
    for assessment in assessments:
        for control in assessment.get("controls", []):
            rows.append({
                "record_key": assessment.get("record_key"),
                "module": assessment.get("module"),
                "status": assessment.get("status"),
                "control_key": control.get("key"),
                "control_label": control.get("label"),
                "passed": control.get("passed"),
                "severity": control.get("severity"),
                "message": control.get("message"),
            })
    return rows



def summarize_sla_observations(observations, target_minutes):
    """Summarize elapsed-minute observations against a proposed target.

    The function accepts simple dictionaries so it can be reused by a report, a
    CLI reconciliation job, or a future forecasting module without ORM coupling.
    Missing or invalid elapsed values are excluded and reported explicitly.
    """
    try:
        target = int(target_minutes)
    except (TypeError, ValueError):
        raise ValueError("target_minutes must be an integer")
    if target < 0 or target > 525600:
        raise ValueError("target_minutes must be between 0 and 525600")
    valid = []
    excluded = 0
    for observation in observations:
        elapsed = _number(observation.get("elapsed_minutes"))
        if elapsed is None or elapsed < 0:
            excluded += 1
            continue
        valid.append({
            "module": str(observation.get("module", "unknown")),
            "elapsed_minutes": float(elapsed),
            "event_type": str(observation.get("event_type", "unknown")),
        })
    elapsed_values = sorted(item["elapsed_minutes"] for item in valid)
    within = sum(1 for value in elapsed_values if value <= target)
    outside = len(elapsed_values) - within
    def percentile(values, fraction):
        if not values:
            return None
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * fraction))))
        return values[index]
    grouped = {}
    for item in valid:
        module = item["module"]
        bucket = grouped.setdefault(module, {"module": module, "samples": 0,
                                              "within_target": 0, "outside_target": 0,
                                              "elapsed_total": 0.0, "event_types": {}})
        bucket["samples"] += 1
        bucket["elapsed_total"] += item["elapsed_minutes"]
        bucket["within_target" if item["elapsed_minutes"] <= target else "outside_target"] += 1
        event_type = item["event_type"]
        bucket["event_types"][event_type] = bucket["event_types"].get(event_type, 0) + 1
    modules = []
    for bucket in grouped.values():
        bucket["average_elapsed_minutes"] = round(bucket["elapsed_total"] / bucket["samples"], 2)
        bucket["compliance_percent"] = round(bucket["within_target"] / bucket["samples"] * 100, 2)
        del bucket["elapsed_total"]
        modules.append(bucket)
    modules.sort(key=lambda item: (-item["outside_target"], -item["samples"], item["module"]))
    return {
        "target_minutes": target,
        "sample_count": len(valid),
        "excluded_count": excluded,
        "within_target": within,
        "outside_target": outside,
        "compliance_percent": round(within / len(valid) * 100, 2) if valid else None,
        "median_elapsed_minutes": percentile(elapsed_values, 0.5),
        "p90_elapsed_minutes": percentile(elapsed_values, 0.9),
        "maximum_elapsed_minutes": elapsed_values[-1] if elapsed_values else None,
        "minimum_elapsed_minutes": elapsed_values[0] if elapsed_values else None,
        "average_elapsed_minutes": round(sum(elapsed_values) / len(elapsed_values), 2) if elapsed_values else None,
        "modules": modules,
    }
