"""
Productivity Analytics and CSV Export API routes.
"""
import io
import csv
from datetime import datetime, date, timedelta
from flask import Blueprint, request, Response
from flask_login import current_user, login_required
from sqlalchemy import case, func, or_
from app import db
from app.models import (
    Task, Attendance, User, Team,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
)
from app.routes.utils import api_success, api_error, active_account_required, roles_required

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')


@reports_bp.route('/productivity', methods=['GET'])
@login_required
@active_account_required
def productivity_metrics():
    """Return report data in the contract consumed by templates/reports.html and tests."""
    raw_days = request.args.get('range_days', request.args.get('days'))
    if raw_days is not None:
        try:
            days = int(raw_days)
            if days <= 0:
                return api_error('Invalid range_days parameter.', 400)
        except (TypeError, ValueError):
            return api_error('Invalid range_days parameter.', 400)
    else:
        days = 30

    today = date.today()
    start_date = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_date = today
    end_dt = datetime.combine(end_date, datetime.max.time())

    query = Task.query
    if current_user.role == ROLE_TEAM_LEAD:
        if current_user.team_id:
            query = query.filter((Task.team_id == current_user.team_id) | (Task.assignee_id == current_user.id) | (Task.user_id == current_user.id))
        else:
            query = query.filter((Task.assignee_id == current_user.id) | (Task.user_id == current_user.id))
    elif current_user.role not in (ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr'):
        query = query.filter((Task.assignee_id == current_user.id) | (Task.user_id == current_user.id))

    tasks = query.all()
    total_tasks_count = len(tasks)

    # In-range completed tasks (completed_at within range)
    completed_in_range = [
        t for t in tasks
        if t.status == 'completed' and t.completed_at and t.completed_at >= start_dt and t.completed_at <= end_dt
    ]

    # Overdue incomplete tasks
    overdue_incomplete = [
        t for t in tasks
        if t.status != 'completed' and t.due_date and t.due_date < today
    ]

    # Blocked tasks
    blocked_tasks = [t for t in tasks if t.status == 'blocked']

    # On time rate for completed tasks within range
    on_time = sum(1 for t in completed_in_range if not t.due_date or (t.completed_at and t.completed_at.date() <= t.due_date))
    on_time_rate = round(on_time * 100.0 / len(completed_in_range), 1) if completed_in_range else 0.0

    trend = { (start_date + timedelta(days=i)).isoformat(): 0 for i in range(days) }
    for task in completed_in_range:
        if task.completed_at:
            key = task.completed_at.date().isoformat()
            if key in trend:
                trend[key] += 1

    status_distribution = {}
    priority_distribution = {}
    for task in tasks:
        status_distribution[task.status] = status_distribution.get(task.status, 0) + 1
        priority = task.priority or 'medium'
        priority_distribution[priority] = priority_distribution.get(priority, 0) + 1

    workload_distribution = []
    if current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr', ROLE_TEAM_LEAD):
        users_query = User.query.filter_by(account_active=True)
        if current_user.role == ROLE_TEAM_LEAD:
            users_query = users_query.filter((User.team_id == current_user.team_id) if current_user.team_id else (User.id == current_user.id))
        for user in users_query.order_by(User.full_name, User.username).all():
            assigned = [t for t in tasks if (t.assignee_id or t.user_id) == user.id]
            active_count = sum(1 for t in assigned if t.status != 'completed')
            completed_count = sum(1 for t in assigned if t.status == 'completed' and t.completed_at and t.completed_at >= start_dt and t.completed_at <= end_dt)
            if assigned:
                workload_distribution.append({
                    'user_id': user.id,
                    'name': user.full_name or user.username,
                    'active_tasks': active_count,
                    'completed_tasks': completed_count,
                })

    return api_success({
        'range_days': days,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'total_tasks': total_tasks_count,
        'metrics': {
            'total_tasks': total_tasks_count,
            'completed_tasks': len(completed_in_range),
            'overdue_incomplete_tasks': len(overdue_incomplete),
            'blocked_tasks': len(blocked_tasks),
            'on_time_rate': on_time_rate,
        },
        'completion_trends': [{'date': day, 'completed_count': count} for day, count in trend.items()],
        'status_distribution': status_distribution,
        'priority_distribution': priority_distribution,
        'workload_distribution': workload_distribution,
    })


# ── CSV Exports ────────────────────────────────────────────────────────────────

@reports_bp.route('/export/tasks', methods=['GET'])
@login_required
@active_account_required
def export_tasks_csv():
    if not current_user.is_management:
        return api_error('Permission denied to export reports.', 403)

    query = Task.query
    if current_user.role == ROLE_TEAM_LEAD and current_user.team_id:
        query = query.filter(Task.team_id == current_user.team_id)

    tasks = query.order_by(Task.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Title', 'Status', 'Priority', 'Assignee',
        'Due Date', 'Progress (%)', 'Created At', 'Completed At'
    ])

    for t in tasks:
        assignee = t.assignee or t.user
        assignee_name = (assignee.full_name or assignee.username) if assignee else 'Unassigned'
        writer.writerow([
            t.id,
            t.title,
            t.status,
            t.priority,
            assignee_name,
            t.due_date.isoformat() if t.due_date else '',
            t.progress,
            t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
            t.completed_at.strftime('%Y-%m-%d %H:%M') if t.completed_at else ''
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=tasknest_tasks_export.csv'}
    )


@reports_bp.route('/export/attendance', methods=['GET'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD)
def export_attendance_csv():
    query = Attendance.query.join(User)
    if current_user.role == ROLE_TEAM_LEAD and current_user.team_id:
        query = query.filter(User.team_id == current_user.team_id)

    records = query.order_by(Attendance.check_in.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Employee Name', 'Employee ID', 'Email',
        'Check-In', 'Check-Out', 'Duration (Hours)', 'Status', 'Notes'
    ])

    for r in records:
        emp = r.user
        emp_name = (emp.full_name or emp.username) if emp else 'Unknown'
        emp_code = emp.employee_id_code if emp else ''
        email = emp.email if emp else ''
        writer.writerow([
            r.id,
            emp_name,
            emp_code,
            email,
            r.check_in.strftime('%Y-%m-%d %H:%M') if r.check_in else '',
            r.check_out.strftime('%Y-%m-%d %H:%M') if r.check_out else '',
            round(r.duration_minutes / 60.0, 2),
            r.status,
            r.notes or ''
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=tasknest_attendance_export.csv'}
    )
