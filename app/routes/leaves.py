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
