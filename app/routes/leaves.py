"""
Leave and Time-Off Management Blueprint (HR & Operations).
Handles leave requests, balances, manager approvals, team calendar, and CSV exports.
"""
import io
import csv
from datetime import datetime, date, timezone
from flask import Blueprint, request, Response, jsonify
from flask_login import current_user, login_required
from sqlalchemy import or_, and_
from app import db
from app.models import (
    User, Team, LeaveRequest, LeaveBalance,
    LEAVE_STATUS_PENDING, LEAVE_STATUS_APPROVED, LEAVE_STATUS_REJECTED, LEAVE_STATUS_CANCELLED,
    LEAVE_TYPE_VACATION, LEAVE_TYPE_SICK, LEAVE_TYPE_CASUAL, LEAVE_TYPE_UNPAID, LEAVE_TYPE_OTHER,
    ALL_LEAVE_TYPES,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD, ROLE_EMPLOYEE
)
from app.routes.utils import (
    api_success, api_error, active_account_required, roles_required,
    send_notification, log_audit
)

leaves_bp = Blueprint('leaves', __name__, url_prefix='/api/leaves')


def utc_now():
    return datetime.now(timezone.utc)


def parse_iso_date(date_str):
    """Safely parse YYYY-MM-DD string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


# ── Employee Endpoints ────────────────────────────────────────────────────────

@leaves_bp.route('/balance', methods=['GET'])
@login_required
@active_account_required
def get_leave_balance():
    """Get the current user's leave balance for the requested or current year."""
    try:
        year = int(request.args.get('year', date.today().year))
    except (TypeError, ValueError):
        year = date.today().year

    balance = current_user.get_or_create_leave_balance(year)
    return api_success(balance.to_dict())


@leaves_bp.route('/my', methods=['GET'])
@login_required
@active_account_required
def get_my_leaves():
    """Get all leave requests submitted by the logged-in employee."""
    requests = LeaveRequest.query.filter_by(user_id=current_user.id)\
        .order_by(LeaveRequest.created_at.desc()).all()
    return api_success([r.to_dict() for r in requests])


@leaves_bp.route('', methods=['POST'])
@login_required
@active_account_required
def apply_leave():
    """
    Submit a new leave application with date validation, overlap check,
    and balance availability verification.
    """
    data = request.get_json() or {}
    leave_type = (data.get('leave_type') or '').strip().lower()
    start_str = data.get('start_date')
    end_str = data.get('end_date')
    reason = (data.get('reason') or '').strip()

    if not leave_type or leave_type not in ALL_LEAVE_TYPES:
        return api_error(f"Invalid leave type. Allowed: {', '.join(ALL_LEAVE_TYPES)}", 400)

    start_d = parse_iso_date(start_str)
    end_d = parse_iso_date(end_str)

    if not start_d or not end_d:
        return api_error("Start date and end date are required in YYYY-MM-DD format.", 400)

    if end_d < start_d:
        return api_error("End date cannot precede start date.", 400)

    if not reason:
        return api_error("A reason for the leave request is required.", 400)

    days_count = (end_d - start_d).days + 1
    if days_count <= 0:
        return api_error("Leave duration must be at least 1 day.", 400)

    # Prevent overlapping active or pending leave applications for this user
    overlapping = LeaveRequest.query.filter(
        LeaveRequest.user_id == current_user.id,
        LeaveRequest.status.in_([LEAVE_STATUS_PENDING, LEAVE_STATUS_APPROVED]),
        LeaveRequest.start_date <= end_d,
        LeaveRequest.end_date >= start_d
    ).first()

    if overlapping:
        return api_error(
            f"You already have a {overlapping.status} leave request from "
            f"{overlapping.start_date} to {overlapping.end_date}.", 409
        )

    # Check leave balance if type is vacation, sick, or casual
    current_year = start_d.year
    balance = current_user.get_or_create_leave_balance(current_year)
    if leave_type == LEAVE_TYPE_VACATION and balance.annual_used + days_count > balance.annual_total:
        avail = max(0.0, balance.annual_total - balance.annual_used)
        return api_error(f"Insufficient annual leave balance. Requested: {days_count}, Available: {avail}", 400)
    elif leave_type == LEAVE_TYPE_SICK and balance.sick_used + days_count > balance.sick_total:
        avail = max(0.0, balance.sick_total - balance.sick_used)
        return api_error(f"Insufficient sick leave balance. Requested: {days_count}, Available: {avail}", 400)
    elif leave_type == LEAVE_TYPE_CASUAL and balance.casual_used + days_count > balance.casual_total:
        avail = max(0.0, balance.casual_total - balance.casual_used)
        return api_error(f"Insufficient casual leave balance. Requested: {days_count}, Available: {avail}", 400)

    req = LeaveRequest(
        user_id=current_user.id,
        leave_type=leave_type,
        start_date=start_d,
        end_date=end_d,
        days_count=float(days_count),
        reason=reason,
        status=LEAVE_STATUS_PENDING
    )
    db.session.add(req)
    db.session.commit()

    # Notify team lead or manager if assigned
    applicant_name = current_user.full_name or current_user.username
    notif_title = f"New Leave Request: {applicant_name}"
    notif_msg = f"{applicant_name} applied for {days_count} day(s) of {leave_type} leave ({start_d} to {end_d})."

    if current_user.manager_id:
        send_notification(current_user.manager_id, notif_title, notif_msg, link='/leaves', notif_type='leave_request')
    elif current_user.team and current_user.team.lead_id and current_user.team.lead_id != current_user.id:
        send_notification(current_user.team.lead_id, notif_title, notif_msg, link='/leaves', notif_type='leave_request')
    else:
        # Notify admins
        admins = User.query.filter(User.role.in_([ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR])).all()
        for admin in admins:
            if admin.id != current_user.id:
                send_notification(admin.id, notif_title, notif_msg, link='/leaves', notif_type='leave_request')

    log_audit('leave_applied', 'LeaveRequest', req.id, f"Applied for {days_count}d {leave_type} leave")

    return api_success(req.to_dict(), "Leave application submitted successfully.", 201)


