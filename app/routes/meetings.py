"""
Calendar, Meetings, and Scheduling API routes.
"""
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import (
    Meeting, MeetingAttendee, Task, User, Team,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
)
from app.routes.utils import (
    api_success, api_error, active_account_required,
    log_audit, send_notification
)

meetings_bp = Blueprint('meetings', __name__, url_prefix='/api')


def utc_now():
    return datetime.now(timezone.utc)


# ── Meeting List & Creation ───────────────────────────────────────────────────

@meetings_bp.route('/meetings', methods=['GET', 'POST'])
@login_required
@active_account_required
def meetings():
    if request.method == 'GET':
        # Return user's organized or invited meetings
        user_invited_meeting_ids = db.session.query(MeetingAttendee.meeting_id).filter_by(user_id=current_user.id).subquery()
        query = Meeting.query.filter(
            or_(
                Meeting.organizer_id == current_user.id,
                Meeting.id.in_(user_invited_meeting_ids),
                Meeting.team_id == current_user.team_id
            ),
            Meeting.status != 'cancelled'
        )

        upcoming_only = request.args.get('upcoming')
        if upcoming_only:
            query = query.filter(Meeting.end_time >= utc_now())

        meetings_list = query.order_by(Meeting.start_time.asc()).limit(100).all()
        return api_success([m.to_dict() for m in meetings_list])

    # POST — schedule meeting
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    start_str = data.get('start_time')
    end_str = data.get('end_time')
    location_or_link = (data.get('location_or_link') or '').strip()
    agenda = (data.get('agenda') or '').strip()
    team_id = data.get('team_id')
    invitee_ids = data.get('invitee_ids') or []

    if not title:
        return api_error('Meeting title is required.', 400)
    if not start_str or not end_str:
        return api_error('Start time and end time are required.', 400)

    try:
        start_time = datetime.fromisoformat(start_str)
        end_time = datetime.fromisoformat(end_str)
    except ValueError:
        return api_error('Invalid datetime format. Use ISO format (YYYY-MM-DDTHH:MM).', 400)

    if end_time <= start_time:
        return api_error('End time must be after start time.', 400)

    meeting = Meeting(
        title=title,
        agenda=agenda,
        organizer_id=current_user.id,
        team_id=int(team_id) if team_id else None,
        organization_id=current_user.organization_id or 1,
        start_time=start_time,
        end_time=end_time,
        location_or_link=location_or_link,
        status='scheduled'
    )
    db.session.add(meeting)
    db.session.flush()

    # Automatically add organizer as accepted attendee
    db.session.add(MeetingAttendee(meeting_id=meeting.id, user_id=current_user.id, status='accepted'))

    # Add invitees and notify
    if isinstance(invitee_ids, list):
        for uid in invitee_ids:
            try:
                uid_int = int(uid)
                if uid_int != current_user.id and User.query.get(uid_int):
                    db.session.add(MeetingAttendee(meeting_id=meeting.id, user_id=uid_int, status='invited'))
                    send_notification(
                        uid_int,
                        f'Meeting Invitation: {title}',
                        f'{current_user.full_name or current_user.username} invited you to {title} ({start_time.strftime("%b %d, %H:%M")})',
                        '/calendar',
                        'meeting_invite'
                    )
            except (ValueError, TypeError):
                continue

    db.session.commit()
    log_audit('meeting_scheduled', 'Meeting', meeting.id, f'Scheduled meeting: {meeting.title}')
    return api_success(meeting.to_dict(), message='Meeting scheduled successfully.', status_code=201)


# ── Meeting Details & Updates ──────────────────────────────────────────────────

