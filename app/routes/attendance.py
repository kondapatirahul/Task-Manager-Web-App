"""
Attendance, Timesheets, and Correction Requests API routes.
Strictly scoped for Admin and Team Lead management workflows,
while keeping personal check-in/out and shift tracking intact.
"""
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, request, Response
from flask_login import current_user, login_required
from sqlalchemy import func
from app import db
from app.models import (
    Attendance, AttendanceCorrection, User, Team, TeamMember,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
)
from app.routes.utils import (
    api_success, api_error, roles_required, active_account_required,
    log_audit, send_notification
)

attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/attendance')


def utc_now():
    return datetime.now(timezone.utc)


def format_duration(minutes):
    """Format minutes into human-readable string: e.g. '7h 30m', '45m', '< 1m'."""
    if minutes is None or minutes < 0:
        return '0m'
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0 and mins > 0:
        return f"{hours}h {mins}m"
    elif hours > 0:
        return f"{hours}h"
    elif mins > 0:
        return f"{mins}m"
    return "< 1m"


def get_authorized_team_ids_for_user(user):
    """Return list of team IDs authorized for this user."""
    if user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        teams = Team.query.all()
        return [t.id for t in teams]
    elif user.has_role(ROLE_TEAM_LEAD):
        led_teams = Team.query.filter_by(lead_id=user.id).all()
        tids = set(t.id for t in led_teams)
        if user.team_id:
            tids.add(user.team_id)
        member_teams = TeamMember.query.filter_by(user_id=user.id).all()
        for mt in member_teams:
            tids.add(mt.team_id)
        return list(tids)
    return []


def get_authorized_user_ids_for_user(user):
    """Return list of user IDs authorized for this user."""
    if user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        org_id = user.organization_id
        if org_id:
            users = User.query.filter((User.organization_id == org_id) | (User.organization_id.is_(None))).all()
        else:
            users = User.query.all()
        return [u.id for u in users]
    elif user.has_role(ROLE_TEAM_LEAD):
        team_ids = get_authorized_team_ids_for_user(user)
        user_ids = {user.id}
        if team_ids:
            assigned_users = User.query.filter(User.team_id.in_(team_ids)).all()
            for u in assigned_users:
                user_ids.add(u.id)
            tm_list = TeamMember.query.filter(TeamMember.team_id.in_(team_ids)).all()
            for tm in tm_list:
                user_ids.add(tm.user_id)
        return list(user_ids)
    return []


# ── Today's Status ─────────────────────────────────────────────────────────────

@attendance_bp.route('/today', methods=['GET'])
@login_required
@active_account_required
def get_today_status():
    """Return user's check-in state today, active session, and completed shifts."""
    active_session = Attendance.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).first()

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    completed_today = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        Attendance.check_in >= today_start,
        Attendance.check_in < today_end,
        Attendance.status.in_(['completed', 'corrected'])
    ).order_by(Attendance.check_out.asc()).all()

    total_minutes = sum(a.duration_minutes for a in completed_today)
    last_completed = completed_today[-1] if completed_today else None

    active_duration_minutes = 0
    if active_session:
        delta = utc_now() - active_session.check_in.replace(tzinfo=timezone.utc if active_session.check_in.tzinfo is None else active_session.check_in.tzinfo)
        active_duration_seconds = max(0, int(delta.total_seconds()))
        session_today_start = max(today_start, active_session.check_in.replace(tzinfo=None) if active_session.check_in.tzinfo else active_session.check_in)
        active_today_seconds = max(0, int((utc_now().replace(tzinfo=None) - session_today_start).total_seconds()))
        active_duration_minutes = active_today_seconds // 60
        total_minutes += active_duration_minutes
    else:
        active_duration_seconds = 0

    # Standard Shift: 09:30 AM threshold
    is_late = False
    ref_session = active_session or (completed_today[0] if completed_today else None)
    if ref_session and ref_session.check_in:
        ci = ref_session.check_in
        if ci.hour > 9 or (ci.hour == 9 and ci.minute > 30):
            is_late = True

    status_label = 'working' if active_session else ('completed' if last_completed else 'not_checked_in')

    return api_success({
        'is_checked_in': active_session is not None,
        'has_completed_shift': last_completed is not None and active_session is None,
        'status_label': status_label,
        'is_late': is_late,
        'active_session': active_session.to_dict() if active_session else None,
        'last_completed_session': last_completed.to_dict() if last_completed else None,
        'today_duration_minutes': total_minutes,
        'today_duration_hours': round(total_minutes / 60.0, 2),
        'today_duration_display': format_duration(total_minutes),
        'active_duration_seconds': active_duration_seconds,
        'completed_duration_seconds': sum(a.duration_minutes * 60 for a in completed_today),
    })


