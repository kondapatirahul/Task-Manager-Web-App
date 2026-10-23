from flask import Blueprint, request
from flask_login import current_user, login_required

from app import db
from app.models import ProjectDecision, Task, Team
from app.routes.utils import active_account_required, api_error, api_success
from app.services.decisions import (
    DECISION_STATUSES,
    can_manage_decision,
    can_view_team,
    create_history,
    serialize_decision,
)
from app.services.notifications import notify_task_collaboration_event
from app.routes.tasks import can_user_view_task

decisions_bp = Blueprint('decisions', __name__, url_prefix='/api/decisions')

MAX_TITLE = 200
MAX_DETAILS = 10000
MAX_RATIONALE = 10000
MAX_ALTERNATIVES = 5000


def _text(data, key, maximum, required=True):
    value = (data.get(key) or '').strip()
    if required and not value:
        return None, f'{key.replace("_", " ").capitalize()} is required.'
    if len(value) > maximum:
        return None, f'{key.replace("_", " ").capitalize()} cannot exceed {maximum} characters.'
    return value, None


def _decision_or_404(decision_id):
    decision = db.session.get(ProjectDecision, decision_id)
    if not decision or not can_view_team(current_user, decision.team):
        return None
    return decision


@decisions_bp.get('')
@active_account_required
@login_required
def list_decisions():
    query = ProjectDecision.query.join(Team)
    if current_user.role == 'super_admin':
        pass
    elif current_user.role in ('admin', 'hr'):
        if current_user.organization_id is not None:
            query = query.filter(Team.organization_id == current_user.organization_id)
    else:
        visible_team_ids = [
            team.id for team in Team.query.all()
            if can_view_team(current_user, team)
        ]
        query = query.filter(ProjectDecision.team_id.in_(visible_team_ids or [-1]))

    search = (request.args.get('q') or '').strip()
    if len(search) > 200:
        return api_error('Search text is too long.', 400)
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            ProjectDecision.title.ilike(pattern)
            | ProjectDecision.details.ilike(pattern)
            | ProjectDecision.rationale.ilike(pattern)
        )
    status = (request.args.get('status') or '').strip().lower()
    if status and status not in DECISION_STATUSES:
        return api_error('Invalid decision status.', 400)
    if status:
        query = query.filter(ProjectDecision.status == status)
    if request.args.get('task_id'):
        try:
            task_id = int(request.args['task_id'])
        except (TypeError, ValueError):
            return api_error('Invalid task filter.', 400)
        task = db.session.get(Task, task_id)
        if not task or not can_user_view_task(current_user, task):
            return api_error('Task not found.', 404)
        query = query.filter(ProjectDecision.linked_tasks.any(Task.id == task_id))
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    except (TypeError, ValueError):
        return api_error('Invalid pagination values.', 400)
    pagination = query.order_by(
        ProjectDecision.updated_at.desc(),
        ProjectDecision.id.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)
    return api_success({
        'items': [serialize_decision(current_user, item) for item in pagination.items],
        'page': pagination.page,
        'pages': pagination.pages,
        'has_more': pagination.has_next,
    })