@leaves_bp.route('/<int:leave_id>/cancel', methods=['PUT'])
@login_required
@active_account_required
def cancel_leave(leave_id):
    """Allow an employee to cancel their own pending leave request."""
    req = db.session.get(LeaveRequest, leave_id)
    if not req:
        return api_error("Leave request not found.", 404)

    if req.user_id != current_user.id and not current_user.is_admin:
        return api_error("You do not have permission to cancel this leave request.", 403)

    if req.status != LEAVE_STATUS_PENDING:
        return api_error(f"Cannot cancel a leave request that is already {req.status}.", 400)

    req.status = LEAVE_STATUS_CANCELLED
    db.session.commit()

    log_audit('leave_cancelled', 'LeaveRequest', req.id, "Employee cancelled leave request")
    return api_success(req.to_dict(), "Leave request cancelled.")


# ── Management Endpoints (Leads, HR, Admins) ─────────────────────────────────

@leaves_bp.route('/pending', methods=['GET'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD)
def get_pending_leaves():
    """
    Get pending leave requests.
    Team Leads see requests from their team members; Admins and HR see all.
    """
    query = LeaveRequest.query.filter_by(status=LEAVE_STATUS_PENDING)

    if current_user.role == ROLE_TEAM_LEAD:
        if current_user.team_id:
            # Query users in the same team
            team_user_ids = [u.id for u in User.query.filter_by(team_id=current_user.team_id).all()]
            query = query.filter(LeaveRequest.user_id.in_(team_user_ids))
        else:
            query = query.filter(LeaveRequest.user_id == current_user.id)

    requests = query.order_by(LeaveRequest.created_at.asc()).all()
    return api_success([r.to_dict() for r in requests])


@leaves_bp.route('/all', methods=['GET'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD)
def get_all_leaves():
    """Get all leave history with optional status and type filters."""
    query = LeaveRequest.query

    status_filter = request.args.get('status')
    if status_filter:
        query = query.filter_by(status=status_filter)

    type_filter = request.args.get('leave_type')
    if type_filter:
        query = query.filter_by(leave_type=type_filter)

    if current_user.role == ROLE_TEAM_LEAD:
        if current_user.team_id:
            team_user_ids = [u.id for u in User.query.filter_by(team_id=current_user.team_id).all()]
            query = query.filter(LeaveRequest.user_id.in_(team_user_ids))
        else:
            query = query.filter(LeaveRequest.user_id == current_user.id)

    requests = query.order_by(LeaveRequest.created_at.desc()).all()
    return api_success([r.to_dict() for r in requests])


@leaves_bp.route('/<int:leave_id>/review', methods=['PUT'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD)
def review_leave(leave_id):
    """
    Approve or reject a leave request.
    If approved, deducts used days from the employee's LeaveBalance.
    """
    req = db.session.get(LeaveRequest, leave_id)
    if not req:
        return api_error("Leave request not found.", 404)

    if req.status != LEAVE_STATUS_PENDING:
        return api_error(f"This leave request has already been reviewed ({req.status}).", 400)

    # Check permission boundary: team leads can only review members of their team
    if current_user.role == ROLE_TEAM_LEAD:
        applicant = req.user
        if not applicant or applicant.team_id != current_user.team_id:
            return api_error("You can only review leave requests for your team members.", 403)

    data = request.get_json() or {}
    decision = (data.get('decision') or data.get('action') or '').strip().lower()
    review_notes = (data.get('review_notes') or '').strip()

    if decision not in ('approved', 'rejected'):
        return api_error("Decision must be either 'approved' or 'rejected'.", 400)

    req.reviewed_by = current_user.id
    req.reviewer_id = current_user.id
    req.reviewed_at = utc_now()
    req.review_notes = review_notes

    if decision == 'approved':
        req.status = LEAVE_STATUS_APPROVED
        # Deduct balance
        applicant = req.user
        balance = applicant.get_or_create_leave_balance(req.start_date.year)
        if req.leave_type == LEAVE_TYPE_VACATION:
            balance.annual_used += req.days_count
        elif req.leave_type == LEAVE_TYPE_SICK:
            balance.sick_used += req.days_count
        elif req.leave_type == LEAVE_TYPE_CASUAL:
            balance.casual_used += req.days_count
    else:
        req.status = LEAVE_STATUS_REJECTED

    db.session.commit()

    # Notify employee
    reviewer_name = current_user.full_name or current_user.username
    notif_title = f"Leave Request {decision.title()}"
    notif_msg = f"Your {req.leave_type} leave from {req.start_date} to {req.end_date} has been {decision} by {reviewer_name}."
    if review_notes:
        notif_msg += f" Note: {review_notes}"
    send_notification(req.user_id, notif_title, notif_msg, link='/leaves', notif_type='leave_decision')

    log_audit(f'leave_{decision}', 'LeaveRequest', req.id, f"Decision: {decision}. Notes: {review_notes}")

    return api_success(req.to_dict(), f"Leave request {decision} successfully.")


# ── Calendar & Export ─────────────────────────────────────────────────────────

@leaves_bp.route('/calendar', methods=['GET'])
@login_required
@active_account_required
def get_leave_calendar():
    """
    Get all approved leaves within an optional month/year range
    for the Team Leave Calendar (Who's Away).
    """
    query = LeaveRequest.query.filter_by(status=LEAVE_STATUS_APPROVED)

    # Optional month and year filters
    month = request.args.get('month')
    year = request.args.get('year')
    if year:
        try:
            y = int(year)
            query = query.filter(db.extract('year', LeaveRequest.start_date) == y)
        except ValueError:
            pass
    if month:
        try:
            m = int(month)
            query = query.filter(db.extract('month', LeaveRequest.start_date) == m)
        except ValueError:
            pass

    # Filter to user's team if not management
    if current_user.role == ROLE_EMPLOYEE and current_user.team_id:
        team_user_ids = [u.id for u in User.query.filter_by(team_id=current_user.team_id).all()]
        query = query.filter(LeaveRequest.user_id.in_(team_user_ids))

    leaves = query.order_by(LeaveRequest.start_date.asc()).all()
    return api_success([l.to_dict() for l in leaves])


@leaves_bp.route('/export', methods=['GET'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD)
def export_leaves_csv():
    """Export organizational leave records as a downloadable CSV."""
    query = LeaveRequest.query

    if current_user.role == ROLE_TEAM_LEAD and current_user.team_id:
        team_user_ids = [u.id for u in User.query.filter_by(team_id=current_user.team_id).all()]
        query = query.filter(LeaveRequest.user_id.in_(team_user_ids))

    records = query.order_by(LeaveRequest.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Request ID', 'Employee Name', 'Employee Code', 'Department', 'Team',
        'Leave Type', 'Start Date', 'End Date', 'Days Count', 'Status',
        'Reason', 'Reviewer', 'Review Notes', 'Reviewed At', 'Applied At'
    ])

    for r in records:
        emp = r.user
        emp_name = (emp.full_name or emp.username) if emp else 'Unknown'
        emp_code = emp.employee_id_code if emp else ''
        dept_name = emp.department.name if emp and emp.department else ''
        team_name = emp.team.name if emp and emp.team else ''
        rev_name = (r.reviewer.full_name or r.reviewer.username) if r.reviewer else ''
        rev_at = r.reviewed_at.strftime('%Y-%m-%d %H:%M') if r.reviewed_at else ''
        app_at = r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''

        writer.writerow([
            r.id, emp_name, emp_code, dept_name, team_name,
            r.leave_type, r.start_date.isoformat(), r.end_date.isoformat(),
            r.days_count, r.status, r.reason, rev_name, r.review_notes or '',
            rev_at, app_at
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=tasknest_leave_records.csv'}
    )
