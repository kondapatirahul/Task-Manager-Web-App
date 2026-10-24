"""Tests for operational control evaluations."""
from types import SimpleNamespace
from datetime import date, datetime
from app.services.operations_controls import evaluate_due_date, evaluate_record_controls, summarize_controls


def test_due_date_classifies_overdue_active_record():
    result = evaluate_due_date(date(2026, 10, 1), "investigating", today=date(2026, 10, 24))
    assert result["state"] == "overdue"
    assert result["days"] == -23
    assert result["overdue"] is True


def test_terminal_record_is_not_marked_overdue():
    result = evaluate_due_date(date(2026, 1, 1), "closed", today=date(2026, 10, 24))
    assert result["state"] == "terminal"
    assert result["overdue"] is False


def test_release_missing_rollback_is_critical_control_failure():
    record = SimpleNamespace(
        id=1, module_key="releases", record_key="REL-00001", status="draft",
        priority="high", owner_id=None, due_date=None, payload_json={"version": "1.0.0"},
    )
    result = evaluate_record_controls("releases", record, {})
    assert result["critical_failures"] >= 1
    assert result["blocked_by_critical_control"] is True


def test_control_summary_aggregates_readiness():
    result = summarize_controls([
        {"controls": [{"passed": True}, {"passed": False}], "critical_failures": 1,
         "due": {"overdue": True}, "blocked_by_critical_control": True, "ready_for_review": False},
        {"controls": [{"passed": True}], "critical_failures": 0,
         "due": {"overdue": False}, "blocked_by_critical_control": False, "ready_for_review": True},
    ])
    assert result["records"] == 2
    assert result["critical_failures"] == 1
    assert result["overdue_records"] == 1



def test_sla_summary_calculates_compliance_and_percentiles():
    from app.services.operations_controls import summarize_sla_observations
    result = summarize_sla_observations([
        {"module": "incidents", "elapsed_minutes": 30, "event_type": "resolved"},
        {"module": "incidents", "elapsed_minutes": 90, "event_type": "resolved"},
        {"module": "changes", "elapsed_minutes": 300, "event_type": "resolved"},
        {"module": "changes", "elapsed_minutes": None, "event_type": "resolved"},
    ], 120)
    assert result["sample_count"] == 3
    assert result["excluded_count"] == 1
    assert result["within_target"] == 2
    assert result["outside_target"] == 1
    assert result["compliance_percent"] == 66.67
