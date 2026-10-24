"""Common workflow primitives for operational workspaces."""
from datetime import date
from sqlalchemy import func, false
from app import db
from app.models import ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_TEAM_LEAD, ROLE_HR
from app.operations_models import OperationalRecord, OperationalEvent, OperationalSequence


MANAGEMENT_ROLES = {ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_TEAM_LEAD, ROLE_HR}


def can_manage(user):
    return bool(user and (getattr(user, "role", "") in MANAGEMENT_ROLES or
                          getattr(user, "has_role", lambda *_: False)(ROLE_ADMIN, ROLE_SUPER_ADMIN)))


def tenant_id_for(user):
    """Return the current tenant id; super-admin must still select a tenant explicitly."""
    return getattr(user, "organization_id", None)


def next_key(organization_id, module_key, prefix):
    """Allocate a readable key under a transaction; unique constraints are the final guard."""
    row = OperationalSequence.query.filter_by(
        organization_id=organization_id, module_key=module_key
    ).with_for_update().first()
    if row is None:
        row = OperationalSequence(organization_id=organization_id, module_key=module_key, last_value=0)
        db.session.add(row)
        db.session.flush()
    row.last_value += 1
    db.session.flush()
    return f"{prefix}-{row.last_value:05d}"


def add_event(record, actor_id, event_type, message="", from_status=None, to_status=None, details=None):
    event = OperationalEvent(
        organization_id=record.organization_id, record_id=record.id, actor_id=actor_id,
        event_type=event_type, message=(message or "")[:5000], from_status=from_status,
        to_status=to_status, details_json=details or {},
    )
    db.session.add(event)
    return event


def parse_due_date(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("due_date must be an ISO date string.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("due_date must use YYYY-MM-DD format.") from exc


def visible_query(model, user, module_key):
    query = model.query.filter_by(module_key=module_key, archived=False)
    if getattr(user, "role", "") != ROLE_SUPER_ADMIN:
        organization_id = tenant_id_for(user)
        if organization_id is None:
            return query.filter(false())
        query = query.filter_by(organization_id=organization_id)
    return query


def serialize_page(query, page, page_size):
    total = query.count()
    rows = query.order_by(OperationalRecord.updated_at.desc(), OperationalRecord.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [row.to_dict() for row in rows],
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


def module_metrics(query):
    """Calculate a compact operational summary from the filtered record query."""
    rows = query.with_entities(OperationalRecord.status, func.count(OperationalRecord.id)).group_by(
        OperationalRecord.status
    ).all()
    counts = {status: count for status, count in rows}
    total = sum(counts.values())
    open_count = sum(value for status, value in counts.items()
                     if status not in {"closed", "completed", "cancelled", "rejected", "released"})
    return {"total": total, "open": open_count, "by_status": counts}
