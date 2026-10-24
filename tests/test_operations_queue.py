"""Tests for explainable queue ranking and workload recommendations."""
from types import SimpleNamespace
from datetime import date, datetime
from app.services.operations_queue import calculate_queue_score, rank_queue, recommend_owner


def record(**overrides):
    base = dict(id=1, priority="medium", status="new", due_date=None, owner_id=2,
                payload_json={}, created_at=datetime(2026, 10, 1), updated_at=datetime(2026, 10, 2))
    base.update(overrides)
    return SimpleNamespace(**base)


def test_critical_overdue_unassigned_work_scores_higher():
    ordinary = record()
    urgent = record(id=2, priority="critical", status="investigating",
                    due_date=date(2026, 10, 1), owner_id=None,
                    payload_json={"impact": "critical"})
    assert calculate_queue_score(urgent)["score"] > calculate_queue_score(ordinary)["score"]


def test_rank_queue_returns_highest_score_first():
    low = record(id=1, priority="low")
    high = record(id=2, priority="high")
    ranked = rank_queue([low, high])
    assert ranked[0][0].id == 2


def test_recommend_owner_prefers_lower_active_workload():
    users = [
        SimpleNamespace(id=10, account_active=True, role="employee", full_name="A"),
        SimpleNamespace(id=11, account_active=True, role="employee", full_name="B"),
    ]
    records = [record(owner_id=10) for _ in range(4)] + [record(owner_id=11)]
    result = recommend_owner(users, records)
    assert result["recommended"]["user_id"] == 11
