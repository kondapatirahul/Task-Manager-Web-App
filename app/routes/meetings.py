"""
Calendar, Meetings, and Scheduling API routes.
"""
from datetime import datetime, date, timedelta, timezone
from urllib.parse import urlparse
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import (
    Meeting, MeetingAttendee, Task, User, Team,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, TeamMember
)
from app.routes.utils import (
    api_success, api_error, active_account_required,
    log_audit, send_notification
)

meetings_bp = Blueprint('meetings', __name__, url_prefix='/api')


def utc_now():
    return datetime.now(timezone.utc)



def _is_admin():
    return current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr', 'hr')

def _visible_meeting_query():
    invited_ids = db.session.query(MeetingAttendee.meeting_id).filter_by(user_id=current_user.id)
    clauses = [Meeting.organizer_id == current_user.id, Meeting.id.in_(invited_ids)]
    if _is_admin():
        if current_user.organization_id is not None:
            clauses.append(Meeting.organization_id == current_user.organization_id)
        else:
            clauses.append(Meeting.organizer_id == current_user.id)
    elif current_user.role == ROLE_TEAM_LEAD:
        led_team_ids = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
        if led_team_ids:
            clauses.append(Meeting.team_id.in_(led_team_ids))
    query = Meeting.query.filter(or_(*clauses))
    if current_user.organization_id is not None and not _is_admin():
        query = query.filter(Meeting.organization_id == current_user.organization_id)
    return query

def _valid_location(value):
    value = (value or '').strip()
    if len(value) > 255:
        return False
    if not value or '://' not in value:
        return True  # physical room or empty value
    parsed = urlparse(value)
    return parsed.scheme in ('https', 'http') and bool(parsed.netloc) and parsed.username is None and parsed.password is None

# ── Meeting List & Creation ───────────────────────────────────────────────────

