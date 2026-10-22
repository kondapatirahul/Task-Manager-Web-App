"""
Attendance, Timesheets, and Correction Requests API routes.
"""
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, request
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


# ── Today's Status ─────────────────────────────────────────────────────────────

@attendance_bp.route('/today', methods=['GET'])
@login_required
@active_account_required
def get_today_status():
    """Return user's check-in state today and active session."""
    active_session = Attendance.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).first()

    today_start = datetime.combine(date.today(), datetime.min.time())
    completed_today = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        Attendance.check_in >= today_start,
        Attendance.status.in_(['completed', 'corrected'])
    ).all()

    total_minutes = sum(a.duration_minutes for a in completed_today)

    active_duration_minutes = 0
    if active_session:
        delta = utc_now() - active_session.check_in.replace(tzinfo=timezone.utc if active_session.check_in.tzinfo is None else active_session.check_in.tzinfo)
        active_duration_minutes = max(0, int(delta.total_seconds() / 60))
        total_minutes += active_duration_minutes

    return api_success({
        'is_checked_in': active_session is not None,
        'active_session': active_session.to_dict() if active_session else None,
        'today_duration_minutes': total_minutes,
        'today_duration_hours': round(total_minutes / 60.0, 2),
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
    seven_days_ago = date.today() - timedelta(days=7)
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

    return api_success({
        'records': [r.to_dict() for r in records],
        'weekly_hours': round(weekly_minutes / 60.0, 2),
        'missing_checkouts_count': missing_checkouts,
    })


# ── Team & Organization Reports ────────────────────────────────────────────────

@attendance_bp.route('/team', methods=['GET'])
@login_required
@active_account_required
def team_attendance():
    if not current_user.is_management:
        return api_error('Permission denied to view team attendance.', 403)

    # If lead, get lead's teams; if admin, get all teams
    if current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        members = User.query.filter_by(account_active=True).all()
    else:
        led_teams = Team.query.filter_by(lead_id=current_user.id).all()
        team_ids = [t.id for t in led_teams]
        if current_user.team_id and current_user.team_id not in team_ids:
            team_ids.append(current_user.team_id)
        members = User.query.filter(User.team_id.in_(team_ids), User.account_active == True).all()

    today_start = datetime.combine(date.today(), datetime.min.time())
    results = []
    for m in members:
        today_att = Attendance.query.filter(
            Attendance.user_id == m.id,
            Attendance.check_in >= today_start
        ).order_by(Attendance.check_in.desc()).first()

        results.append({
            'user_id': m.id,
            'name': m.full_name or m.username,
            'email': m.email,
            'designation': m.designation,
            'team_id': m.team_id,
            'status': today_att.status if today_att else 'not_checked_in',
            'check_in': today_att.check_in.isoformat() if today_att else None,
            'check_out': today_att.check_out.isoformat() if today_att and today_att.check_out else None,
            'duration_hours': round(today_att.duration_minutes / 60.0, 2) if today_att else 0.0,
        })

    return api_success(results)


@attendance_bp.route('/organization', methods=['GET'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def org_attendance():
    """Organization-wide attendance statistics and records."""
    org_id = current_user.organization_id or 1
    recent = Attendance.query.join(User).filter(
        (User.organization_id == org_id) | (User.organization_id.is_(None))
    ).order_by(Attendance.check_in.desc()).limit(100).all()

    # Active count right now
    currently_active = Attendance.query.join(User).filter(
        Attendance.status == 'active',
        (User.organization_id == org_id) | (User.organization_id.is_(None))
    ).count()

    return api_success({
        'currently_active_count': currently_active,
        'records': [r.to_dict() for r in recent],
    })


# ── Correction Requests ────────────────────────────────────────────────────────

@attendance_bp.route('/corrections', methods=['GET', 'POST'])
@login_required
@active_account_required
def attendance_corrections():
    if request.method == 'GET':
        if current_user.is_management:
            corrections = AttendanceCorrection.query.order_by(AttendanceCorrection.created_at.desc()).all()
        else:
            corrections = AttendanceCorrection.query.filter_by(user_id=current_user.id).order_by(AttendanceCorrection.created_at.desc()).all()
        return api_success([c.to_dict() for c in corrections])

    # POST correction request
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
    if not current_user.is_management:
        return api_error('Permission denied to review attendance corrections.', 403)

    corr = AttendanceCorrection.query.get_or_404(corr_id)
    data = request.get_json(silent=True) or {}
    decision = (data.get('decision') or '').strip().lower()

    if decision not in ('approve', 'reject'):
        return api_error("Decision must be 'approve' or 'reject'.", 400)

    corr.reviewed_by = current_user.id
    corr.reviewed_at = utc_now()

    if decision == 'approve':
        corr.status = 'approved'
        if corr.attendance_id:
            att = Attendance.query.get(corr.attendance_id)
            if att:
                att.check_in = corr.requested_check_in
                att.check_out = corr.requested_check_out
                att.status = 'corrected'
                att.calculate_duration()
        else:
            # Create new attendance record
            att = Attendance(
                user_id=corr.user_id,
                organization_id=current_user.organization_id or 1,
                check_in=corr.requested_check_in,
                check_out=corr.requested_check_out,
                status='corrected',
                notes=f'Approved correction: {corr.reason}'
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

    log_audit(f'correction_{decision}d', 'AttendanceCorrection', corr.id, f'Correction {decision}d')
    return api_success(corr.to_dict(), message=f'Correction {decision}d.')
