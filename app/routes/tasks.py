"""
Task Management API routes with Enterprise extensions.
Supports list, Kanban board, team assignment, subtasks, recurrence, and lifecycle workflows.
"""
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_, desc, asc, case
from app import db
from app.models import (
    Task, Category, SubTask, User, Team, TeamMember,
    STATUS_TODO, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_IN_REVIEW,
    STATUS_CHANGES_REQUESTED, STATUS_COMPLETED, STATUS_PENDING,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
)
from app.routes.utils import (
    api_success, api_error, active_account_required,
    log_audit, send_notification
)

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')

VALID_PRIORITIES = {'low', 'medium', 'high', 'urgent'}
VALID_CREATE_STATUSES = {'pending', 'todo', STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_IN_REVIEW, STATUS_COMPLETED}
VALID_UPDATE_STATUSES = {
    STATUS_TODO, STATUS_IN_PROGRESS, STATUS_BLOCKED,
    STATUS_IN_REVIEW, STATUS_CHANGES_REQUESTED, STATUS_COMPLETED,
}
VALID_STATUSES = VALID_UPDATE_STATUSES


def utc_now():
    return datetime.now(timezone.utc)


def parse_date(date_str):
    if not date_str:
        return None
    try:
        if isinstance(date_str, date):
            return date_str
        clean_str = date_str.split('T')[0].strip()
        return datetime.strptime(clean_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def can_manage_task(task, user):
    """Check if user has permission to modify/assign/delete task."""
    if user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return True
    if task.user_id == user.id or task.creator_id == user.id:
        return True
    if user.is_team_lead and (task.team_id == user.team_id or task.creator_id == user.id):
        return True
    return False


def can_view_task(task, user):
    """Check if user has permission to view task."""
    if user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return True
    if task.user_id == user.id or task.creator_id == user.id or task.assignee_id == user.id:
        return True
    if user.is_team_lead and (task.team_id == user.team_id or task.creator_id == user.id):
        return True
    return False


# ── Task List & Filter ─────────────────────────────────────────────────────────

@tasks_bp.route('', methods=['GET'])
@login_required
@active_account_required
def get_tasks():
    # Scoping:
    # If admin: see all org tasks, or filter by user
    # If lead: see team tasks, assigned tasks, or created tasks
    # If employee: see tasks assigned to them or created by them
    if current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        query = Task.query
    elif current_user.is_team_lead:
        led_team_ids = [team.id for team in Team.query.filter_by(lead_id=current_user.id).all()]
        team_scope = [Task.team_id.in_(led_team_ids)] if led_team_ids else []
        query = Task.query.filter(or_(
            Task.user_id == current_user.id,
            Task.assignee_id == current_user.id,
            Task.creator_id == current_user.id,
            *team_scope
        ))
    else:
        query = Task.query.filter(
            or_(
                Task.user_id == current_user.id,
                Task.assignee_id == current_user.id,
                Task.creator_id == current_user.id
            )
        )

    # Search query
    q = (request.args.get('q') or '').strip()
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Task.title.ilike(search_pattern),
                Task.description.ilike(search_pattern)
            )
        )

    # Filter by status (normalizes 'pending' and 'todo')
    status = (request.args.get('status') or '').strip().lower()
    if status in VALID_STATUSES:
        if status == 'todo':
            query = query.filter(Task.status.in_(['todo', 'pending']))
        else:
            query = query.filter(Task.status == status)

    # Filter by priority
    priority = (request.args.get('priority') or '').strip().lower()
    if priority in VALID_PRIORITIES:
        query = query.filter(Task.priority == priority)

    # Filter by category
    category_id = request.args.get('category_id')
    if category_id:
        try:
            cat_id = int(category_id)
            query = query.filter(Task.category_id == cat_id)
        except ValueError:
            pass

    # Filter by team
    team_id = request.args.get('team_id')
    if team_id:
        try:
            t_id = int(team_id)
            query = query.filter(Task.team_id == t_id)
        except ValueError:
            pass

    # Filter by assignee
    assignee_id = request.args.get('assignee_id')
    if assignee_id:
        try:
            a_id = int(assignee_id)
            query = query.filter(or_(Task.assignee_id == a_id, Task.user_id == a_id))
        except ValueError:
            pass

    # Filter by date ranges
    due_before = parse_date(request.args.get('due_before'))
    if due_before:
        query = query.filter(Task.due_date <= due_before)

    due_after = parse_date(request.args.get('due_after'))
    if due_after:
        query = query.filter(Task.due_date >= due_after)

    # Sorting with strict allowlist
    sort = (request.args.get('sort') or 'created_at_desc').strip().lower()
    if sort == 'due_date_asc':
        query = query.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.id.desc())
    elif sort == 'due_date_desc':
        query = query.order_by(Task.due_date.is_(None), Task.due_date.desc(), Task.id.desc())
    elif sort == 'created_at_asc':
        query = query.order_by(Task.created_at.asc())
    elif sort == 'priority_desc':
        priority_weight = case(
            (Task.priority == 'urgent', 4),
            (Task.priority == 'high', 3),
            (Task.priority == 'medium', 2),
            (Task.priority == 'low', 1),
            else_=0
        )
        query = query.order_by(priority_weight.desc(), Task.created_at.desc())
    elif sort == 'priority_asc':
        priority_weight = case(
            (Task.priority == 'urgent', 4),
            (Task.priority == 'high', 3),
            (Task.priority == 'medium', 2),
            (Task.priority == 'low', 1),
            else_=0
        )
        query = query.order_by(priority_weight.asc(), Task.created_at.desc())
    elif sort == 'title_asc':
        query = query.order_by(Task.title.asc())
    else:  # default created_at_desc
        query = query.order_by(Task.created_at.desc())

    tasks = query.all()
    return api_success([t.to_dict() for t in tasks])