# ── Check-In ───────────────────────────────────────────────────────────────────

@attendance_bp.route('/check-in', methods=['POST'])
@login_required
@active_account_required
def check_in():
    # Enforce: Prevent duplicate active session
    existing_active = Attendance.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).first()
    if existing_active:
        return api_error('You already have an active session in progress. Please check out first.', 409)

    data = request.get_json(silent=True) or {}
    notes = (data.get('notes') or '').strip()

    record = Attendance(
        user_id=current_user.id,
        organization_id=current_user.organization_id or 1,
        check_in=utc_now(),
        notes=notes,
        status='active'
    )
    db.session.add(record)
    db.session.commit()

    log_audit('attendance_check_in', 'Attendance', record.id, f'User {current_user.username} checked in')
    return api_success(record.to_dict(), message='Checked in successfully.', status_code=201)


# ── Check-Out ──────────────────────────────────────────────────────────────────

@attendance_bp.route('/check-out', methods=['POST'])
@login_required
@active_account_required
def check_out():
    # Enforce: Prevent checkout without valid active session
    active_session = Attendance.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).first()
    if not active_session:
        return api_error('No active check-in session found to check out from.', 400)

    now = utc_now()
    active_session.check_out = now
    active_session.status = 'completed'
    active_session.calculate_duration()

    data = request.get_json(silent=True) or {}
    if 'notes' in data and data['notes']:
        existing_notes = active_session.notes or ''
        active_session.notes = f"{existing_notes} | Check-out: {data['notes'].strip()}" if existing_notes else data['notes'].strip()

    db.session.commit()

    log_audit(
        'attendance_check_out',
        'Attendance',
        active_session.id,
        f'User {current_user.username} checked out ({active_session.duration_minutes} mins)'
    )
    return api_success(active_session.to_dict(), message='Checked out successfully.')


# ── Personal Timesheet ─────────────────────────────────────────────────────────

@attendance_bp.route('/my', methods=['GET'])
@login_required
@active_account_required
def my_attendance():
    """Get authenticated user's attendance records and summaries."""
    records = Attendance.query.filter_by(
        user_id=current_user.id
    ).order_by(Attendance.check_in.desc()).limit(60).all()

    # Total recorded minutes across last 7 days
    seven_days_ago = date.today() - timedelta(days=6)
    weekly_records = [
        r for r in records
        if r.check_in and r.check_in.date() >= seven_days_ago and r.status in ('completed', 'corrected')
    ]
    weekly_minutes = sum(r.duration_minutes for r in weekly_records)

    # Missing checkout indicators
    missing_checkouts = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        Attendance.status == 'active',
        Attendance.check_in < datetime.combine(date.today(), datetime.min.time())
    ).count()

    serialized_records = []
    for r in records:
        rd = r.to_dict()
        rd['duration_display'] = format_duration(r.duration_minutes)
        rd['is_late'] = bool(r.check_in and (r.check_in.hour > 9 or (r.check_in.hour == 9 and r.check_in.minute > 30)))
        rd['is_missing_checkout'] = bool(r.status == 'active' and r.check_in and r.check_in.date() < date.today())
        serialized_records.append(rd)

    return api_success({
        'records': serialized_records,
        'weekly_hours': round(weekly_minutes / 60.0, 2),
        'weekly_duration_display': format_duration(weekly_minutes),
        'missing_checkouts_count': missing_checkouts,
    })


# ── Attendance Summary Metrics (Admin & TL) ───────────────────────────────────

