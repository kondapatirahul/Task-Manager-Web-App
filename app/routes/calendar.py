"""Authorized calendar views over task due dates."""

from datetime import date, timedelta

from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.models import Task
from app.routes.tasks import normalize_status, VALID_PRIORITIES
from app.routes.utils import active_account_required, api_error, api_success
from app.services.workload import authorized_task_query, permitted_team_employee_ids

calendar_bp = Blueprint('calendar', __name__, url_prefix='/api/calendar')

VALID_CALENDAR_STATUSES = {
    'todo', 'pending', 'in_progress', 'blocked', 'in_review',
    'changes_requested', 'completed',
}


def _parse_calendar_date(value, field_name):
    if not value:
        return None, None
    try:
        return date.fromisoformat(value), None
    except (TypeError, ValueError):
        return None, f'{field_name} must be a valid ISO date (YYYY-MM-DD).'


@calendar_bp.get('/tasks')
@active_account_required
@login_required
def calendar_tasks():
    start, error = _parse_calendar_date(request.args.get('start'), 'start')
    if error:
        return api_error(error, 400)
    end, error = _parse_calendar_date(request.args.get('end'), 'end')
    if error:
        return api_error(error, 400)
    if not start or not end:
        return api_error('Both start and end dates are required.', 400)
    if start > end:
        return api_error('start must be on or before end.', 400)
    if end - start > timedelta(days=366):
        return api_error('Calendar date range cannot exceed 366 days.', 400)

    query = authorized_task_query(current_user).filter(
        Task.due_date.isnot(None),
        Task.due_date >= start,
        Task.due_date <= end,
    )

    status = (request.args.get('status') or '').strip().lower()
    if status:
        normalized_status = normalize_status(status)
        if not normalized_status or normalized_status not in VALID_CALENDAR_STATUSES:
            return api_error('Invalid status filter.', 400)
        if normalized_status in ('todo', 'pending'):
            query = query.filter(Task.status.in_(['todo', 'pending']))
        else:
            query = query.filter(Task.status == normalized_status)

    priority = (request.args.get('priority') or '').strip().lower()
    if priority:
        if priority not in VALID_PRIORITIES:
            return api_error('Invalid priority filter.', 400)
        query = query.filter(Task.priority == priority)

    deadline = (request.args.get('deadline') or '').strip().lower()
    if deadline not in ('', 'overdue', 'upcoming'):
        return api_error('Invalid deadline filter.', 400)
    if deadline == 'overdue':
        query = query.filter(Task.status != 'completed', Task.due_date < date.today())
    elif deadline == 'upcoming':
        query = query.filter(Task.status != 'completed', Task.due_date >= date.today())

    search = (request.args.get('q') or '').strip()
    if search:
        query = query.filter(Task.title.ilike(f'%{search}%'))

    employee_id = request.args.get('employee_id')
    if employee_id:
        try:
            employee_id = int(employee_id)
        except ValueError:
            return api_error('Invalid employee_id filter.', 400)
        if current_user.role == 'employee' or (
            current_user.role == 'team_lead'
            and employee_id not in permitted_team_employee_ids(current_user)
        ):
            return api_error('Employee is outside your authorized scope.', 403)
        query = query.filter(Task.assigned_to_id == employee_id)

    tasks = query.order_by(Task.due_date.asc(), Task.id.asc()).all()
    return api_success({
        'start': start.isoformat(),
        'end': end.isoformat(),
        'tasks': [
            {
                'id': task.id,
                'title': task.title,
                'due_date': task.due_date.isoformat(),
                'priority': task.priority,
                'status': task.status,
                'status_label': task.status_label,
                'is_overdue': task.is_overdue,
                'task_url': f'/tasks/{task.id}',
                'assigned_to_id': task.assigned_to_id,
                'assigned_to_name': (
                    task.assigned_to.full_name or task.assigned_to.username
                ) if task.assigned_to else None,
            }
            for task in tasks
        ],
    })