# ── Create Task ────────────────────────────────────────────────────────────────

@tasks_bp.route('', methods=['POST'])
@login_required
@active_account_required
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return api_error('Title is required.', 400)

    priority = (data.get('priority') or 'medium').strip().lower()
    if priority not in VALID_PRIORITIES:
        return api_error(f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}", 400)

    status = (data.get('status') or 'pending').strip().lower()
    if status not in VALID_CREATE_STATUSES:
        return api_error(f"Status must be one of: {', '.join(sorted(VALID_CREATE_STATUSES))}", 400)

    category_id = data.get('category_id')
    if category_id:
        try:
            category_id = int(category_id)
            cat = Category.query.filter_by(id=category_id).first()
            if not cat:
                return api_error('Category not found or does not belong to you.', 404)
        except (ValueError, TypeError):
            category_id = None
    else:
        category_id = None

    due_date = parse_date(data.get('due_date'))
    start_date = parse_date(data.get('start_date'))
    completed_at = utc_now() if status == 'completed' else None

    # Team leads can assign only to active members of teams they lead.
    assignee_id = data.get('assignee_id')
    led_teams = Team.query.filter_by(lead_id=current_user.id).all() if current_user.is_team_lead else []
    led_team_ids = {team.id for team in led_teams}
    if current_user.is_team_lead and not led_team_ids:
        return api_error('Your account is not assigned as the lead of a team yet. Ask an administrator to assign your team first.', 403)

    if assignee_id:
        try:
            assignee_id = int(assignee_id)
        except (ValueError, TypeError):
            return api_error('Select a valid assignee.', 400)
        assignee_user = User.query.filter_by(id=assignee_id, account_active=True).first()
        if not assignee_user:
            return api_error('The selected assignee is not an active account.', 400)
    else:
        assignee_id = current_user.id

    team_id = data.get('team_id')
    if team_id:
        try:
            team_id = int(team_id)
        except (ValueError, TypeError):
            return api_error('Select a valid team.', 400)
    elif current_user.is_team_lead:
        # If the lead manages multiple teams, infer from the selected member's membership.
        memberships = TeamMember.query.filter(TeamMember.user_id == assignee_id, TeamMember.team_id.in_(led_team_ids)).all()
        team_id = memberships[0].team_id if memberships else next(iter(led_team_ids))
    elif current_user.team_id:
        team_id = current_user.team_id
    else:
        team_id = None

    if current_user.is_team_lead:
        if team_id not in led_team_ids:
            return api_error('You can only assign tasks within a team you lead.', 403)
        is_member = (TeamMember.query.filter_by(team_id=team_id, user_id=assignee_id).first()
                     or Team.query.filter_by(id=team_id, lead_id=assignee_id).first()
                     or User.query.filter_by(id=assignee_id, team_id=team_id).first())
        if not is_member:
            return api_error('The selected employee is not a member of your team.', 403)
    elif not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN) and assignee_id != current_user.id:
        return api_error('Only administrators and team leads can assign tasks to other employees.', 403)

    acceptance_criteria = (data.get('acceptance_criteria') or '').strip()
    progress = min(100, max(0, int(data.get('progress') or 0)))
    if status == 'completed':
        progress = 100

    is_recurring = bool(data.get('is_recurring', False))
    recurrence_interval = data.get('recurrence_interval') if is_recurring else None

    task = Task(
        title=title,
        description=(data.get('description') or '').strip(),
        priority=priority,
        status=status,
        due_date=due_date,
        start_date=start_date,
        completed_at=completed_at,
        category_id=category_id,
        user_id=assignee_id,       # legacy backward compatibility
        assignee_id=assignee_id,
        creator_id=current_user.id,
        team_id=team_id,
        organization_id=current_user.organization_id or 1,
        acceptance_criteria=acceptance_criteria,
        progress=progress,
        is_recurring=is_recurring,
        recurrence_interval=recurrence_interval
    )

    db.session.add(task)
    db.session.flush()

    # Create initial subtasks if supplied
    subtask_titles = data.get('subtasks') or []
    if isinstance(subtask_titles, list):
        for st_title in subtask_titles:
            st_text = str(st_title).strip()
            if st_text:
                db.session.add(SubTask(task_id=task.id, title=st_text))

    db.session.commit()

    # Notify assignee if assigned to someone else
    if assignee_id and assignee_id != current_user.id:
        send_notification(
            assignee_id,
            f'New Task Assigned: "{task.title}"',
            f"{current_user.full_name or current_user.username} assigned you to '{task.title}' (Priority: {task.priority.upper()}).",
            f"/tasks?task_id={task.id}",
            'task_assigned'
        )

    log_audit('task_created', 'Task', task.id, f'Created task {task.title} (assigned to {assignee_id})')
    return api_success(task.to_dict(), message='Task created successfully', status_code=201)


