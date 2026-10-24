"""Prioritization and workload balancing for the cross-module work queue."""
from datetime import date


PRIORITY_WEIGHT = {"critical": 100, "high": 70, "medium": 40, "low": 10}
AGING_WEIGHT = {"critical": 8, "high": 5, "medium": 3, "low": 1}


def calculate_queue_score(record, today=None):
    """Return an explainable priority score; this never changes record priority."""
    today = today or date.today()
    priority = getattr(record, "priority", "medium")
    score = PRIORITY_WEIGHT.get(priority, 40)
    reasons = [f"{priority} priority"]
    due_date = getattr(record, "due_date", None)
    status = getattr(record, "status", "")
    terminal = status in {"closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"}
    overdue_days = max(0, (today - due_date).days) if due_date and due_date < today and not terminal else 0
    if overdue_days:
        score += min(40, overdue_days * AGING_WEIGHT.get(priority, 3))
        reasons.append(f"{overdue_days} day(s) overdue")
    elif due_date and (due_date - today).days <= 2 and not terminal:
        score += 15
        reasons.append("due within 48 hours")
    if not getattr(record, "owner_id", None) and not terminal:
        score += 10
        reasons.append("unassigned")
    payload = getattr(record, "payload_json", None) or {}
    if payload.get("impact") == "critical" or payload.get("risk_level") == "critical":
        score += 15
        reasons.append("critical impact or risk")
    if status in {"blocked", "failed", "investigating", "mitigated"}:
        score += 8
        reasons.append(f"status is {status}")
    return {"score": score, "reasons": reasons, "overdue_days": overdue_days}


def rank_queue(records, today=None):
    """Return records ordered by explainable score, then earliest due date."""
    today = today or date.today()
    scored = [(record, calculate_queue_score(record, today)) for record in records]
    scored.sort(key=lambda pair: (
        -pair[1]["score"],
        pair[0].due_date or date.max,
        pair[0].created_at or pair[0].updated_at,
        pair[0].id,
    ))
    return scored


def workload_by_owner(records):
    """Count active records by owner for a simple balancing recommendation."""
    terminal = {"closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"}
    result = {}
    for record in records:
        if record.status in terminal:
            continue
        key = record.owner_id or 0
        bucket = result.setdefault(key, {"owner_id": key or None, "open_records": 0,
                                         "critical_records": 0, "overdue_records": 0})
        bucket["open_records"] += 1
        if record.priority == "critical":
            bucket["critical_records"] += 1
        if record.due_date and record.due_date < date.today():
            bucket["overdue_records"] += 1
    return result


def recommend_owner(users, records, *, exclude_user_ids=None):
    """Recommend the least-loaded active user; final assignment remains a human action."""
    excluded = set(exclude_user_ids or [])
    workload = workload_by_owner(records)
    candidates = []
    for user in users:
        if not getattr(user, "account_active", False) or user.id in excluded:
            continue
        if user.role in {"super_admin"}:
            continue
        bucket = workload.get(user.id, {})
        candidates.append({
            "user_id": user.id,
            "name": getattr(user, "full_name", None) or getattr(user, "email", "User"),
            "role": user.role,
            "open_records": bucket.get("open_records", 0),
            "critical_records": bucket.get("critical_records", 0),
            "overdue_records": bucket.get("overdue_records", 0),
        })
    candidates.sort(key=lambda item: (
        item["critical_records"], item["overdue_records"], item["open_records"], item["user_id"]
    ))
    if not candidates:
        return {"recommended": None, "candidates": [], "reason": "No eligible active users are available."}
    first = candidates[0]
    return {"recommended": first, "candidates": candidates[:10],
            "reason": "Recommended by current open-work count, critical work, and overdue workload. Confirm skills and availability before assigning."}