@meetings_bp.route('/meetings', methods=['GET', 'POST'])
@login_required
@active_account_required
def meetings():
    if request.method == 'GET':
        query = _visible_meeting_query().filter(Meeting.status != 'cancelled')

        upcoming_only = request.args.get('upcoming')
        if upcoming_only:
            query = query.filter(Meeting.end_time >= utc_now())

        meetings_list = query.order_by(Meeting.start_time.asc()).limit(150).all()

        # Batch lookup user RSVPs
        meeting_ids = [m.id for m in meetings_list]
        user_attendances = MeetingAttendee.query.filter(
            MeetingAttendee.meeting_id.in_(meeting_ids),
            MeetingAttendee.user_id == current_user.id
        ).all() if meeting_ids else []
        rsvp_map = {a.meeting_id: a.status for a in user_attendances}

        res = []
        for m in meetings_list:
            m_dict = m.to_dict()
            m_dict['my_rsvp'] = rsvp_map.get(m.id, 'none')
            m_dict['can_modify'] = can_manage_meeting(m, current_user)
            m_dict['is_url'] = bool(m.location_or_link and ('http' in m.location_or_link.lower() or 'zoom' in m.location_or_link.lower() or 'meet' in m.location_or_link.lower()))
            res.append(m_dict)

        return api_success(res)

    # POST — only authorized management roles may schedule meetings.
    if not (_is_admin() or current_user.role == ROLE_TEAM_LEAD):
        return api_error('Only authorized management users can schedule meetings.', 403)
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    start_str = data.get('start_time')
    end_str = data.get('end_time')
    raw_location = (data.get('location_or_link') or '').strip()
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
    if not _valid_location(location_or_link):
        return api_error('Meeting link must be a valid HTTP(S) URL or a room name.', 400)
    if end_time - start_time > timedelta(hours=24):
        return api_error('Meeting duration cannot exceed 24 hours.', 400)

    if current_user.role == ROLE_TEAM_LEAD:
        led_team_ids = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
        if team_id and (not str(team_id).isdigit() or int(team_id) not in led_team_ids):
            return api_error('You can schedule meetings only for a team you lead.', 403)
        team_id = int(team_id) if team_id else (led_team_ids[0] if len(led_team_ids) == 1 else None)
        if not team_id:
            return api_error('Select a team you lead for this meeting.', 400)
    elif team_id:
        team = db.session.get(Team, int(team_id)) if str(team_id).isdigit() else None
        if not team or (current_user.organization_id and team.organization_id != current_user.organization_id):
            return api_error('Invalid team for your organization.', 403)

    try:
        location_or_link = validate_and_normalize_location_link(raw_location)
    except ValueError as e:
        return api_error(str(e), 400)

    # Scoping team_id
    assigned_team_id = None
    if team_id:
        try:
            tid = int(team_id)
            if current_user.is_admin:
                assigned_team_id = tid
            elif current_user.is_team_lead:
                led_teams = Team.query.filter_by(lead_id=current_user.id).all()
                allowed_ids = {t.id for t in led_teams}
                if current_user.team_id:
                    allowed_ids.add(current_user.team_id)
                assigned_team_id = tid if tid in allowed_ids else current_user.team_id
            else:
                assigned_team_id = current_user.team_id
        except (ValueError, TypeError):
            assigned_team_id = current_user.team_id
    elif current_user.team_id:
        assigned_team_id = current_user.team_id

    meeting = Meeting(
        title=title,
        agenda=agenda,
        organizer_id=current_user.id,
        team_id=int(team_id) if team_id else None,
        organization_id=current_user.organization_id,
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
                invitee = db.session.get(User, uid_int)
                if uid_int == current_user.id or not invitee:
                    continue
                if invitee.organization_id != current_user.organization_id:
                    continue
                if current_user.role == ROLE_TEAM_LEAD and invitee.team_id != team_id:
                    continue
                existing = MeetingAttendee.query.filter_by(meeting_id=meeting.id, user_id=uid_int).first()
                if not existing:
                    db.session.add(MeetingAttendee(meeting_id=meeting.id, user_id=uid_int, status='invited'))
                    send_notification(uid_int, f'Meeting Invitation: {title}', f'{current_user.full_name or current_user.username} invited you to {title} ({start_time.strftime("%b %d, %H:%M")})', '/calendar', 'meeting_invite', f'meeting-invite-{meeting.id}-{uid_int}')
            except (ValueError, TypeError):
                continue

    db.session.commit()
    log_audit('meeting_scheduled', 'Meeting', meeting.id, f'Scheduled meeting: {meeting.title}')

    resp = meeting.to_dict()
    resp['can_modify'] = True
    resp['my_rsvp'] = 'accepted'
    return api_success(resp, message='Meeting scheduled successfully.', status_code=201)


# ── Meeting Details & Updates ──────────────────────────────────────────────────

@meetings_bp.route('/meetings/<int:meeting_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@active_account_required
def meeting_detail(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if not _visible_meeting_query().filter(Meeting.id == meeting.id).first():
        return api_error('Meeting not found or access denied.', 404)

    if request.method == 'GET':
        if not can_view_meeting(meeting, current_user):
            return api_error('You do not have permission to view this meeting.', 403)

        attendees = MeetingAttendee.query.filter_by(meeting_id=meeting.id).all()
        res = meeting.to_dict()
        res['attendees'] = [a.to_dict() for a in attendees]
        my_att = next((a for a in attendees if a.user_id == current_user.id), None)
        res['my_rsvp'] = my_att.status if my_att else 'none'
        res['can_modify'] = can_manage_meeting(meeting, current_user)
        res['is_url'] = bool(meeting.location_or_link and ('http' in meeting.location_or_link.lower() or 'zoom' in meeting.location_or_link.lower() or 'meet' in meeting.location_or_link.lower()))
        return api_success(res)

    # Permission check for modify/cancel
    can_modify = (
        meeting.organizer_id == current_user.id or
        _is_admin() or (current_user.role == ROLE_TEAM_LEAD and meeting.team_id in [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()])
    )
    if not can_modify:
        return api_error('Only the meeting organizer or admin can edit this meeting.', 403)

    if request.method == 'DELETE':
        meeting.status = 'cancelled'
        db.session.commit()

        # Notify attendees
        attendees = MeetingAttendee.query.filter_by(meeting_id=meeting.id).all()
        for att in attendees:
            if att.user_id != current_user.id:
                send_notification(
                    att.user_id,
                    f'Meeting Cancelled: {meeting.title}',
                    f'The meeting "{meeting.title}" scheduled for {meeting.start_time.strftime("%b %d, %H:%M")} has been cancelled.',
                    '/calendar',
                    'meeting_cancelled'
                )

        log_audit('meeting_cancelled', 'Meeting', meeting.id, f'Cancelled meeting: {meeting.title}')
        return api_success(message='Meeting cancelled successfully.')

    # PUT — update meeting
    data = request.get_json(silent=True) or {}
    if 'title' in data:
        t = data['title'].strip()
        if not t:
            return api_error('Meeting title cannot be empty.', 400)
        meeting.title = t

    if 'agenda' in data:
        meeting.agenda = (data['agenda'] or '').strip()

    if 'location_or_link' in data:
        candidate_link = str(data['location_or_link'] or '').strip()
        if not _valid_location(candidate_link):
            return api_error('Meeting link must be a valid HTTP(S) URL or a room name.', 400)
        meeting.location_or_link = candidate_link
    if 'start_time' in data:
        try:
            meeting.start_time = datetime.fromisoformat(data['start_time'])
        except (ValueError, TypeError):
            return api_error('Invalid start time.', 400)
    if 'end_time' in data:
        try:
            meeting.end_time = datetime.fromisoformat(data['end_time'])
        except (ValueError, TypeError):
            return api_error('Invalid end time.', 400)
    if meeting.end_time <= meeting.start_time or meeting.end_time - meeting.start_time > timedelta(hours=24):
        return api_error('Meeting end must be after start and duration cannot exceed 24 hours.', 400)

    db.session.commit()
    log_audit('meeting_updated', 'Meeting', meeting.id, f'Updated meeting: {meeting.title}')

    attendees = MeetingAttendee.query.filter_by(meeting_id=meeting.id).all()
    res = meeting.to_dict()
    res['attendees'] = [a.to_dict() for a in attendees]
    my_att = next((a for a in attendees if a.user_id == current_user.id), None)
    res['my_rsvp'] = my_att.status if my_att else 'none'
    res['can_modify'] = True
    res['is_url'] = bool(meeting.location_or_link and ('http' in meeting.location_or_link.lower() or 'zoom' in meeting.location_or_link.lower() or 'meet' in meeting.location_or_link.lower()))
    return api_success(res, message='Meeting updated successfully.')


@meetings_bp.route('/meetings/<int:meeting_id>/cancel', methods=['POST'])
@login_required
@active_account_required
def cancel_meeting_post(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if not can_manage_meeting(meeting, current_user):
        return api_error('Only the meeting organizer, team lead, or admin can cancel this meeting.', 403)

    meeting.status = 'cancelled'
    db.session.commit()

    attendees = MeetingAttendee.query.filter_by(meeting_id=meeting.id).all()
    for att in attendees:
        if att.user_id != current_user.id:
            send_notification(
                att.user_id,
                f'Meeting Cancelled: {meeting.title}',
                f'The meeting "{meeting.title}" scheduled for {meeting.start_time.strftime("%b %d, %H:%M")} has been cancelled.',
                '/calendar',
                'meeting_cancelled'
            )

    log_audit('meeting_cancelled', 'Meeting', meeting.id, f'Cancelled meeting: {meeting.title}')
    return api_success(message='Meeting cancelled successfully.')


# ── Meeting RSVP ───────────────────────────────────────────────────────────────

@meetings_bp.route('/meetings/<int:meeting_id>/rsvp', methods=['POST'])
@login_required
@active_account_required
def rsvp_meeting(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if not MeetingAttendee.query.filter_by(meeting_id=meeting.id, user_id=current_user.id).first():
        return api_error('You are not invited to this meeting.', 403)
    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').strip().lower()

    if status not in ('accepted', 'declined', 'tentative'):
        return api_error("RSVP status must be 'accepted', 'declined', or 'tentative'.", 400)

    attendee = MeetingAttendee.query.filter_by(meeting_id=meeting.id, user_id=current_user.id).first()
    if not attendee:
        return api_error('You are not invited to this meeting.', 403)

    attendee.status = status
    db.session.commit()

    # Notify organizer of status change if user is not organizer
    if meeting.organizer_id != current_user.id:
        user_name = current_user.full_name or current_user.username
        send_notification(
            meeting.organizer_id,
            f'Meeting RSVP: {user_name} ({status})',
            f'{user_name} responded "{status}" to {meeting.title}.',
            f'/calendar?meeting_id={meeting.id}',
            'meeting_rsvp'
        )

    log_audit('meeting_rsvp', 'Meeting', meeting.id, f'RSVP {status} by {current_user.username}')
    return api_success(attendee.to_dict(), message=f'RSVP recorded as {status}.')


# ── Combined Calendar Feed ─────────────────────────────────────────────────────

@meetings_bp.route('/calendar/events', methods=['GET'])
@login_required
@active_account_required
def calendar_events():
    """
    Unified calendar event feed combining tasks with due dates and scheduled meetings.
    Ensures zero duplicate events and enforces strict role-based access scoping.
    """
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    # Default to current month window (-14 days to +35 days)
    today = date.today()
    start_date = today.replace(day=1) - timedelta(days=14)
    # Estimate end of month + extra window
    end_date = (today.replace(day=28) + timedelta(days=35)).replace(day=1) + timedelta(days=14)

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

    # 1. Tasks within the authenticated user's authorized scope.
    personal_scope = (Task.assignee_id == current_user.id) | (Task.user_id == current_user.id)
    if _is_admin():
        task_query = Task.query
        if current_user.organization_id is not None:
            task_query = task_query.filter(Task.organization_id == current_user.organization_id)
        else:
            task_query = task_query.filter(personal_scope | (Task.creator_id == current_user.id))
    elif current_user.role == ROLE_TEAM_LEAD:
        team_ids = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
        scope = [personal_scope | (Task.creator_id == current_user.id)]
        if team_ids:
            scope.append(Task.team_id.in_(team_ids))
        task_query = Task.query.filter(or_(*scope))
    else:
        task_query = Task.query.filter(personal_scope)
    tasks = task_query.filter(Task.due_date.isnot(None), Task.due_date >= start_date, Task.due_date <= end_date).all()

    for t in tasks:
        # Determine color badge
        if t.status == 'completed':
            color = '#25845A' # Forest Green
        elif t.is_overdue:
            color = '#D94C4C' # Danger Red
        elif t.priority == 'high':
            color = '#E6A23C' # Warning Amber
        else:
            color = '#173F35' # Brand Primary

        assignee_display = (t.assignee.full_name or t.assignee.username) if t.assignee else 'Unassigned'
        events.append({
            'id': f"task-{t.id}",
            'raw_id': t.id,
            'type': 'task',
            'scope': 'team' if t.team_id else 'my',
            'title': f"Task: {t.title}",
            'date': t.due_date.isoformat(),
            'due_date': t.due_date.isoformat(),
            'status': t.status,
            'priority': t.priority,
            'assignee_name': (t.assignee.full_name or t.assignee.username) if t.assignee else ((t.user.full_name or t.user.username) if t.user else None),
            'url': f"/tasks?task_id={t.id}",
            'color': '#25845A' if t.status == 'completed' else '#C96B45' if t.is_overdue else '#173F35',
        })

    # 2. Meetings
    meetings_list = _visible_meeting_query().filter(
        Meeting.status == 'scheduled',
        Meeting.start_time >= datetime.combine(start_date, datetime.min.time()),
        Meeting.start_time <= datetime.combine(end_date, datetime.max.time())
    ).all()

    for m in meetings_list:
        is_url = bool(m.location_or_link and ('http' in m.location_or_link.lower() or 'zoom' in m.location_or_link.lower() or 'meet' in m.location_or_link.lower()))
        organizer_name = (m.organizer.full_name or m.organizer.username) if m.organizer else 'Unknown'

        events.append({
            'id': f"meeting-{m.id}",
            'raw_id': m.id,
            'type': 'meeting',
            'scope': 'team' if m.team_id else 'my',
            'title': f"Meeting: {m.title}",
            'start_time': m.start_time.isoformat(),
            'end_time': m.end_time.isoformat(),
            'location_or_link': m.location_or_link or '',
            'join_url': m.location_or_link if _valid_location(m.location_or_link) and urlparse(m.location_or_link or '').scheme in ('https', 'http') else None,
            'url': f"/calendar?meeting_id={m.id}",
            'color': '#C96B45', # Terracotta Brand Accent
        })

    # Sort events by date and time
    def get_sort_key(ev):
        if ev['type'] == 'meeting':
            return ev['start_time']
        return ev['date'] + "T00:00:00"

    events.sort(key=get_sort_key)
    return api_success(events)