# ── Single Task Details ────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>', methods=['GET'])
@login_required
@active_account_required
def get_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return api_error('Task not found.', 404)

    if not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    task_dict = task.to_dict()
    task_dict['subtasks'] = [st.to_dict() for st in task.subtasks.all()]
    return api_success(task_dict)


# ── Update Task ────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>', methods=['PUT'])
@login_required
@active_account_required
def update_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return api_error('Task not found.', 404)

    if not can_manage_task(task, current_user) and task.assignee_id != current_user.id:
        return api_error('Task not found.', 404)

    data = request.get_json(silent=True) or {}

    if 'title' in data:
        title = (data.get('title') or '').strip()
        if not title:
            return api_error('Title cannot be empty.', 400)
        task.title = title

    if 'description' in data:
        task.description = (data.get('description') or '').strip()

    if 'priority' in data:
        priority = (data.get('priority') or '').strip().lower()
        if priority not in VALID_PRIORITIES:
            return api_error(f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}", 400)
        task.priority = priority

    if 'status' in data:
        status = (data.get('status') or '').strip().lower()
        if status not in VALID_UPDATE_STATUSES:
            return api_error(f"Status must be one of: {', '.join(sorted(VALID_UPDATE_STATUSES))}", 400)
        if status == 'completed' and task.status != 'completed':
            task.completed_at = utc_now()
            task.progress = 100
        elif status != 'completed':
            task.completed_at = None
        task.status = status

    if 'progress' in data:
        try:
            task.progress = min(100, max(0, int(data['progress'])))
            if task.progress == 100 and task.status != 'completed':
                task.status = 'completed'
                task.completed_at = utc_now()
        except (ValueError, TypeError):
            pass

    if 'due_date' in data:
        raw_due = data.get('due_date')
        task.due_date = parse_date(raw_due) if raw_due else None

    if 'start_date' in data:
        raw_start = data.get('start_date')
        task.start_date = parse_date(raw_start) if raw_start else None

    if 'acceptance_criteria' in data:
        task.acceptance_criteria = (data.get('acceptance_criteria') or '').strip()

    if 'category_id' in data:
        cat_id = data.get('category_id')
        if cat_id:
            try:
                cat_id = int(cat_id)
                cat = Category.query.filter_by(id=cat_id).first()
                if not cat:
                    return api_error('Category not found.', 404)
                task.category_id = cat_id
            except (ValueError, TypeError):
                task.category_id = None
        else:
            task.category_id = None

    # Reassignment (Authorized to Creator, Lead, Admin)
    if 'assignee_id' in data and can_manage_task(task, current_user):
        new_assignee_id = data.get('assignee_id')
        if new_assignee_id:
            try:
                new_uid = int(new_assignee_id)
                assignee_user = User.query.get(new_uid)
                if assignee_user and assignee_user.account_active:
                    old_assignee_id = task.assignee_id
                    task.assignee_id = new_uid
                    task.user_id = new_uid
                    if new_uid != current_user.id and new_uid != old_assignee_id:
                        send_notification(
                            new_uid,
                            f'Task Reassigned: "{task.title}"',
                            f"You have been assigned to task '{task.title}' by {current_user.full_name or current_user.username}.",
                            f"/tasks?task_id={task.id}",
                            'task_assigned'
                        )
            except (ValueError, TypeError):
                pass

    if 'team_id' in data and can_manage_task(task, current_user):
        try:
            task.team_id = int(data['team_id']) if data['team_id'] else None
        except (ValueError, TypeError):
            pass

    task.updated_at = utc_now()
    db.session.commit()

    log_audit('task_updated', 'Task', task.id, f'Updated task {task.title}')
    return api_success(task.to_dict(), message='Task updated successfully')