@meetings_bp.route('/meetings/<int:meeting_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@active_account_required
def meeting_detail(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    if request.method == 'GET':
        attendees = MeetingAttendee.query.filter_by(meeting_id=meeting.id).all()
        res = meeting.to_dict()
        res['attendees'] = [a.to_dict() for a in attendees]
        return api_success(res)

    # Permission check for modify/cancel
    can_modify = (
        meeting.organizer_id == current_user.id or
        current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)
    )
    if not can_modify:
        return api_error('Only the meeting organizer or admin can edit this meeting.', 403)

    if request.method == 'DELETE':
        meeting.status = 'cancelled'
        db.session.commit()
        log_audit('meeting_cancelled', 'Meeting', meeting.id, f'Cancelled meeting {meeting.title}')
        return api_success(message='Meeting cancelled.')

    # PUT
    data = request.get_json(silent=True) or {}
    if 'title' in data:
        meeting.title = data['title'].strip()
    if 'agenda' in data:
        meeting.agenda = data['agenda'].strip()
    if 'location_or_link' in data:
        meeting.location_or_link = data['location_or_link'].strip()
    if 'start_time' in data:
        try:
            meeting.start_time = datetime.fromisoformat(data['start_time'])
        except ValueError:
            pass
    if 'end_time' in data:
        try:
            meeting.end_time = datetime.fromisoformat(data['end_time'])
        except ValueError:
            pass

    db.session.commit()
    log_audit('meeting_updated', 'Meeting', meeting.id, f'Updated meeting {meeting.title}')
    return api_success(meeting.to_dict(), message='Meeting updated successfully.')


# ── Meeting RSVP ───────────────────────────────────────────────────────────────

@meetings_bp.route('/meetings/<int:meeting_id>/rsvp', methods=['POST'])
@login_required
@active_account_required
def rsvp_meeting(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').strip().lower()

    if status not in ('accepted', 'declined', 'tentative'):
        return api_error("RSVP status must be 'accepted', 'declined', or 'tentative'.", 400)

    attendee = MeetingAttendee.query.filter_by(meeting_id=meeting.id, user_id=current_user.id).first()
    if not attendee:
        attendee = MeetingAttendee(meeting_id=meeting.id, user_id=current_user.id)
        db.session.add(attendee)

    attendee.status = status
    db.session.commit()

    return api_success(attendee.to_dict(), message=f'RSVP recorded as {status}.')


# ── Combined Calendar Feed ─────────────────────────────────────────────────────

@meetings_bp.route('/calendar/events', methods=['GET'])
@login_required
@active_account_required
def calendar_events():
    """
    Unified calendar event feed combining tasks with due dates and scheduled meetings.
    """
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    # Default to current month window
    today = date.today()
    start_date = today.replace(day=1) - timedelta(days=7)
    end_date = today.replace(day=28) + timedelta(days=14)

    if start_str:
        try:
            start_date = date.fromisoformat(start_str.split('T')[0])
        except ValueError:
            pass
    if end_str:
        try:
            end_date = date.fromisoformat(end_str.split('T')[0])
        except ValueError:
            pass

    events = []

    # 1. Tasks assigned to or created by current user within date window
    tasks = Task.query.filter(
        (Task.assignee_id == current_user.id) | (Task.user_id == current_user.id) | (Task.creator_id == current_user.id),
        Task.due_date.isnot(None),
        Task.due_date >= start_date,
        Task.due_date <= end_date
    ).all()

    for t in tasks:
        events.append({
            'id': f"task-{t.id}",
            'type': 'task',
            'title': f"Task: {t.title}",
            'date': t.due_date.isoformat(),
            'status': t.status,
            'priority': t.priority,
            'url': f"/tasks?task_id={t.id}",
            'color': '#25845A' if t.status == 'completed' else '#C96B45' if t.is_overdue else '#173F35',
        })

    # 2. Meetings
    user_invited_subquery = db.session.query(MeetingAttendee.meeting_id).filter_by(user_id=current_user.id).subquery()
    meetings_list = Meeting.query.filter(
        or_(
            Meeting.organizer_id == current_user.id,
            Meeting.id.in_(user_invited_subquery),
            Meeting.team_id == current_user.team_id
        ),
        Meeting.status == 'scheduled',
        Meeting.start_time >= datetime.combine(start_date, datetime.min.time()),
        Meeting.end_time <= datetime.combine(end_date, datetime.max.time())
    ).all()

    for m in meetings_list:
        events.append({
            'id': f"meeting-{m.id}",
            'type': 'meeting',
            'title': f"Meeting: {m.title}",
            'start_time': m.start_time.isoformat(),
            'end_time': m.end_time.isoformat(),
            'date': m.start_time.date().isoformat(),
            'location_or_link': m.location_or_link or '',
            'url': f"/calendar?meeting_id={m.id}",
            'color': '#245548',
        })

    return api_success(events)