@attendance_bp.route('/metrics', methods=['GET'])
@login_required
@active_account_required
def get_attendance_metrics():
    """
    Returns 6 real database-backed attendance summary metrics:
    - Currently Checked In
    - Checked In Today
    - Total Working Hours Today
    - Total Working Hours This Week
    - Missing Check-Outs
    - Pending Correction Requests
    Restricted to Admin and Team Lead. Admin gets org-wide metrics; TL gets team-scoped metrics.
    """
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD):
        return api_error('Permission denied to view attendance metrics.', 403)

    auth_user_ids = get_authorized_user_ids_for_user(current_user)
    if not auth_user_ids:
        return api_success({
            'currently_checked_in': 0,
            'checked_in_today': 0,
            'total_working_hours_today': 0.0,
            'total_working_hours_week': 0.0,
            'missing_checkouts': 0,
            'pending_corrections': 0,
        })

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    week_start = datetime.combine(date.today() - timedelta(days=date.today().weekday()), datetime.min.time())

    # 1. Currently Checked In (status == 'active')
    currently_active = Attendance.query.filter(
        Attendance.user_id.in_(auth_user_ids),
        Attendance.status == 'active'
    ).count()

    # 2. Checked In Today (distinct users who checked in today)
    checked_in_today = db.session.query(func.count(func.distinct(Attendance.user_id))).filter(
        Attendance.user_id.in_(auth_user_ids),
        Attendance.check_in >= today_start,
        Attendance.check_in < today_end
    ).scalar() or 0

    # 3. Total Working Hours Today
    completed_today_minutes = db.session.query(func.coalesce(func.sum(Attendance.duration_minutes), 0)).filter(
        Attendance.user_id.in_(auth_user_ids),
        Attendance.check_in >= today_start,
        Attendance.check_in < today_end,
        Attendance.status.in_(['completed', 'corrected'])
    ).scalar() or 0

    active_today_sessions = Attendance.query.filter(
        Attendance.user_id.in_(auth_user_ids),
        Attendance.status == 'active'
    ).all()
    active_today_minutes = 0
    now_utc = utc_now()
    now_naive = now_utc.replace(tzinfo=None)
    for s in active_today_sessions:
        ci = s.check_in.replace(tzinfo=None) if s.check_in.tzinfo else s.check_in
        session_today_start = max(today_start, ci)
        if session_today_start < now_naive:
            active_today_minutes += max(0, int((now_naive - session_today_start).total_seconds() / 60))

    total_minutes_today = completed_today_minutes + active_today_minutes
    total_hours_today = round(total_minutes_today / 60.0, 2)

    # 4. Total Working Hours This Week
    completed_week_minutes = db.session.query(func.coalesce(func.sum(Attendance.duration_minutes), 0)).filter(
        Attendance.user_id.in_(auth_user_ids),
        Attendance.check_in >= week_start,
        Attendance.status.in_(['completed', 'corrected'])
    ).scalar() or 0

    active_week_minutes = 0
    for s in active_today_sessions:
        ci = s.check_in.replace(tzinfo=None) if s.check_in.tzinfo else s.check_in
        session_week_start = max(week_start, ci)
        if session_week_start < now_naive:
            active_week_minutes += max(0, int((now_naive - session_week_start).total_seconds() / 60))

    total_minutes_week = completed_week_minutes + active_week_minutes
    total_hours_week = round(total_minutes_week / 60.0, 2)

    # 5. Missing Check-Outs (active session started before today)
    missing_checkouts = Attendance.query.filter(
        Attendance.user_id.in_(auth_user_ids),
        Attendance.status == 'active',
        Attendance.check_in < today_start
    ).count()

    # 6. Pending Correction Requests
    pending_corrections = AttendanceCorrection.query.filter(
        AttendanceCorrection.user_id.in_(auth_user_ids),
        AttendanceCorrection.status == 'pending'
    ).count()

    return api_success({
        'currently_checked_in': currently_active,
        'checked_in_today': checked_in_today,
        'total_working_hours_today': total_hours_today,
        'total_working_hours_week': total_hours_week,
        'missing_checkouts': missing_checkouts,
        'pending_corrections': pending_corrections,
    })


