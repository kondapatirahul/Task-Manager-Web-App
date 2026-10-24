"""Administrative audit-log search and CSV export endpoints.

The audit trail is intentionally read-only through this API. Events are scoped
by organization unless the caller is a super administrator. Query parameters
are validated and result sizes are bounded to protect the database.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta

from flask import Blueprint, Response, request
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.models import AuditLog, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.routes.utils import active_account_required, api_error, api_success, roles_required


audit_logs_bp = Blueprint("audit_logs", __name__, url_prefix="/api/audit-logs")
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200
_MAX_EXPORT_ROWS = 10_000


def _parse_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be an integer.")
    if value < minimum or value > maximum:
        raise ValueError(f"'{name}' must be between {minimum} and {maximum}.")
    return value


def _parse_date(name: str) -> date | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"'{name}' must use YYYY-MM-DD format.")


def _build_query():
    """Build a filtered, organization-scoped query and its normalized filters."""
    query = AuditLog.query.options(joinedload(AuditLog.user))
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        org_id = current_user.organization_id
        if org_id is None:
            query = query.filter(AuditLog.organization_id.is_(None))
        else:
            query = query.filter(AuditLog.organization_id == org_id)

    action = request.args.get("action", "").strip()
    entity_type = request.args.get("entity_type", "").strip()
    if len(action) > 100:
        raise ValueError("'action' cannot exceed 100 characters.")
    if len(entity_type) > 50:
        raise ValueError("'entity_type' cannot exceed 50 characters.")
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)

    user_id = request.args.get("user_id", "").strip()
    if user_id:
        try:
            parsed_user_id = int(user_id)
        except ValueError:
            raise ValueError("'user_id' must be an integer.")
        if parsed_user_id < 1:
            raise ValueError("'user_id' must be a positive integer.")
        query = query.filter(AuditLog.user_id == parsed_user_id)

    start_date = _parse_date("start_date")
    end_date = _parse_date("end_date")
    if start_date and end_date and start_date > end_date:
        raise ValueError("'start_date' cannot be after 'end_date'.")
    if start_date:
        query = query.filter(AuditLog.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(
            AuditLog.created_at < datetime.combine(end_date + timedelta(days=1), time.min)
        )

    return query, {
        "action": action or None,
        "entity_type": entity_type or None,
        "user_id": int(user_id) if user_id else None,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }


def _safe_csv_cell(value) -> str:
    """Prevent spreadsheet formula injection in exported user-controlled text."""
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@audit_logs_bp.get("")
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def list_audit_logs():
    """Return a paginated audit log with optional exact-match/date filters."""
    try:
        page = _parse_integer("page", 1, 1, 2_147_483_647)
        page_size = _parse_integer("page_size", _DEFAULT_PAGE_SIZE, 1, _MAX_PAGE_SIZE)
        query, filters = _build_query()
    except ValueError as exc:
        return api_error(str(exc), 400)

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return api_success({
        "items": [row.to_dict() for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_previous": page > 1,
        },
        "filters": filters,
    })


@audit_logs_bp.get("/export.csv")
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def export_audit_logs():
    """Export at most 10,000 matching audit rows as formula-safe CSV."""
    try:
        query, _filters = _build_query()
    except ValueError as exc:
        return api_error(str(exc), 400)

    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(
        _MAX_EXPORT_ROWS + 1
    ).all()
    if len(rows) > _MAX_EXPORT_ROWS:
        return api_error(
            f"Export exceeds {_MAX_EXPORT_ROWS:,} rows. Narrow the date range or filters.",
            413,
        )

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "id", "created_at", "organization_id", "user_id", "user_name",
        "action", "entity_type", "entity_id", "details", "ip_address",
    ])
    for row in rows:
        payload = row.to_dict()
        writer.writerow([
            payload.get("id"),
            payload.get("created_at"),
            payload.get("organization_id"),
            payload.get("user_id"),
            _safe_csv_cell(payload.get("user_name")),
            _safe_csv_cell(payload.get("action")),
            _safe_csv_cell(payload.get("entity_type")),
            payload.get("entity_id"),
            _safe_csv_cell(payload.get("details")),
            _safe_csv_cell(row.ip_address),
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tasknest-audit-logs.csv"'},
    )
