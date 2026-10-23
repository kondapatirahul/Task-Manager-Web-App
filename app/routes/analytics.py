import csv
import io
from datetime import date

from flask import Blueprint, Response, request
from flask_login import current_user, login_required

from app import db
from app.models import Goal, User
from app.routes.utils import active_account_required, api_error, api_success
from app.services.analytics import (
    GOAL_TYPES,
    accessible_tasks,
    employee_analytics,
    goal_to_dict,
    parse_period,
)
from app.services.workload import permitted_team_employee_ids

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api')


def _date_value(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be a valid ISO date (YYYY-MM-DD).')


def _goal_payload(data):
    title = (data.get('title') or '').strip()
    if not title or len(title) > 200:
        raise ValueError('Goal title is required and must be at most 200 characters.')
    goal_type = (data.get('goal_type') or '').strip()
    if goal_type not in GOAL_TYPES:
        raise ValueError('Invalid goal type.')
    try:
        target_value = int(data.get('target_value'))
    except (TypeError, ValueError):
        raise ValueError('Target value must be a positive integer.')
    if target_value <= 0 or target_value > 100000:
        raise ValueError('Target value must be between 1 and 100000.')
    start_date = _date_value(data.get('start_date'), 'start_date')
    target_date = _date_value(data.get('target_date'), 'target_date')
    if target_date < start_date:
        raise ValueError('target_date must be on or after start_date.')
    return {
        'title': title,
        'description': (data.get('description') or '').strip()[:2000],
        'goal_type': goal_type,
        'target_value': target_value,
        'start_date': start_date,
        'target_date': target_date,
    }


@analytics_bp.get('/goals')
@active_account_required
@login_required
def list_goals():
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.target_date.asc()).all()
    tasks = accessible_tasks(current_user).all()
    return api_success([goal_to_dict(goal, current_user, tasks) for goal in goals])


@analytics_bp.get('/goals/<int:goal_id>')
@active_account_required
@login_required
def get_goal(goal_id):
    goal = db.session.get(Goal, goal_id)
    if not goal or goal.user_id != current_user.id:
        return api_error('Goal not found.', 404)
    return api_success(goal_to_dict(goal, current_user, accessible_tasks(current_user).all()))


@analytics_bp.post('/goals')
@active_account_required
@login_required
def create_goal():
    try:
        payload = _goal_payload(request.get_json(silent=True) or {})
    except ValueError as error:
        return api_error(str(error), 400)
    goal = Goal(user_id=current_user.id, **payload)
    db.session.add(goal)
    db.session.commit()
    return api_success(goal_to_dict(goal, current_user), status_code=201)


@analytics_bp.put('/goals/<int:goal_id>')
@active_account_required
@login_required
def update_goal(goal_id):
    goal = db.session.get(Goal, goal_id)
    if not goal or goal.user_id != current_user.id:
        return api_error('Goal not found.', 404)
    try:
        payload = _goal_payload(request.get_json(silent=True) or {})
    except ValueError as error:
        return api_error(str(error), 400)
    for key, value in payload.items():
        setattr(goal, key, value)
    db.session.commit()
    return api_success(goal_to_dict(goal, current_user))


@analytics_bp.delete('/goals/<int:goal_id>')
@active_account_required
@login_required
def delete_goal(goal_id):
    goal = db.session.get(Goal, goal_id)
    if not goal or goal.user_id != current_user.id:
        return api_error('Goal not found.', 404)
    db.session.delete(goal)
    db.session.commit()
    return api_success(message='Goal deleted.')


@analytics_bp.patch('/goals/<int:goal_id>/complete')
@active_account_required
@login_required
def complete_goal(goal_id):
    goal = db.session.get(Goal, goal_id)
    if not goal or goal.user_id != current_user.id:
        return api_error('Goal not found.', 404)
    goal.status = 'completed'
    db.session.commit()
    return api_success(goal_to_dict(goal, current_user))


@analytics_bp.get('/analytics')
@active_account_required
@login_required
def employee_analytics_api():
    try:
        start, end = parse_period(request.args.get('start'), request.args.get('end'))
    except ValueError as error:
        return api_error(str(error), 400)
    return api_success(employee_analytics(current_user, start, end))


@analytics_bp.get('/analytics/team')
@active_account_required
@login_required
def team_analytics_api():
    if current_user.role not in ('team_lead', 'admin', 'super_admin'):
        return api_error('Only team leaders and administrators can view team analytics.', 403)
    try:
        start, end = parse_period(request.args.get('start'), request.args.get('end'))
    except ValueError as error:
        return api_error(str(error), 400)
    authorized_ids = permitted_team_employee_ids(current_user)
    if current_user.role in ('admin', 'super_admin'):
        users = User.query.filter(User.id.in_(authorized_ids), User.account_active.is_(True)).all()
    else:
        users = User.query.filter(User.id.in_(authorized_ids), User.account_active.is_(True)).all()
    summaries = [employee_analytics(user, start, end) for user in users]
    visible_tasks = accessible_tasks(current_user).all()
    completed = sum(1 for task in visible_tasks if task.status == 'completed' and task.completed_at and start <= task.completed_at.date() <= end)
    open_count = sum(1 for task in visible_tasks if task.status != 'completed')
    overdue = sum(1 for task in visible_tasks if task.status != 'completed' and task.due_date and task.due_date < date.today())
    totals = {
        'completed': completed,
        'open': open_count,
        'overdue': overdue,
    }
    return api_success({'start': start.isoformat(), 'end': end.isoformat(), 'totals': totals, 'employees': summaries})


def _csv_safe(value):
    text = '' if value is None else str(value)
    return "'" + text if text.startswith(('=', '+', '-', '@')) else text


@analytics_bp.get('/analytics/export.csv')
@active_account_required
@login_required
def analytics_export():
    if current_user.role not in ('team_lead', 'admin', 'super_admin'):
        return api_error('Only team leaders and administrators can export team analytics.', 403)
    try:
        start, end = parse_period(request.args.get('start'), request.args.get('end'))
    except ValueError as error:
        return api_error(str(error), 400)
    users = User.query.filter(User.id.in_(permitted_team_employee_ids(current_user)), User.account_active.is_(True)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Employee', 'Completed', 'Open', 'Overdue', 'Completion rate'])
    for user in users:
        data = employee_analytics(user, start, end)
        writer.writerow([_csv_safe(user.full_name or user.username), data['completed'], data['open'], data['overdue'], data['completion_rate']])
    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename=tasknest-analytics-{start.isoformat()}-{end.isoformat()}.csv'
    })
