"""
Productivity Analytics and CSV Export API routes.
"""
import io
import csv
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, request, Response
from flask_login import current_user, login_required
from sqlalchemy import func
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
    """
    Real productivity analytics calculated from actual database records.
    """
    days = 14
    try:
        if request.args.get('days'):
            days = min(90, max(7, int(request.args.get('days'))))
    except ValueError:
        pass

    start_date = date.today() - timedelta(days=days)

    # Scoping: if admin, organization-wide; if lead, team tasks; if employee, self tasks
    task_query = Task.query
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        if current_user.is_team_lead and current_user.team_id:
            task_query = task_query.filter(
                (Task.team_id == current_user.team_id) | (Task.assignee_id == current_user.id)
            )
        else:
            task_query = task_query.filter(
                (Task.assignee_id == current_user.id) | (Task.user_id == current_user.id)
            )

    tasks_in_period = task_query.filter(Task.created_at >= datetime.combine(start_date, datetime.min.time())).all()

    total_tasks = len(tasks_in_period)
    completed_tasks = [t for t in tasks_in_period if t.status == 'completed']
    completed_count = len(completed_tasks)
    overdue_count = len([t for t in tasks_in_period if t.is_overdue])

    # Calculate real on-time rate
    on_time_count = 0
    for t in completed_tasks:
        if t.due_date and t.completed_at:
            if t.completed_at.date() <= t.due_date:
                on_time_count += 1
        elif not t.due_date:
            on_time_count += 1

    on_time_rate = round((on_time_count / completed_count) * 100, 1) if completed_count > 0 else 0.0

    # Trend by date: count completed per day
    daily_trends = {}
    for i in range(days + 1):
        day_str = (start_date + timedelta(days=i)).isoformat()
        daily_trends[day_str] = 0

    for t in completed_tasks:
        if t.completed_at:
            d_str = t.completed_at.date().isoformat()
            if d_str in daily_trends:
                daily_trends[d_str] += 1

    # Team workload distribution (for management)
    workload = []
    if current_user.is_management:
        assignee_counts = (
            db.session.query(Task.assignee_id, func.count(Task.id))
            .filter(Task.status != 'completed')
            .group_by(Task.assignee_id)
            .all()
        )
        for uid, cnt in assignee_counts:
            if uid:
                u = User.query.get(uid)
                if u:
                    workload.append({
                        'user_id': u.id,
                        'name': u.full_name or u.username,
                        'active_tasks': cnt
                    })

    return api_success({
        'total_tasks': total_tasks,
        'completed_count': completed_count,
        'overdue_count': overdue_count,
        'on_time_rate': on_time_rate,
        'completion_trends': [{'date': d, 'completed': c} for d, c in daily_trends.items()],
        'workload_distribution': workload,
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