# ── Paginated & Filterable Attendance Records (Admin & TL) ────────────────────

@attendance_bp.route('/records', methods=['GET'])
@login_required
@active_account_required
def get_attendance_records():
    """
    Paginated, filterable attendance records for Admin and Team Lead.
    Team Lead is strictly restricted to their authorized team members + self.
    """
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD):
        return api_error('Permission denied to view attendance records.', 403)

    auth_user_ids = get_authorized_user_ids_for_user(current_user)
    if not auth_user_ids:
        return api_success({
            'items': [],
            'page': 1,
            'per_page': 15,
            'total': 0,
            'pages': 0
        })

    query = Attendance.query.join(User, Attendance.user_id == User.id).filter(
        Attendance.user_id.in_(auth_user_ids)
    )

    # Filter: specific employee (user_id)
    target_user_id = request.args.get('user_id', type=int)
    if target_user_id:
        if target_user_id not in auth_user_ids:
            return api_error('Permission denied for requested employee.', 403)
        query = query.filter(Attendance.user_id == target_user_id)

    # Filter: team_id
    team_id = request.args.get('team_id', type=int)
    if team_id:
        if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
            led_tids = get_authorized_team_ids_for_user(current_user)
            if team_id not in led_tids:
                return api_error('Permission denied for requested team.', 403)
        query = query.filter(User.team_id == team_id)

    # Filter: role
    role_filter = (request.args.get('role') or '').strip()
    if role_filter:
        query = query.filter(User.role == role_filter)

    # Filter: search q
    q = (request.args.get('q') or '').strip()
    if q:
        query = query.filter(
            (User.full_name.ilike(f'%{q}%')) |
            (User.username.ilike(f'%{q}%')) |
            (User.employee_id_code.ilike(f'%{q}%')) |
            (User.email.ilike(f'%{q}%'))
        )

    # Filter: status
    status_filter = (request.args.get('status') or '').strip().lower()
    today_start = datetime.combine(date.today(), datetime.min.time())
    if status_filter in ('active', 'completed', 'corrected'):
        query = query.filter(Attendance.status == status_filter)

    # Filter: missing_checkout
    missing_co = request.args.get('missing_checkout')
    if missing_co and missing_co.lower() in ('1', 'true', 'yes'):
        query = query.filter(
            Attendance.status == 'active',
            Attendance.check_in < today_start
        )

    # Filter: date range
    date_from = request.args.get('start_date') or request.args.get('date_from')
    if date_from:
        try:
            df = datetime.fromisoformat(date_from.strip())
            query = query.filter(Attendance.check_in >= datetime.combine(df.date(), datetime.min.time()))
        except ValueError:
            pass

    date_to = request.args.get('end_date') or request.args.get('date_to')
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to.strip())
            query = query.filter(Attendance.check_in <= datetime.combine(dt.date(), datetime.max.time()))
        except ValueError:
            pass

    # Filter: has_correction
    has_corr = request.args.get('has_correction')
    if has_corr and has_corr.lower() in ('1', 'true', 'yes'):
        query = query.join(AttendanceCorrection, Attendance.id == AttendanceCorrection.attendance_id)

    # Order
    query = query.order_by(Attendance.check_in.desc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 15, type=int), 100)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    now_naive = utc_now().replace(tzinfo=None)
    items = []
    for att in pagination.items:
        emp = att.user
        emp_name = (emp.full_name or emp.username) if emp else 'Unknown'
        emp_code = (emp.employee_id_code or f'EMP-{emp.id:04d}') if emp else ''
        role_name = emp.role if emp else ''
        team_name = emp.team.name if emp and emp.team else 'No Team'

        if att.status == 'active':
            ci = att.check_in.replace(tzinfo=None) if att.check_in.tzinfo else att.check_in
            cur_mins = max(0, int((now_naive - ci).total_seconds() / 60))
            hours = cur_mins // 60
            mins = cur_mins % 60
            duration_str = f"{hours}h {mins}m (Active)"
            duration_minutes = cur_mins
        else:
            duration_minutes = att.duration_minutes
            duration_str = format_duration(att.duration_minutes)

        latest_corr = att.corrections.order_by(AttendanceCorrection.created_at.desc()).first() if hasattr(att, 'corrections') else None

        items.append({
            'id': att.id,
            'user_id': att.user_id,
            'employee_name': emp_name,
            'employee_id_code': emp_code,
            'role': role_name,
            'team_id': emp.team_id if emp else None,
            'team_name': team_name,
            'check_in': att.check_in.isoformat() if att.check_in else None,
            'check_out': att.check_out.isoformat() if att.check_out else None,
            'duration_minutes': duration_minutes,
            'duration_hours': round(duration_minutes / 60.0, 2),
            'duration_display': duration_str,
            'status': att.status,
            'is_missing_checkout': bool(att.status == 'active' and att.check_in < today_start),
            'correction_status': latest_corr.status if latest_corr else None,
            'correction_id': latest_corr.id if latest_corr else None,
            'notes': att.notes or '',
            'can_review': bool(latest_corr and latest_corr.status == 'pending' and latest_corr.user_id != current_user.id and current_user.is_management),
        })

    return api_success({
        'items': items,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
    })


