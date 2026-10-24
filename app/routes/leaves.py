"""
Leave Requests and Management API routes.
Supports employee request submission, team lead review scoping, and admin organization-wide management.
"""
from datetime import datetime, date, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.models import (
    LeaveRequest, User, Team, TeamMember,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
)
from app.routes.utils import (
    api_success, api_error, active_account_required,
    send_notification, log_audit
)

leaves_bp = Blueprint('leaves', __name__, url_prefix='/api/leaves')

VALID_LEAVE_TYPES = {
    'Casual', 'Sick', 'Annual', 'Maternity/Paternity', 'Unpaid', 'Other'
}


def utc_now():
    return datetime.now(timezone.utc)


def parse_date(date_str):
    if not date_str:
        return None
    try:
        clean = str(date_str).split('T')[0].strip()
        return datetime.strptime(clean, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


# ── GET /api/leaves/my — Employee's own leave requests ─────────────────────────

@leaves_bp.route('/my', methods=['GET'])
@login_required
@active_account_required
def my_leaves():
    """Return all leave requests submitted by the authenticated user."""
    requests = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(
        LeaveRequest.created_at.desc()
    ).all()
    return api_success([r.to_dict() for r in requests])


# ── POST /api/leaves — Submit a new leave request ──────────────────────────────

@leaves_bp.route('', methods=['POST'])
@login_required
@active_account_required
def submit_leave():
    """Submit a leave request as the currently authenticated user."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    
    leave_type = (data.get('leave_type') or 'Casual').strip()
    if leave_type not in VALID_LEAVE_TYPES:
        leave_type = 'Other'

    start_date = parse_date(data.get('start_date'))
    end_date = parse_date(data.get('end_date'))
    reason = (data.get('reason') or '').strip()

    if not start_date or not end_date:
        return api_error('Valid start and end dates are required (YYYY-MM-DD).', 400)

    if end_date < start_date:
        return api_error('End date cannot be earlier than start date.', 400)

    if not reason:
        return api_error('Please provide a reason for the leave request.', 400)

    # Check for overlapping pending or approved leave requests for this user
    overlap = LeaveRequest.query.filter(
        LeaveRequest.user_id == current_user.id,
        LeaveRequest.status.in_(['pending', 'approved']),
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date
    ).first()

    if overlap:
        return api_error(
            f'You already have a {overlap.status} leave request overlapping this date range ({overlap.start_date} to {overlap.end_date}).',
            400
        )

    leave = LeaveRequest(
        user_id=current_user.id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status='pending'
    )
    db.session.add(leave)
    db.session.flush()

    # Notify team lead or admins
    emp_name = current_user.full_name or current_user.username
    notif_msg = f"{emp_name} requested {leave_type} leave from {start_date} to {end_date}."

    # If employee belongs to a team with a lead, notify lead
    notified = False
    if current_user.team and current_user.team.lead_id and current_user.team.lead_id != current_user.id:
        send_notification(
            current_user.team.lead_id,
            'New Leave Request',
            notif_msg,
            '/leaves',
            'leave_request'
        )
        notified = True

    # Also notify admins if no lead or additionally
    admins = User.query.filter(User.role.in_([ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr']), User.account_active == True).all()
    for admin in admins:
        if admin.id != current_user.id:
            send_notification(
                admin.id,
                'New Leave Request',
                notif_msg,
                '/leaves',
                'leave_request'
            )

    db.session.commit()
    log_audit('leave_submitted', 'LeaveRequest', leave.id, f'Submitted {leave_type} leave ({start_date} to {end_date})')
    return api_success(leave.to_dict(), message='Leave request submitted successfully.', status_code=201)


# ── GET /api/leaves/team — Team Lead team leave requests ────────────────────────

@leaves_bp.route('/team', methods=['GET'])
@login_required
@active_account_required
def team_leaves():
    """Return leave requests for members of teams led by the authenticated Team Lead."""
    if not (current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr') or current_user.is_team_lead):
        return api_error('Permission denied to view team leave requests.', 403)

    query = LeaveRequest.query.join(User, LeaveRequest.user_id == User.id)

    if current_user.role == ROLE_TEAM_LEAD:
        led_teams = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
        if current_user.team_id and current_user.team_id not in led_teams:
            led_teams.append(current_user.team_id)

        # Team member user IDs
        team_member_ids = [
            m.user_id for m in TeamMember.query.filter(TeamMember.team_id.in_(led_teams)).all()
        ]
        # Include users directly in user.team_id
        direct_member_ids = [
            u.id for u in User.query.filter(User.team_id.in_(led_teams)).all()
        ]
        authorized_user_ids = set(team_member_ids + direct_member_ids)
        if current_user.id in authorized_user_ids:
            # TL can view their team members' requests
            pass
        query = query.filter(User.id.in_(authorized_user_ids))

    status_filter = request.args.get('status')
    if status_filter:
        query = query.filter(LeaveRequest.status == status_filter.lower())

    leaves = query.order_by(LeaveRequest.created_at.desc()).all()
    return api_success([l.to_dict() for l in leaves])


# ── GET /api/leaves — Admin view all organization leave requests ────────────────

@leaves_bp.route('', methods=['GET'])
@login_required
@active_account_required
def list_leaves():
    """Admin endpoint to view all leave requests organization-wide."""
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr'):
        # If team lead calls this, redirect logic to team scope
        if current_user.is_team_lead:
            return team_leaves()
        return api_error('Administrator permissions required to view organization leaves.', 403)

    query = LeaveRequest.query.join(User, LeaveRequest.user_id == User.id)

    status_filter = request.args.get('status')
    if status_filter:
        query = query.filter(LeaveRequest.status == status_filter.lower())

    team_id = request.args.get('team_id')
    if team_id:
        try:
            tid = int(team_id)
            query = query.filter(User.team_id == tid)
        except ValueError:
            pass

    leaves = query.order_by(LeaveRequest.created_at.desc()).all()
    return api_success([l.to_dict() for l in leaves])


# ── POST /api/leaves/<id>/review — Approve or Reject a leave request ───────────

@leaves_bp.route('/<int:leave_id>/review', methods=['POST'])
@login_required
@active_account_required
def review_leave(leave_id):
    """Review (approve/reject) a leave request."""
    leave = LeaveRequest.query.get_or_404(leave_id)

    # Check permission: Admin organization-wide, or TL for authorized team members
    is_admin = current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr')
    is_tl = current_user.is_team_lead

    if not (is_admin or is_tl):
        return api_error('Permission denied to review leave requests.', 403)

    # Prevent self-approval
    if leave.user_id == current_user.id and not is_admin:
        return api_error('You cannot approve or reject your own leave request.', 403)

    if is_tl and not is_admin:
        led_teams = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
        if current_user.team_id and current_user.team_id not in led_teams:
            led_teams.append(current_user.team_id)

        team_member_ids = set([
            m.user_id for m in TeamMember.query.filter(TeamMember.team_id.in_(led_teams)).all()
        ] + [
            u.id for u in User.query.filter(User.team_id.in_(led_teams)).all()
        ])

        if leave.user_id not in team_member_ids:
            return api_error('You can only review leave requests from members of your authorized team.', 403)

    if leave.status != 'pending':
        return api_error(f'This leave request has already been {leave.status}.', 400)

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    decision = (data.get('decision') or data.get('action') or '').strip().lower()
    comment = (data.get('comment') or data.get('reviewer_comment') or '').strip()

    if decision not in ('approve', 'approved', 'reject', 'rejected'):
        return api_error("Decision must be 'approve' or 'reject'.", 400)

    now = utc_now()
    final_status = 'approved' if decision in ('approve', 'approved') else 'rejected'

    leave.status = final_status
    leave.reviewer_id = current_user.id
    leave.reviewer_comment = comment
    leave.decision_at = now

    # Send persistent notification to employee
    reviewer_name = current_user.full_name or current_user.username
    status_label = 'Approved' if final_status == 'approved' else 'Rejected'
    note_snippet = f" Feedback: {comment}" if comment else ""
    send_notification(
        leave.user_id,
        f'Leave Request {status_label}',
        f'Your {leave.leave_type} leave request ({leave.start_date} to {leave.end_date}) was {final_status} by {reviewer_name}.{note_snippet}',
        '/leaves',
        'leave_decision'
    )

    db.session.commit()
    log_audit('leave_reviewed', 'LeaveRequest', leave.id, f'Leave {final_status} by {reviewer_name}')
    return api_success(leave.to_dict(), message=f'Leave request has been {final_status}.')

