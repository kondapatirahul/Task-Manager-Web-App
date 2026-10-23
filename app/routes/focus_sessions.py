"""Focus-session API endpoints."""

from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import FocusSession, Task
from app.routes.utils import active_account_required, api_error, api_success
from app.services.focus_sessions import (
    ACTIVE_STATES,
    add_running_time,
    active_session_for,
    can_start_task,
    now_utc,
    permitted_history_query,
    serialize_session,
    summary_for,
)

focus_bp = Blueprint('focus_sessions', __name__, url_prefix='/api/focus-sessions')


def _get_session(session_id):
    session = db.session.get(FocusSession, session_id)
    if not session or session.user_id != current_user.id:
        return None
    return session


def _range():
    today = date.today()
    raw_start = request.args.get('start')
    raw_end = request.args.get('end')
    try:
        start = date.fromisoformat(raw_start) if raw_start else today
        end = date.fromisoformat(raw_end) if raw_end else start
    except ValueError:
        raise ValueError('start and end must be valid ISO dates.')
    if start > end or end - start > timedelta(days=366):
        raise ValueError('Invalid focus-session date range.')
    return start, end


def _in_range(query, start, end):
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return query.filter(FocusSession.started_at >= start_dt, FocusSession.started_at < end_dt)


@focus_bp.post('')
@active_account_required
@login_required
def start_session():
    data = request.get_json(silent=True) or {}
    try:
        task_id = int(data.get('task_id'))
    except (TypeError, ValueError):
        return api_error('A valid task_id is required.', 400)
    task = db.session.get(Task, task_id)
    if not can_start_task(current_user, task):
        return api_error('Task is outside your authorized scope.', 404)
    if active_session_for(current_user.id):
        return api_error('You already have an active focus session.', 409)
    now = now_utc()
    session = FocusSession(
        user_id=current_user.id,
        task_id=task.id,
        status='active',
        started_at=now,
        last_resumed_at=now,
    )
    db.session.add(session)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return api_error('Unable to start a concurrent focus session.', 409)
    return api_success(serialize_session(session), message='Focus session started.', status_code=201)


@focus_bp.get('/active')
@active_account_required
@login_required
def active():
    session = active_session_for(current_user.id)
    return api_success(serialize_session(session) if session else None)


@focus_bp.post('/<int:session_id>/pause')
@active_account_required
@login_required
def pause(session_id):
    session = _get_session(session_id)
    if not session or session.status != 'active':
        return api_error('Only an active session can be paused.', 409)
    now = now_utc()
    add_running_time(session, now)
    session.status = 'paused'
    session.paused_at = now
    db.session.commit()
    return api_success(serialize_session(session), message='Focus session paused.')


@focus_bp.post('/<int:session_id>/resume')
@active_account_required
@login_required
def resume(session_id):
    session = _get_session(session_id)
    if not session or session.status != 'paused':
        return api_error('Only a paused session can be resumed.', 409)
    now = now_utc()
    session.status = 'active'
    session.last_resumed_at = now
    session.paused_at = None
    db.session.commit()
    return api_success(serialize_session(session), message='Focus session resumed.')


@focus_bp.post('/<int:session_id>/finish')
@active_account_required
@login_required
def finish(session_id):
    session = _get_session(session_id)
    if not session or session.status not in ACTIVE_STATES:
        return api_error('Only an active or paused session can be finished.', 409)
    now = now_utc()
    add_running_time(session, now)
    session.status = 'finished'
    session.ended_at = now
    session.paused_at = session.paused_at or now
    db.session.commit()
    return api_success(serialize_session(session), message='Focus session finished.')


@focus_bp.post('/<int:session_id>/interrupt')
@active_account_required
@login_required
def interrupt(session_id):
    session = _get_session(session_id)
    if not session or session.status not in ACTIVE_STATES:
        return api_error('Only an active or paused session can be interrupted.', 409)
    now = now_utc()
    add_running_time(session, now)
    session.status = 'interrupted'
    session.ended_at = now
    session.paused_at = session.paused_at or now
    db.session.commit()
    return api_success(serialize_session(session), message='Focus session interrupted.')


@focus_bp.get('')
@active_account_required
@login_required
def history():
    try:
        start, end = _range()
    except ValueError as error:
        return api_error(str(error), 400)
    query = _in_range(permitted_history_query(current_user), start, end)
    sessions = query.order_by(FocusSession.started_at.desc()).limit(200).all()
    week_start = end - timedelta(days=end.weekday())
    week_query = _in_range(permitted_history_query(current_user), week_start, end)
    week_sessions = week_query.order_by(FocusSession.started_at.desc()).limit(500).all()
    return api_success({
        'items': [serialize_session(item) for item in sessions],
        'summary': summary_for(current_user, sessions, start, end),
        'weekly_summary': summary_for(current_user, week_sessions, week_start, end),
    })
