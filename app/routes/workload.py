from flask import Blueprint, request
from flask_login import current_user, login_required

from app import db
from app.routes.utils import active_account_required, api_error, api_success
from app.services.workload import (
    assignment_recommendations,
    eligible_assignment_employee_ids,
    employee_tasks,
    permitted_team_employee_ids,
    team_workload,
    authorized_task_query,
    workload_state_counts,
    workload_summary,
)
from app.services.notifications import notify_task_collaboration_event
from app.services.handovers import pending_handover
from app.models import Task, Team, User

workload_bp = Blueprint('workload', __name__, url_prefix='/api/workload')


@workload_bp.get('/me')
@active_account_required
@login_required
def my_workload():
    return api_success(workload_summary(current_user, employee_tasks(current_user.id)))


@workload_bp.get('/team')
@active_account_required
@login_required
def team_workload_overview():
    if current_user.role not in ('team_lead', 'admin', 'super_admin'):
        return api_error('Only team leaders and administrators can view team workload.', 403)
    try:
        employee_id = int(request.args['employee_id']) if request.args.get('employee_id') else None
    except ValueError:
        return api_error('Invalid employee_id.', 400)
    status = (request.args.get('status') or '').strip()
    allowed_statuses = {'pending', 'todo', 'in_progress', 'blocked', 'in_review', 'changes_requested', 'completed'}
    if status and status not in allowed_statuses:
        return api_error('Invalid status filter.', 400)
    priority = (request.args.get('priority') or '').strip()
    if priority and priority not in {'low', 'medium', 'high'}:
        return api_error('Invalid priority filter.', 400)
    result = team_workload(current_user, employee_id, {
        'status': status,
        'priority': priority,
        'overdue': request.args.get('overdue'),
    })
    if result is None:
        return api_error('Employee is outside your authorized scope.', 403)
    return api_success({
        'employees': result,
        'employee_count': len(result),
        'capacity_summary': workload_state_counts(result),
        'authorized_employee_ids': permitted_team_employee_ids(current_user),
    })


@workload_bp.get('/employees/<int:employee_id>')
@active_account_required
@login_required
def employee_workload(employee_id):
    if current_user.role == 'employee':
        authorized = employee_id == current_user.id
    elif current_user.role in ('team_lead', 'admin', 'super_admin'):
        authorized = employee_id in permitted_team_employee_ids(current_user)
    else:
        authorized = False
    if not authorized:
        return api_error('Employee is outside your authorized scope.', 403)
    employee = db.session.get(User, employee_id)
    if not employee:
        return api_error('Employee not found.', 404)
    return api_success(workload_summary(employee, employee_tasks(employee.id)))


def _manager_can_assign_task(task):
    if current_user.role not in ('admin', 'super_admin', 'team_lead'):
        return False
    if not task:
        return False
    if current_user.role == 'team_lead':
        from app.routes.tasks import can_user_manage_task
        return can_user_manage_task(current_user, task)
    if current_user.role == 'admin':
        return authorized_task_query(current_user).filter(Task.id == task.id).first() is not None
    return True


@workload_bp.post('/recommendations')
@active_account_required
@login_required
def recommend_assignment():
    if current_user.role not in ('admin', 'super_admin', 'team_lead'):
        return api_error('Only managers can request assignment recommendations.', 403)
    data = request.get_json(silent=True) or {}
    task = None
    if data.get('task_id') is not None:
        try:
            task = db.session.get(Task, int(data['task_id']))
        except (TypeError, ValueError):
            return api_error('Invalid task_id.', 400)
        if not _manager_can_assign_task(task):
            return api_error('Task is outside your authorized scope.', 404)
    try:
        team_id = int(data['team_id']) if data.get('team_id') is not None else None
    except (TypeError, ValueError):
        return api_error('Invalid team_id.', 400)
    if team_id is not None and current_user.organization_id is not None:
        team = db.session.get(Team, team_id)
        if not team or team.organization_id != current_user.organization_id:
            return api_error('Team is outside your authorized scope.', 404)
    raw_effort = data.get('estimated_effort_hours')
    if raw_effort in (None, ''):
        proposed_effort = task.estimated_effort_hours if task else 0.0
    else:
        try:
            proposed_effort = float(raw_effort)
        except (TypeError, ValueError):
            return api_error('Estimated effort must be a non-negative number.', 400)
    if proposed_effort < 0 or proposed_effort > 10000:
        return api_error('Estimated effort must be between 0 and 10000 hours.', 400)
    recommendations = assignment_recommendations(
        current_user, task=task, team_id=team_id,
        proposed_effort=proposed_effort,
    )
    return api_success({
        'recommendations': recommendations,
        'proposed_effort_hours': proposed_effort,
        'capacity_default_hours': 40.0,
        'missing_estimate_default_hours': 0.0,
        'assignment_saved': False,
    })


@workload_bp.post('/recommendations/<int:task_id>/accept')
@active_account_required
@login_required
def accept_assignment_recommendation(task_id):
    task = db.session.get(Task, task_id)
    if not _manager_can_assign_task(task):
        return api_error('Task is outside your authorized scope.', 404)
    if pending_handover(task_id):
        return api_error(
            'Resolve the pending handover before changing this assignment.',
            409,
        )
    data = request.get_json(silent=True) or {}
    try:
        employee_id = int(data.get('employee_id'))
    except (TypeError, ValueError):
        return api_error('A valid employee_id is required.', 400)
    if employee_id not in eligible_assignment_employee_ids(current_user, task.team_id):
        return api_error('Employee is outside your authorized scope.', 403)
    # Recalculate immediately before persistence; recommendations are advisory.
    recommendations = assignment_recommendations(current_user, task=task)
    selected = next(
        (item for item in recommendations if item['employee_id'] == employee_id),
        None,
    )
    if selected is None:
        return api_error('Employee is no longer eligible for this assignment.', 409)
    task.assigned_to_id = employee_id
    db.session.commit()
    notify_task_collaboration_event(
        'task_reassigned',
        task,
        current_user,
        recipients=[employee_id],
        metadata={
            'description': f'Assignment changed for "{task.title}".',
            'event_id': f'assignment:{task.id}:{task.updated_at.isoformat()}',
        },
    )
    return api_success({
        'assignment_saved': True,
        'task_id': task.id,
        'assigned_to_id': employee_id,
        'planned_workload': selected,
    }, message='Assignment accepted and saved.')
