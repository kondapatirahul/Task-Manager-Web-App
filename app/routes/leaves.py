<<<<<<< HEAD
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

=======
"""Leave requests with server-side team-lead authorization."""
from datetime import date, datetime
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_, func, extract
from app import db
from app.models import LeaveRequest, User, Team, TeamMember, ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
from app.routes.utils import api_success, api_error, active_account_required, send_notification

leaves_bp = Blueprint('leaves', __name__, url_prefix='/api/leaves')
LEAVE_LIMITS = {'casual': 12, 'sick': 10, 'personal': 5}


def _is_admin():
    return current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr', 'hr')


def _team_lead_can_review(employee):
    if employee.organization_id != current_user.organization_id:
        return False
    if employee.manager_id == current_user.id:
        return True
    teams = Team.query.filter_by(lead_id=current_user.id).all()
    team_ids = {t.id for t in teams}
    if employee.team_id in team_ids:
        return True
    return TeamMember.query.filter(TeamMember.user_id == employee.id, TeamMember.team_id.in_(team_ids)).first() is not None if team_ids else False


def _can_review(req):
    if current_user.role == ROLE_SUPER_ADMIN:
        return True
    if _is_admin():
        return req.employee.organization_id == current_user.organization_id
    return current_user.role == ROLE_TEAM_LEAD and _team_lead_can_review(req.employee)


def _balance(user_id, leave_type, year):
    limit = LEAVE_LIMITS[leave_type]
    used = db.session.query(func.coalesce(func.sum(LeaveRequest.days), 0)).filter(
        LeaveRequest.user_id == user_id, LeaveRequest.leave_type == leave_type,
        LeaveRequest.status == 'approved', extract('year', LeaveRequest.start_date) == year
    ).scalar() or 0
    pending = db.session.query(func.coalesce(func.sum(LeaveRequest.days), 0)).filter(
        LeaveRequest.user_id == user_id, LeaveRequest.leave_type == leave_type,
        LeaveRequest.status == 'pending', extract('year', LeaveRequest.start_date) == year
    ).scalar() or 0
    return {'type': leave_type, 'allowance': limit, 'approved_days': int(used), 'pending_days': int(pending), 'remaining': max(0, limit-int(used))}


@leaves_bp.route('', methods=['GET', 'POST'])
@login_required
@active_account_required
def leave_collection():
    if request.method == 'GET':
        if current_user.role == ROLE_TEAM_LEAD or _is_admin():
            requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).limit(500).all()
            requests = [r for r in requests if _can_review(r) or r.user_id == current_user.id]
        else:
            requests = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(LeaveRequest.created_at.desc()).all()
        balances = [_balance(current_user.id, kind, date.today().year) for kind in LEAVE_LIMITS]
        return api_success({'requests': [r.to_dict() for r in requests], 'balances': balances, 'limits': LEAVE_LIMITS})

    data = request.get_json(silent=True) or request.form
    kind = str(data.get('leave_type', '')).strip().lower()
    reason = str(data.get('reason', '')).strip()
    try:
        start = date.fromisoformat(str(data.get('start_date', '')))
        end = date.fromisoformat(str(data.get('end_date', '')))
    except (TypeError, ValueError):
        return api_error('Valid start and end dates are required.', 400)
    if kind not in LEAVE_LIMITS:
        return api_error('Leave type must be Casual, Sick, or Personal.', 400)
    if end < start:
        return api_error('End date cannot be before start date.', 400)
    if start < date.today():
        return api_error('Leave start date cannot be in the past.', 400)
    if not reason or len(reason) > 1000:
        return api_error('Reason is required and must be at most 1000 characters.', 400)
    overlap = LeaveRequest.query.filter(
        LeaveRequest.user_id == current_user.id,
        LeaveRequest.status.in_(['pending', 'approved']),
        LeaveRequest.start_date <= end, LeaveRequest.end_date >= start
    ).first()
    if overlap:
        return api_error('This request overlaps an existing pending or approved leave.', 409)
    days = (end - start).days + 1
    balance = _balance(current_user.id, kind, start.year)
    if start.year != end.year:
        return api_error('A leave request must be within one calendar year.', 400)
    if days + balance['approved_days'] + balance['pending_days'] > balance['allowance']:
        return api_error('Requested days exceed the available leave allowance.', 400)
    req = LeaveRequest(user_id=current_user.id, leave_type=kind, start_date=start, end_date=end, days=days, reason=reason, status='pending')
    db.session.add(req)
    db.session.commit()
    # Notify the actual manager/team lead when a reviewer relationship exists.
    reviewer_ids = set()
    if current_user.manager_id:
        reviewer_ids.add(current_user.manager_id)
    if current_user.team_id:
        team = db.session.get(Team, current_user.team_id)
        if team and team.lead_id:
            reviewer_ids.add(team.lead_id)
    for rid in reviewer_ids:
        send_notification(rid, 'Leave request submitted', f'{current_user.full_name or current_user.username} submitted a {kind} leave request.', '/lead/leave-requests', 'leave_request', f'leave-submit-{req.id}-{rid}')
    return api_success(req.to_dict(), message='Leave request submitted.', status_code=201)


@leaves_bp.route('/<int:request_id>/decision', methods=['POST'])
@login_required
@active_account_required
def leave_decision(request_id):
    req = db.session.get(LeaveRequest, request_id)
    if not req:
        return api_error('Leave request not found.', 404)
    if not _can_review(req):
        return api_error('You are not authorized to review this employee leave request.', 403)
    if req.status != 'pending':
        return api_error('This request has already been decided.', 409)
    data = request.get_json(silent=True) or {}
    decision = str(data.get('status', '')).strip().lower()
    comment = str(data.get('comment', '')).strip()
    if decision not in ('approved', 'rejected'):
        return api_error('Decision must be approved or rejected.', 400)
    if decision == 'rejected' and not comment:
        return api_error('A comment is required when rejecting a request.', 400)
    if len(comment) > 1000:
        return api_error('Comment must be at most 1000 characters.', 400)
    if decision == 'approved':
        current_balance = _balance(req.user_id, req.leave_type, req.start_date.year)
        if current_balance['approved_days'] + req.days > current_balance['allowance']:
            return api_error('Insufficient leave balance to approve this request.', 409)
    req.status = decision
    req.reviewer_id = current_user.id
    req.reviewer_comment = comment
    req.decided_at = datetime.utcnow()
    db.session.commit()
    send_notification(req.user_id, f'Leave request {decision}', f'Your {req.leave_type} leave request ({req.start_date} to {req.end_date}) was {decision}. {comment}'.strip(), '/employee/leave', 'leave_decision', f'leave-decision-{req.id}')
    return api_success(req.to_dict(), message=f'Leave request {decision}.')
>>>>>>> origin/main
