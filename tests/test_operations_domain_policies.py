"""Unit tests for operational domain validation and state transitions."""
import importlib
import pytest

MODULES = {
    "incidents": {
        "valid": {"title": "API outage", "service": "Public API", "impact": "high",
                  "urgency": "critical", "reported_by": "Monitoring"},
        "invalid": {"title": "API outage", "service": "", "impact": "unknown",
                    "urgency": "critical", "reported_by": ""},
    },
    "changes": {
        "valid": {"title": "Rotate certificates", "change_type": "normal", "risk_level": "medium",
                  "planned_start": "2026-11-01", "planned_end": "2026-11-02",
                  "implementation_plan": "Deploy certificate", "rollback_plan": "Restore prior certificate"},
        "invalid": {"title": "Rotate certificates", "change_type": "normal", "risk_level": "medium",
                    "planned_start": "2026-11-02", "planned_end": "2026-11-01",
                    "implementation_plan": "", "rollback_plan": ""},
    },
    "quality": {
        "valid": {"title": "Login regression", "test_type": "regression", "test_environment": "test",
                  "steps": "1. Sign in", "expected_result": "Dashboard is shown", "owner": "QA"},
        "invalid": {"title": "Login regression", "test_type": "unknown", "test_environment": "test",
                    "steps": "", "expected_result": "", "owner": ""},
    },
    "capacity": {
        "valid": {"title": "November capacity", "period_start": "2026-11-01",
                  "period_end": "2026-11-30", "team": "Platform", "planned_hours": 80,
                  "available_hours": 100},
        "invalid": {"title": "November capacity", "period_start": "2026-11-30",
                    "period_end": "2026-11-01", "team": "", "planned_hours": -1,
                    "available_hours": 0},
    },
    "lifecycle": {
        "valid": {"title": "New employee", "employee_name": "Example Person",
                  "employee_email": "person@example.com", "event_type": "onboarding",
                  "effective_date": "2026-11-01", "manager": "Team Lead"},
        "invalid": {"title": "New employee", "employee_name": "", "employee_email": "bad",
                    "event_type": "invalid", "effective_date": "not-a-date", "manager": ""},
    },
    "data_governance": {
        "valid": {"title": "Analytics access", "requester": "Analyst", "dataset": "Usage",
                  "purpose": "Monthly report", "data_classification": "internal",
                  "access_level": "read", "legal_basis": "contract", "expiry_date": "2026-12-01"},
        "invalid": {"title": "Analytics access", "requester": "", "dataset": "",
                    "purpose": "", "data_classification": "secret", "access_level": "root",
                    "legal_basis": "unknown", "expiry_date": "2020-01-01"},
    },
    "procurement": {
        "valid": {"title": "Laptop purchase", "supplier": "Supplier Ltd",
                  "description": "Laptop", "quantity": 2, "unit_cost": "75000",
                  "currency": "INR", "business_justification": "Replacement"},
        "invalid": {"title": "Laptop purchase", "supplier": "", "description": "",
                    "quantity": -1, "unit_cost": "-2", "currency": "XYZ",
                    "business_justification": ""},
    },
    "baselines": {
        "valid": {"title": "Release baseline", "baseline_type": "integrated",
                  "scope": "Project scope", "planned_start": "2026-11-01",
                  "planned_finish": "2026-12-01", "cost_baseline": 10000,
                  "assumptions": "Team available"},
        "invalid": {"title": "Release baseline", "baseline_type": "wrong",
                    "scope": "", "planned_start": "2026-12-01",
                    "planned_finish": "2026-11-01", "cost_baseline": -1,
                    "assumptions": ""},
    },
    "releases": {
        "valid": {"title": "Version 2.1", "version": "2.1.0",
                  "target_environment": "staging", "release_notes": "Fixes",
                  "test_evidence": "CI report", "rollback_plan": "Redeploy prior build"},
        "invalid": {"title": "Version 2.1", "version": "", "target_environment": "unknown",
                    "release_notes": "", "test_evidence": "", "rollback_plan": ""},
    },
}

@pytest.mark.parametrize("module_key,examples", MODULES.items())
def test_domain_validators_accept_complete_valid_payload(module_key, examples):
    module = importlib.import_module(f"app.services.operations_domains.{module_key}")
    validate = getattr(module, f"validate_{module_key}")
    normalized, errors = validate(examples["valid"], partial=False)
    assert isinstance(normalized, dict)
    assert errors == {}


@pytest.mark.parametrize("module_key,examples", MODULES.items())
def test_domain_validators_report_invalid_payload(module_key, examples):
    module = importlib.import_module(f"app.services.operations_domains.{module_key}")
    validate = getattr(module, f"validate_{module_key}")
    _, errors = validate(examples["invalid"], partial=False)
    assert errors


@pytest.mark.parametrize("module_key,examples", MODULES.items())
def test_domain_transitions_reject_unknown_status(module_key, examples):
    module = importlib.import_module(f"app.services.operations_domains.{module_key}")
    transition = getattr(module, f"transition_{module_key}")
    assert transition("draft", "not-a-real-status", actor_role="admin", payload=examples["valid"])
