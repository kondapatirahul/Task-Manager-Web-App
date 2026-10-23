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
    """Return report data in the contract consumed by templates/reports.html."""
    try:
        days = int(request.args.get('range_days', request.args.get('days', 30)))
    except (TypeError, ValueError):
        days = 30
    days = min(90, max(7, days))
    start_date = date.today() - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, datetime.min.time())

    query = Task.query
    if current_user.role == ROLE_TEAM_LEAD:
        if current_user.team_id:
            query = query.filter((Task.team_id == current_user.team_id) | (Task.assignee_id == current_user.id) | (Task.user_id == current_user.id))
        else:
            query = query.filter((Task.assignee_id == current_user.id) | (Task.user_id == current_user.id))
    elif current_user.role not in (ROLE_SUPER_ADMIN, ROLE_ADMIN, 'admin_hr'):
        query = query.filter((Task.assignee_id == current_user.id) | (Task.user_id == current_user.id))

    tasks = query.all()
    in_range = [t for t in tasks if t.created_at and t.created_at >= start_dt]
    completed = [t for t in in_range if t.status == 'completed']
    overdue = [t for t in in_range if t.is_overdue]
    blocked = [t for t in in_range if t.status == 'blocked']
    on_time = sum(1 for t in completed if not t.due_date or (t.completed_at and t.completed_at.date() <= t.due_date))
    on_time_rate = round(on_time * 100 / len(completed), 1) if completed else 0.0

    trend = { (start_date + timedelta(days=i)).isoformat(): 0 for i in range(days) }
    for task in completed:
        if task.completed_at:
            key = task.completed_at.date().isoformat()
            if key in trend:
                trend[key] += 1

    status_distribution = {}
    priority_distribution = {}
    for task in in_range:
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
            completed_count = sum(1 for t in assigned if t in completed)
            if assigned:
                workload_distribution.append({
                    'user_id': user.id,
                    'name': user.full_name or user.username,
                    'active_tasks': active_count,
                    'completed_tasks': completed_count,
                })

    total_tasks = task_query.count()
    return api_success({
        'metrics': {
            'total_tasks': len(in_range),
            'completed_tasks': len(completed),
            'overdue_incomplete_tasks': len(overdue),
            'blocked_tasks': len(blocked),
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