# ── Delete Task ────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@login_required
@active_account_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return api_error('Task not found.', 404)

    if not can_manage_task(task, current_user):
        return api_error('Task not found.', 404)

    db.session.delete(task)
    db.session.commit()
    log_audit('task_deleted', 'Task', task_id, f'Deleted task ID {task_id}')
    return api_success(message='Task deleted successfully')


# ── Complete Toggle ────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/complete', methods=['PATCH'])
@login_required
@active_account_required
def toggle_task_complete(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return api_error('Task not found.', 404)

    if not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    data = request.get_json(silent=True) or {}
    explicit_status = data.get('status')

    if explicit_status:
        if explicit_status not in VALID_STATUSES:
            return api_error('Invalid status', 400)
        task.status = explicit_status
        if explicit_status == 'completed':
            task.completed_at = utc_now()
            task.progress = 100
        else:
            task.completed_at = None
    else:
        if task.status == 'completed':
            task.status = 'pending'
            task.completed_at = None
        else:
            task.status = 'completed'
            task.completed_at = utc_now()
            task.progress = 100

    task.updated_at = utc_now()
    db.session.commit()
    return api_success(task.to_dict(), message='Task status updated')


# ── Subtasks ───────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/subtasks', methods=['GET', 'POST'])
@login_required
@active_account_required
def task_subtasks(task_id):
    task = Task.query.get_or_404(task_id)
    if not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    if request.method == 'GET':
        return api_success([st.to_dict() for st in task.subtasks.all()])

    # POST subtask
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return api_error('Subtask title is required.', 400)

    st = SubTask(task_id=task.id, title=title, is_completed=False)
    db.session.add(st)
    db.session.commit()
    return api_success(st.to_dict(), message='Subtask created.', status_code=201)


@tasks_bp.route('/subtasks/<int:subtask_id>', methods=['PATCH', 'DELETE'])
@login_required
@active_account_required
def manage_subtask(subtask_id):
    st = SubTask.query.get_or_404(subtask_id)
    task = Task.query.get_or_404(st.task_id)
    if not can_view_task(task, current_user):
        return api_error('Unauthorized to edit this subtask.', 403)

    if request.method == 'DELETE':
        db.session.delete(st)
        db.session.commit()
        return api_success(message='Subtask deleted.')

    # PATCH
    data = request.get_json(silent=True) or {}
    if 'is_completed' in data:
        st.is_completed = bool(data['is_completed'])
    if 'title' in data and data['title'].strip():
        st.title = data['title'].strip()

    db.session.commit()
    return api_success(st.to_dict(), message='Subtask updated.')


# ── Recurring Tasks Processor ──────────────────────────────────────────────────

@tasks_bp.route('/process-recurring', methods=['POST'])
@login_required
@active_account_required
def process_recurring_tasks():
    """Trigger recurrence generation for completed recurring tasks."""
    today = date.today()
    recurring_tasks = Task.query.filter(
        Task.is_recurring == True,
        Task.status == 'completed'
    ).all()

    created_count = 0
    for t in recurring_tasks:
        # Calculate next due date
        interval = t.recurrence_interval or 'weekly'
        next_due = None
        if t.due_date:
            if interval == 'daily':
                next_due = t.due_date + timedelta(days=1)
            elif interval == 'monthly':
                next_due = t.due_date + timedelta(days=30)
            else:  # weekly
                next_due = t.due_date + timedelta(days=7)

        # Create next occurrence
        next_task = Task(
            title=f"{t.title}",
            description=t.description,
            priority=t.priority,
            status='todo',
            due_date=next_due,
            start_date=today,
            category_id=t.category_id,
            user_id=t.user_id,
            assignee_id=t.assignee_id,
            creator_id=t.creator_id,
            team_id=t.team_id,
            organization_id=t.organization_id,
            is_recurring=True,
            recurrence_interval=t.recurrence_interval
        )
        # Turn off recurrence on old completed task so it doesn't duplicate
        t.is_recurring = False
        db.session.add(next_task)
        created_count += 1

    db.session.commit()
    return api_success({'spawned_count': created_count}, message=f'Spawned {created_count} recurring tasks.')