# ── Team & Organization Reports ────────────────────────────────────────────────

@attendance_bp.route('/team', methods=['GET'])
@login_required
@active_account_required
def team_attendance():
    """Team attendance overview for Admin and Team Lead."""
    if not current_user.is_management:
        return api_error('Permission denied to view team attendance.', 403)

    auth_user_ids = get_authorized_user_ids_for_user(current_user)
    if not auth_user_ids:
        return api_success([])

    members = User.query.filter(User.id.in_(auth_user_ids), User.account_active == True).all()

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    results = []
    now_naive = utc_now().replace(tzinfo=None)

    for m in members:
        today_att = Attendance.query.filter(
            Attendance.user_id == m.id,
            Attendance.check_in >= today_start,
            Attendance.check_in < today_end
        ).order_by(Attendance.check_in.desc()).first()

        current_duration_minutes = today_att.duration_minutes if today_att else 0
        if today_att and today_att.status == 'active':
            checkin_naive = today_att.check_in.replace(tzinfo=None) if today_att.check_in.tzinfo else today_att.check_in
            session_today_start = max(today_start, checkin_naive)
            current_duration_minutes = max(0, int((now_naive - session_today_start).total_seconds() / 60))

        results.append({
            'user_id': m.id,
            'name': m.full_name or m.username,
            'employee_id_code': m.employee_id_code or f'EMP-{m.id:04d}',
            'role': m.role,
            'email': m.email,
            'designation': m.designation,
            'team_id': m.team_id,
            'team_name': m.team.name if m.team else 'No Team',
            'status': today_att.status if today_att else 'not_checked_in',
            'check_in': today_att.check_in.isoformat() if today_att else None,
            'check_out': today_att.check_out.isoformat() if today_att and today_att.check_out else None,
            'duration_hours': round(current_duration_minutes / 60.0, 2),
            'duration_minutes': current_duration_minutes,
            'duration_display': format_duration(current_duration_minutes),
        })

    return api_success(results)


