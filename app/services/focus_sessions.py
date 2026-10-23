"""Server-side focus session state and authorization helpers."""

from datetime import datetime, timezone

from sqlalchemy import or_

from app import db
from app.models import FocusSession, Task, User
from app.services.workload import authorized_task_query

ACTIVE_STATES = {'active', 'paused'}
MANAGER_ROLES = {'super_admin', 'admin', 'hr', 'team_lead'}


def now_utc():
    return datetime.now(timezone.utc)


def can_view_task(user, task):
    return bool(task and authorized_task_query(user).filter(Task.id == task.id).first())


def can_start_task(user, task):
    if not can_view_task(user, task):
        return False
    return (
        task.user_id == user.id
        or task.assigned_to_id == user.id
        or user.role in MANAGER_ROLES
    )


def active_session_for(user_id):
    return FocusSession.query.filter(
        FocusSession.user_id == user_id,
        FocusSession.status.in_(ACTIVE_STATES),
    ).order_by(FocusSession.id.desc()).first()


def add_running_time(session, at):
    if session.status != 'active' or not session.last_resumed_at:
        return
    started = session.last_resumed_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    session.active_seconds += max(0, int((at - started).total_seconds()))
    session.last_resumed_at = at


def serialize_session(session):
    estimated = session.task.estimated_effort_hours
    active_seconds = session.active_seconds
    if session.status == 'active' and session.last_resumed_at:
        resumed = session.last_resumed_at
        if resumed.tzinfo is None:
            resumed = resumed.replace(tzinfo=timezone.utc)
        active_seconds += max(0, int((now_utc() - resumed).total_seconds()))
    actual_hours = round(active_seconds / 3600, 2)
    return {
        'id': session.id,
        'task_id': session.task_id,
        'task_title': session.task.title if session.task else 'Deleted task',
        'task_status': session.task.status if session.task else None,
        'estimated_effort_hours': estimated,
        'actual_hours': actual_hours,
        'status': session.status,
        'started_at': session.started_at.isoformat() if session.started_at else None,
        'last_resumed_at': session.last_resumed_at.isoformat() if session.last_resumed_at else None,
        'paused_at': session.paused_at.isoformat() if session.paused_at else None,
        'ended_at': session.ended_at.isoformat() if session.ended_at else None,
        'active_seconds': active_seconds,
    }


def permitted_history_query(user):
    if user.role == 'super_admin':
        return FocusSession.query
    if user.role in {'admin', 'hr'}:
        visible_tasks = authorized_task_query(user).with_entities(Task.id).subquery()
        return FocusSession.query.filter(FocusSession.task_id.in_(visible_tasks))
    if user.role == 'team_lead':
        visible_tasks = authorized_task_query(user).with_entities(Task.id).subquery()
        return FocusSession.query.filter(
            or_(FocusSession.user_id == user.id, FocusSession.task_id.in_(visible_tasks))
        )
    return FocusSession.query.filter(FocusSession.user_id == user.id)


def summary_for(user, sessions, start, end):
    sessions = list(sessions)
    total_seconds = sum(item.active_seconds for item in sessions)
    by_task = {}
    for item in sessions:
        entry = by_task.setdefault(item.task_id, {
            'task_id': item.task_id,
            'task_title': item.task.title if item.task else 'Deleted task',
            'active_seconds': 0,
            'estimated_effort_hours': item.task.estimated_effort_hours if item.task else None,
        })
        entry['active_seconds'] += item.active_seconds
    for entry in by_task.values():
        entry['actual_hours'] = round(entry['active_seconds'] / 3600, 2)
    return {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'session_count': len(sessions),
        'active_seconds': total_seconds,
        'actual_hours': round(total_seconds / 3600, 2),
        'tasks': list(by_task.values()),
    }