@decisions_bp.post('')
@active_account_required
@login_required
def create_decision():
    data = request.get_json(silent=True) or {}
    try:
        team_id = int(data.get('team_id'))
    except (TypeError, ValueError):
        return api_error('A valid team_id is required.', 400)
    team = db.session.get(Team, team_id)
    if not can_view_team(current_user, team):
        return api_error('Project is outside your authorized scope.', 404)
    if current_user.role == 'employee':
        return api_error('Employees cannot create project decisions.', 403)
    title, error = _text(data, 'title', MAX_TITLE)
    if error:
        return api_error(error, 400)
    details, error = _text(data, 'details', MAX_DETAILS)
    if error:
        return api_error(error, 400)
    rationale, error = _text(data, 'rationale', MAX_RATIONALE)
    if error:
        return api_error(error, 400)
    alternatives, error = _text(data, 'alternatives', MAX_ALTERNATIVES, required=False)
    if error:
        return api_error(error, 400)
    status = (data.get('status') or 'proposed').strip().lower()
    if status not in DECISION_STATUSES:
        return api_error('Invalid decision status.', 400)
    task_ids = data.get('task_ids') or []
    if not isinstance(task_ids, list) or len(task_ids) > 50:
        return api_error('task_ids must be a list of at most 50 tasks.', 400)
    try:
        task_ids = {int(task_id) for task_id in task_ids}
    except (TypeError, ValueError):
        return api_error('Every linked task ID must be valid.', 400)
    tasks = Task.query.filter(Task.id.in_(task_ids)).all() if task_ids else []
    if len(tasks) != len(task_ids) or any(
        task.team_id != team.id or not can_user_view_task(current_user, task)
        for task in tasks
    ):
        return api_error('All linked tasks must belong to this project and be visible to you.', 403)
    decision = ProjectDecision(
        team_id=team.id,
        author_id=current_user.id,
        title=title,
        details=details,
        rationale=rationale,
        alternatives=alternatives or None,
        status=status,
    )
    decision.linked_tasks.extend(tasks)
    db.session.add(decision)
    db.session.flush()
    create_history(decision, current_user, change_note='Decision created.')
    db.session.commit()
    return api_success(serialize_decision(current_user, decision), message='Decision created.', status_code=201)


@decisions_bp.get('/<int:decision_id>')
@active_account_required
@login_required
def get_decision(decision_id):
    decision = _decision_or_404(decision_id)
    if not decision:
        return api_error('Decision not found.', 404)
    return api_success(serialize_decision(current_user, decision))


@decisions_bp.put('/<int:decision_id>')
@active_account_required
@login_required
def update_decision(decision_id):
    decision = _decision_or_404(decision_id)
    if not decision:
        return api_error('Decision not found.', 404)
    if not can_manage_decision(current_user, decision):
        return api_error('You do not have permission to update this decision.', 403)
    data = request.get_json(silent=True) or {}
    title, error = _text(data, 'title', MAX_TITLE)
    if error:
        return api_error(error, 400)
    details, error = _text(data, 'details', MAX_DETAILS)
    if error:
        return api_error(error, 400)
    rationale, error = _text(data, 'rationale', MAX_RATIONALE)
    if error:
        return api_error(error, 400)
    alternatives, error = _text(data, 'alternatives', MAX_ALTERNATIVES, required=False)
    if error:
        return api_error(error, 400)
    status = (data.get('status') or '').strip().lower()
    if status not in DECISION_STATUSES:
        return api_error('A valid decision status is required.', 400)
    note, error = _text(data, 'change_note', 2000)
    if error:
        return api_error(error, 400)
    task_ids = data.get('task_ids')
    if task_ids is not None:
        if not isinstance(task_ids, list) or len(task_ids) > 50:
            return api_error('task_ids must be a list of at most 50 tasks.', 400)
        try:
            task_ids = {int(task_id) for task_id in task_ids}
        except (TypeError, ValueError):
            return api_error('Every linked task ID must be valid.', 400)
        tasks = Task.query.filter(Task.id.in_(task_ids)).all() if task_ids else []
        if len(tasks) != len(task_ids) or any(
            task.team_id != decision.team_id or not can_user_view_task(current_user, task)
            for task in tasks
        ):
            return api_error('All linked tasks must belong to this project and be visible to you.', 403)
    else:
        tasks = None
    old_status = decision.status
    decision.title = title
    decision.details = details
    decision.rationale = rationale
    decision.alternatives = alternatives or None
    decision.status = status
    if tasks is not None:
        decision.linked_tasks = tasks
    create_history(decision, current_user, old_status=old_status, change_note=note)
    db.session.commit()
    return api_success(serialize_decision(current_user, decision), message='Decision updated.')