@attendance_bp.route('/organization', methods=['GET'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def org_attendance():
    """Organization-wide attendance statistics and records (Admin only)."""
    org_id = current_user.organization_id or 1
    recent = Attendance.query.join(User).filter(
        (User.organization_id == org_id) | (User.organization_id.is_(None))
    ).order_by(Attendance.check_in.desc()).limit(100).all()

    currently_active = Attendance.query.join(User).filter(
        Attendance.status == 'active',
        (User.organization_id == org_id) | (User.organization_id.is_(None))
    ).count()

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    checked_in_today = db.session.query(func.count(func.distinct(Attendance.user_id))).join(User).filter(
        Attendance.check_in >= today_start,
        Attendance.check_in < today_end,
        (User.organization_id == org_id) | (User.organization_id.is_(None))
    ).scalar() or 0

    return api_success({
        'currently_active_count': currently_active,
        'checked_in_today_count': checked_in_today,
        'records': [r.to_dict() for r in recent],
    })


# ── Correction Requests ────────────────────────────────────────────────────────

@attendance_bp.route('/corrections', methods=['GET', 'POST'])
@login_required
@active_account_required
def attendance_corrections():
    """List or submit attendance correction requests."""
    if request.method == 'GET':
        if current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
            corrections = AttendanceCorrection.query.order_by(AttendanceCorrection.created_at.desc()).all()
        elif current_user.has_role(ROLE_TEAM_LEAD):
            auth_user_ids = get_authorized_user_ids_for_user(current_user)
            corrections = AttendanceCorrection.query.filter(
                AttendanceCorrection.user_id.in_(auth_user_ids)
            ).order_by(AttendanceCorrection.created_at.desc()).all()
        else:
            corrections = AttendanceCorrection.query.filter_by(
                user_id=current_user.id
            ).order_by(AttendanceCorrection.created_at.desc()).all()

        return api_success([c.to_dict() for c in corrections])

    # POST: Submit correction request
    data = request.get_json(silent=True) or {}
    att_id = data.get('attendance_id')
    req_in_str = data.get('requested_check_in')
    req_out_str = data.get('requested_check_out')
    reason = (data.get('reason') or '').strip()

    if not req_in_str or not req_out_str or not reason:
        return api_error('Requested check-in, check-out, and reason are required.', 400)

    try:
        req_in = datetime.fromisoformat(req_in_str)
        req_out = datetime.fromisoformat(req_out_str)
    except ValueError:
        return api_error('Invalid datetime format. Use ISO format (YYYY-MM-DDTHH:MM).', 400)

    if req_out <= req_in:
        return api_error('Check-out must be after check-in.', 400)

    corr = AttendanceCorrection(
        attendance_id=int(att_id) if att_id else None,
        user_id=current_user.id,
        requested_check_in=req_in,
        requested_check_out=req_out,
        reason=reason,
        status='pending'
    )
    db.session.add(corr)
    db.session.commit()

    log_audit('attendance_correction_requested', 'AttendanceCorrection', corr.id, f'Correction requested by {current_user.username}')
    return api_success(corr.to_dict(), message='Correction request submitted for review.', status_code=201)


@attendance_bp.route('/corrections/<int:corr_id>/review', methods=['POST'])
@login_required
@active_account_required
def review_correction(corr_id):
    """Review (approve or reject) an attendance correction request."""
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD):
        return api_error('Permission denied to review attendance corrections.', 403)

    corr = AttendanceCorrection.query.get_or_404(corr_id)

    # 1. Self-review restriction: Users cannot review their own correction request
    if corr.user_id == current_user.id:
        return api_error('You cannot review or approve your own correction request.', 403)

    # 2. Team Lead scope check: Must belong to authorized team members
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        auth_user_ids = get_authorized_user_ids_for_user(current_user)
        if corr.user_id not in auth_user_ids:
            return api_error('Permission denied to review correction for an employee outside your authorized team.', 403)

    data = request.get_json(silent=True) or {}
    decision = (data.get('decision') or '').strip().lower()
    review_notes = (data.get('review_notes') or data.get('reason') or '').strip()

    if decision not in ('approve', 'reject'):
        return api_error("Decision must be 'approve' or 'reject'.", 400)

    corr.reviewed_by = current_user.id
    corr.reviewed_at = utc_now()

    if decision == 'approve':
        corr.status = 'approved'
        if corr.attendance_id:
            att = db.session.get(Attendance, corr.attendance_id)
            if att:
                att.check_in = corr.requested_check_in
                att.check_out = corr.requested_check_out
                att.status = 'corrected'
                att.calculate_duration()
                if review_notes:
                    att.notes = f"{att.notes} | Correction: {review_notes}" if att.notes else f"Correction: {review_notes}"
        else:
            att = Attendance(
                user_id=corr.user_id,
                organization_id=current_user.organization_id or 1,
                check_in=corr.requested_check_in,
                check_out=corr.requested_check_out,
                status='corrected',
                notes=f'Approved correction: {corr.reason}' + (f' | Reviewer: {review_notes}' if review_notes else '')
            )
            att.calculate_duration()
            db.session.add(att)
    else:
        corr.status = 'rejected'

    db.session.commit()

    send_notification(
        corr.user_id,
        f'Attendance Correction {corr.status.capitalize()}',
        f'Your attendance correction request was {corr.status} by {current_user.full_name or current_user.username}.',
        '/attendance',
        'attendance_alert'
    )

    log_audit(f'correction_{decision}d', 'AttendanceCorrection', corr.id, f'Correction {decision}d by {current_user.username}')
    return api_success(corr.to_dict(), message=f'Correction request {decision}d successfully.')


# ── Authorized Attendance CSV Export ──────────────────────────────────────────

@attendance_bp.route('/export', methods=['GET'])
@login_required
@active_account_required
def export_attendance_csv():
    """
    Export authorized attendance data to CSV.
    Admin gets organization-wide records. Team Lead gets only their authorized team scope.
    Employees are strictly forbidden (403).
    """
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD):
        return api_error('Permission denied to export attendance data.', 403)

    import io, csv
    auth_user_ids = get_authorized_user_ids_for_user(current_user)
    if not auth_user_ids:
        records = []
    else:
        query = Attendance.query.join(User, Attendance.user_id == User.id).filter(
            Attendance.user_id.in_(auth_user_ids)
        )

        # Filters
        target_user_id = request.args.get('user_id', type=int)
        if target_user_id and target_user_id in auth_user_ids:
            query = query.filter(Attendance.user_id == target_user_id)

        team_id = request.args.get('team_id', type=int)
        if team_id:
            if current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN) or team_id in get_authorized_team_ids_for_user(current_user):
                query = query.filter(User.team_id == team_id)

        role_filter = (request.args.get('role') or '').strip()
        if role_filter:
            query = query.filter(User.role == role_filter)

        status_filter = (request.args.get('status') or '').strip().lower()
        if status_filter in ('active', 'completed', 'corrected'):
            query = query.filter(Attendance.status == status_filter)

        today_start = datetime.combine(date.today(), datetime.min.time())
        missing_co = request.args.get('missing_checkout')
        if missing_co and missing_co.lower() in ('1', 'true', 'yes'):
            query = query.filter(Attendance.status == 'active', Attendance.check_in < today_start)

        date_from = request.args.get('start_date') or request.args.get('date_from')
        if date_from:
            try:
                df = datetime.fromisoformat(date_from.strip())
                query = query.filter(Attendance.check_in >= datetime.combine(df.date(), datetime.min.time()))
            except ValueError:
                pass

        date_to = request.args.get('end_date') or request.args.get('date_to')
        if date_to:
            try:
                dt = datetime.fromisoformat(date_to.strip())
                query = query.filter(Attendance.check_in <= datetime.combine(dt.date(), datetime.max.time()))
            except ValueError:
                pass

        records = query.order_by(Attendance.check_in.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Record ID', 'Employee Name', 'Employee ID', 'Role', 'Team',
        'Check-In', 'Check-Out', 'Duration (Hours)', 'Attendance Status',
        'Correction Status', 'Notes'
    ])

    for r in records:
        emp = r.user
        emp_name = (emp.full_name or emp.username) if emp else 'Unknown'
        emp_code = (emp.employee_id_code or f'EMP-{emp.id:04d}') if emp else ''
        role_name = emp.role if emp else ''
        team_name = emp.team.name if emp and emp.team else 'No Team'

        latest_corr = r.corrections.order_by(AttendanceCorrection.created_at.desc()).first() if hasattr(r, 'corrections') else None
        corr_status = latest_corr.status if latest_corr else 'None'

        writer.writerow([
            r.id,
            emp_name,
            emp_code,
            role_name,
            team_name,
            r.check_in.strftime('%Y-%m-%d %H:%M') if r.check_in else '',
            r.check_out.strftime('%Y-%m-%d %H:%M') if r.check_out else 'Active',
            round(r.duration_minutes / 60.0, 2),
            r.status,
            corr_status,
            r.notes or ''
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=attendance_export.csv'}
    )
