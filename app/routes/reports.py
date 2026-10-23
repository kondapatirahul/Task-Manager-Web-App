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
    """
    Real productivity analytics calculated from actual database records.
    """
    raw_days = request.args.get('range_days', request.args.get('days', '30'))
    try:
        days = min(90, max(7, int(raw_days)))
    except ValueError:
        return api_error('range_days must be a whole number between 7 and 90.', 400)

    today = date.today()
    start_date = today - timedelta(days=days - 1)
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(today + timedelta(days=1), datetime.min.time())

    task_query = Task.query
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        if current_user.is_team_lead:
            led_team_ids = [
                team_id for (team_id,) in
                db.session.query(Team.id).filter_by(lead_id=current_user.id).all()
            ]
            visibility_filters = [
                Task.user_id == current_user.id,
                Task.assignee_id == current_user.id,
                Task.creator_id == current_user.id,
            ]
            if led_team_ids:
                visibility_filters.append(Task.team_id.in_(led_team_ids))
            task_query = task_query.filter(or_(*visibility_filters))
        else:
            task_query = task_query.filter(
                or_(
                    Task.user_id == current_user.id,
                    Task.assignee_id == current_user.id,
                    Task.creator_id == current_user.id,
                )
            )

    completed_tasks = task_query.filter(
        Task.status == 'completed',
        Task.completed_at >= start_datetime,
        Task.completed_at < end_datetime,
    ).with_entities(Task.due_date, Task.completed_at).all()
    on_time_count = sum(
        1 for due_date, completed_at in completed_tasks
        if due_date is None or completed_at.date() <= due_date
    )
    completed_count = len(completed_tasks)
    on_time_rate = round((on_time_count / completed_count) * 100, 1) if completed_count else 0.0

    daily_trends = {
        (start_date + timedelta(days=offset)).isoformat(): 0
        for offset in range(days)
    }
    daily_counts = (
        task_query.filter(
            Task.status == 'completed',
            Task.completed_at >= start_datetime,
            Task.completed_at < end_datetime,
        )
        .with_entities(func.date(Task.completed_at), func.count(Task.id))
        .group_by(func.date(Task.completed_at))
        .all()
    )
    for completed_date, count in daily_counts:
        daily_trends[str(completed_date)] = count

    status_distribution = dict(
        task_query.with_entities(Task.status, func.count(Task.id))
        .group_by(Task.status)
        .order_by(Task.status)
        .all()
    )
    priority_distribution = dict(
        task_query.with_entities(Task.priority, func.count(Task.id))
        .group_by(Task.priority)
        .order_by(Task.priority)
        .all()
    )
    overdue_count = task_query.filter(
        Task.status != 'completed',
        Task.due_date < today,
    ).count()
    blocked_count = task_query.filter(Task.status == 'blocked').count()

    workload = []
    if current_user.is_management:
        effective_assignee_id = func.coalesce(Task.assignee_id, Task.user_id)
        workload_counts = (
            task_query.with_entities(
                effective_assignee_id,
                func.sum(case((Task.status != 'completed', 1), else_=0)),
                func.sum(case((
                    (Task.status == 'completed')
                    & (Task.completed_at >= start_datetime)
                    & (Task.completed_at < end_datetime),
                    1,
                ), else_=0)),
            )
            .group_by(effective_assignee_id)
            .all()
        )
        workload_user_ids = [user_id for user_id, _, _ in workload_counts if user_id]
        users_by_id = {
            user.id: user
            for user in User.query.filter(User.id.in_(workload_user_ids)).all()
        } if workload_user_ids else {}
        for user_id, active_count, completed_count_for_user in workload_counts:
            user = users_by_id.get(user_id)
            if user:
                workload.append({
                    'user_id': user.id,
                    'name': user.full_name or user.username,
                    'active_tasks': int(active_count or 0),
                    'completed_tasks': int(completed_count_for_user or 0),
                })
        workload.sort(key=lambda item: item['name'].casefold())

    total_tasks = task_query.count()
    return api_success({
        'range_days': days,
        'start_date': start_date.isoformat(),
        'end_date': today.isoformat(),
        'total_tasks': total_tasks,
        'completed_count': completed_count,
        'overdue_count': overdue_count,
        'on_time_rate': on_time_rate,
        'metrics': {
            'total_tasks': total_tasks,
            'completed_tasks': completed_count,
            'overdue_incomplete_tasks': overdue_count,
            'blocked_tasks': blocked_count,
            'on_time_rate': on_time_rate,
        },
        'completion_trends': [
            {'date': trend_date, 'completed_count': count, 'completed': count}
            for trend_date, count in daily_trends.items()
        ],
        'status_distribution': status_distribution,
        'priority_distribution': priority_distribution,
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
