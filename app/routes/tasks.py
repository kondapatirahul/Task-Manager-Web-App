from datetime import datetime, date, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_, desc, asc, case
from app import db
from app.models import (
    Task,
    Category,
    User,
    Team,
    team_members,
    TaskStatusHistory,
    STATUS_TODO,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_IN_REVIEW,
    STATUS_COMPLETED,
    STATUS_CHANGES_REQUESTED,
    STATUS_PENDING,
    COMPANY_TASK_STATUSES,
    STATUS_LABELS,
)
from app.routes.utils import api_success, api_error

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')

VALID_PRIORITIES = {'low', 'medium', 'high'}
VALID_STATUSES = {
    STATUS_TODO,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_IN_REVIEW,
    STATUS_COMPLETED,
    STATUS_CHANGES_REQUESTED,
    STATUS_PENDING,
}


def parse_date(date_str):
    if not date_str:
        return None
    try:
        if isinstance(date_str, date):
            return date_str
        clean_str = str(date_str).split('T')[0].strip()
        return datetime.strptime(clean_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def normalize_status(raw_status):
    if not raw_status:
        return None
    s = str(raw_status).strip().lower().replace(' ', '_').replace('-', '_')
    if s in ('to_do', 'todo'):
        return STATUS_TODO
    if s == 'pending':
        return STATUS_PENDING
    if s == 'in_progress':
        return STATUS_IN_PROGRESS
    if s == 'blocked':
        return STATUS_BLOCKED
    if s == 'in_review':
        return STATUS_IN_REVIEW
    if s in ('completed', 'done'):
        return STATUS_COMPLETED
    if s in ('changes_requested', 'change_requested'):
        return STATUS_CHANGES_REQUESTED
    return None


def get_user_led_team_ids(user):
    """Return list of team IDs where user has lead privileges."""
    if not user.is_authenticated:
        return []
    if user.role in ('super_admin', 'admin'):
        return [t.id for t in Team.query.all()]
    if user.role == 'team_lead':
        led = set(t.id for t in Team.query.filter_by(lead_id=user.id).all())
        member_led = db.session.query(team_members.c.team_id).filter(
            team_members.c.user_id == user.id,
            team_members.c.role == 'lead'
        ).all()
        for row in member_led:
            led.add(row[0])
        return list(led)
    return []


def get_user_all_team_ids(user):
    """Return all team IDs user is a member of (as lead or member)."""
    if not user.is_authenticated:
        return []
    if user.role in ('super_admin', 'admin'):
        return [t.id for t in Team.query.all()]
    teams = set(t.id for t in Team.query.filter_by(lead_id=user.id).all())
    member_teams = db.session.query(team_members.c.team_id).filter(
        team_members.c.user_id == user.id
    ).all()
    for row in member_teams:
        teams.add(row[0])
    return list(teams)


def get_permitted_assignee_ids_for_user(user, team_id=None):
    """
    Return set of user IDs that `user` is authorized to assign tasks to.
    Returns None if user has unrestricted assignment privileges (admin).
    """
    if user.role in ('super_admin', 'admin'):
        return None

    if user.role == 'team_lead':
        led_teams = get_user_led_team_ids(user)
        if team_id is not None:
            if team_id not in led_teams:
                return set()  # Not authorized to assign in this team
            target_teams = [team_id]
        else:
            target_teams = led_teams

        allowed = {user.id}
        if target_teams:
            rows = db.session.query(team_members.c.user_id).filter(
                team_members.c.team_id.in_(target_teams)
            ).all()
            for r in rows:
                allowed.add(r[0])
        # Also include any direct reports
        direct_reports = User.query.filter_by(reports_to_id=user.id).all()
        for dr in direct_reports:
            allowed.add(dr.id)
        return allowed

    # Regular employee: can only assign personal tasks to self
    return {user.id}


def can_user_view_task(user, task):
    if user.role in ('super_admin', 'admin'):
        return True
    if task.user_id == user.id:
        return True
    if task.assigned_to_id == user.id:
        return True
    if task.team_id and task.team_id in get_user_led_team_ids(user):
        return True
    return False


def can_user_manage_task(user, task):
    """Return True if user has manager/creator rights over this task."""
    if user.role in ('super_admin', 'admin'):
        return True
    if task.user_id == user.id:
        return True
    if task.team_id and task.team_id in get_user_led_team_ids(user):
        return True
    return False


def can_user_review_task(user, task):
    """Return True if user can approve or request changes on this task."""
    if user.role in ('super_admin', 'admin'):
        return True
    if task.team_id and task.team_id in get_user_led_team_ids(user):
        return True
    if task.user_id == user.id and user.id != task.assigned_to_id:
        return True
    return False


@tasks_bp.route('', methods=['GET'])
@login_required
def get_tasks():
    # Base query based on user role and permitted boundaries
    if current_user.role in ('super_admin', 'admin'):
        query = Task.query
    elif current_user.role == 'team_lead':
        led_team_ids = get_user_led_team_ids(current_user)
        conditions = [
            Task.user_id == current_user.id,
            Task.assigned_to_id == current_user.id,
        ]
        if led_team_ids:
            conditions.append(Task.team_id.in_(led_team_ids))
        query = Task.query.filter(or_(*conditions))
    else:
        # Employee: see tasks created by self or assigned to self
        query = Task.query.filter(
            or_(
                Task.user_id == current_user.id,
                Task.assigned_to_id == current_user.id,
            )
        )

    # Scope filter
    scope = (request.args.get('scope') or '').strip().lower()
    if scope == 'assigned_to_me':
        query = query.filter(Task.assigned_to_id == current_user.id)
    elif scope == 'created_by_me':
        query = query.filter(Task.user_id == current_user.id)
    elif scope == 'team':
        query = query.filter(Task.team_id.isnot(None))

    # Assigned to filter
    assigned_to = request.args.get('assigned_to_id')
    if assigned_to:
        if assigned_to.lower() == 'me':
            query = query.filter(Task.assigned_to_id == current_user.id)
        else:
            try:
                query = query.filter(Task.assigned_to_id == int(assigned_to))
            except ValueError:
                pass

    # Team filter
    team_id = request.args.get('team_id')
    if team_id:
        try:
            query = query.filter(Task.team_id == int(team_id))
        except ValueError:
            pass

    # Search query
    q = (request.args.get('q') or '').strip()
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Task.title.ilike(search_pattern),
                Task.description.ilike(search_pattern),
                Task.acceptance_criteria.ilike(search_pattern),
            )
        )

    # Status filter
    status = (request.args.get('status') or '').strip().lower()
    if status:
        norm_status = normalize_status(status)
        if norm_status:
            if norm_status in (STATUS_TODO, STATUS_PENDING):
                query = query.filter(Task.status.in_([STATUS_TODO, STATUS_PENDING]))
            else:
                query = query.filter(Task.status == norm_status)

    # Priority filter
    priority = (request.args.get('priority') or '').strip().lower()
    if priority in VALID_PRIORITIES:
        query = query.filter(Task.priority == priority)

    # Category filter
    category_id = request.args.get('category_id')
    if category_id:
        try:
            cat_id = int(category_id)
            query = query.filter(Task.category_id == cat_id)
        except ValueError:
            pass

    # Date range filters
    due_before = parse_date(request.args.get('due_before'))
    if due_before:
        query = query.filter(Task.due_date <= due_before)

    due_after = parse_date(request.args.get('due_after'))
    if due_after:
        query = query.filter(Task.due_date >= due_after)

    # Sorting
    sort = (request.args.get('sort') or 'created_at_desc').strip().lower()
    if sort == 'due_date_asc':
        query = query.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.id.desc())
    elif sort == 'due_date_desc':
        query = query.order_by(Task.due_date.is_(None), Task.due_date.desc(), Task.id.desc())
    elif sort == 'created_at_asc':
        query = query.order_by(Task.created_at.asc())
    elif sort == 'priority_desc':
        priority_weight = case(
            (Task.priority == 'high', 3),
            (Task.priority == 'medium', 2),
            (Task.priority == 'low', 1),
            else_=0
        )
        query = query.order_by(priority_weight.desc(), Task.created_at.desc())
    elif sort == 'priority_asc':
        priority_weight = case(
            (Task.priority == 'high', 3),
            (Task.priority == 'medium', 2),
            (Task.priority == 'low', 1),
            else_=0
        )
        query = query.order_by(priority_weight.asc(), Task.created_at.desc())
    elif sort == 'title_asc':
        query = query.order_by(Task.title.asc())
    else:
        query = query.order_by(Task.created_at.desc())

    tasks = query.all()
    return api_success([t.to_dict() for t in tasks])


@tasks_bp.route('', methods=['POST'])
@login_required
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return api_error('Title is required.', 400)

    priority = (data.get('priority') or 'medium').strip().lower()
    if priority not in VALID_PRIORITIES:
        return api_error(f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}", 400)

    raw_status = data.get('status')
    if raw_status:
        status = normalize_status(raw_status)
        if not status:
            return api_error(f"Invalid status: {raw_status}", 400)
    else:
        status = STATUS_PENDING

    # Parse dates
    due_date = parse_date(data.get('due_date'))
    start_date = parse_date(data.get('start_date'))

    # Category validation
    category_id = data.get('category_id')
    if category_id:
        try:
            category_id = int(category_id)
            cat = Category.query.filter_by(id=category_id).first()
            if not cat or (cat.user_id != current_user.id and current_user.role not in ('super_admin', 'admin')):
                return api_error('Category not found or does not belong to you.', 404)
        except (ValueError, TypeError):
            category_id = None
    else:
        category_id = None

    # Team & Assignment validation
    team_id = data.get('team_id')
    if team_id:
        try:
            team_id = int(team_id)
            team = db.session.get(Team, team_id)
            if not team:
                return api_error('Team not found.', 404)
        except (ValueError, TypeError):
            team_id = None

    assigned_to_id = data.get('assigned_to_id')
    if assigned_to_id:
        try:
            assigned_to_id = int(assigned_to_id)
            assignee = db.session.get(User, assigned_to_id)
            if not assignee:
                return api_error('Assigned user not found.', 404)
        except (ValueError, TypeError):
            assigned_to_id = None

    # Authorization rules for creation & assignment
    if current_user.role == 'employee':
        if assigned_to_id and assigned_to_id != current_user.id:
            return api_error('Employees cannot assign tasks to other employees.', 403)
        if team_id:
            return api_error('Employees cannot assign tasks to teams.', 403)

    elif current_user.role == 'team_lead':
        led_team_ids = get_user_led_team_ids(current_user)
        if team_id and team_id not in led_team_ids:
            return api_error('Team Leads cannot assign tasks outside their authorized scope.', 403)

        if assigned_to_id and assigned_to_id != current_user.id:
            allowed_assignees = get_permitted_assignee_ids_for_user(current_user, team_id=team_id)
            if allowed_assignees is not None and assigned_to_id not in allowed_assignees:
                return api_error('Team Leads cannot assign tasks outside their authorized scope.', 403)

    acceptance_criteria = (data.get('acceptance_criteria') or '').strip()
    is_recurring = bool(data.get('is_recurring', False))
    recurrence_interval = (data.get('recurrence_interval') or '').strip() or None

    completed_at = datetime.now(timezone.utc) if status == STATUS_COMPLETED else None

    task = Task(
        title=title,
        description=(data.get('description') or '').strip(),
        priority=priority,
        status=status,
        start_date=start_date,
        due_date=due_date,
        completed_at=completed_at,
        category_id=category_id,
        team_id=team_id,
        assigned_to_id=assigned_to_id,
        acceptance_criteria=acceptance_criteria,
        is_recurring=is_recurring,
        recurrence_interval=recurrence_interval,
        user_id=current_user.id,
    )

    db.session.add(task)
    db.session.flush()

    # Create initial status history entry
    history = TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=None,
        new_status=task.status,
        comment='Task created',
    )
    db.session.add(history)
    db.session.commit()

    return api_success(task.to_dict(include_history=True), message='Task created successfully', status_code=201)


@tasks_bp.route('/<int:task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    return api_success(task.to_dict(include_history=True))


@tasks_bp.route('/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    data = request.get_json(silent=True) or {}
    is_manager = can_user_manage_task(current_user, task)
    is_assignee = (task.assigned_to_id == current_user.id)

    # Security check: If caller is regular employee assignee and NOT manager
    if not is_manager:
        protected_fields = [
            'title', 'description', 'priority', 'due_date',
            'start_date', 'acceptance_criteria', 'assigned_to_id',
            'team_id', 'category_id', 'is_recurring'
        ]
        for field in protected_fields:
            if field in data and data[field] != getattr(task, field):
                return api_error('Employees cannot modify protected task details or assignment.', 403)

    old_status = task.status
    status_changed = False

    # Update title
    if 'title' in data:
        title = (data.get('title') or '').strip()
        if not title:
            return api_error('Title cannot be empty.', 400)
        task.title = title

    # Update description
    if 'description' in data:
        task.description = (data.get('description') or '').strip()

    # Update priority
    if 'priority' in data:
        priority = (data.get('priority') or '').strip().lower()
        if priority not in VALID_PRIORITIES:
            return api_error(f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}", 400)
        task.priority = priority

    # Update dates
    if 'due_date' in data:
        raw_due = data.get('due_date')
        task.due_date = parse_date(raw_due) if raw_due else None

    if 'start_date' in data:
        raw_start = data.get('start_date')
        task.start_date = parse_date(raw_start) if raw_start else None

    # Update acceptance criteria
    if 'acceptance_criteria' in data and is_manager:
        task.acceptance_criteria = (data.get('acceptance_criteria') or '').strip()

    # Update submission notes
    if 'submission_notes' in data:
        task.submission_notes = (data.get('submission_notes') or '').strip()

    # Update recurring
    if 'is_recurring' in data and is_manager:
        task.is_recurring = bool(data.get('is_recurring'))
    if 'recurrence_interval' in data and is_manager:
        task.recurrence_interval = (data.get('recurrence_interval') or '').strip() or None

    # Update category
    if 'category_id' in data and is_manager:
        cat_id = data.get('category_id')
        if cat_id:
            try:
                cat_id = int(cat_id)
                cat = Category.query.filter_by(id=cat_id).first()
                if not cat or (cat.user_id != current_user.id and current_user.role not in ('super_admin', 'admin')):
                    return api_error('Category not found.', 404)
                task.category_id = cat_id
            except (ValueError, TypeError):
                task.category_id = None
        else:
            task.category_id = None

    # Update team & assignment (manager only)
    if ('team_id' in data or 'assigned_to_id' in data) and is_manager:
        new_team_id = task.team_id
        if 'team_id' in data:
            raw_t = data.get('team_id')
            new_team_id = int(raw_t) if raw_t else None

        new_assigned_id = task.assigned_to_id
        if 'assigned_to_id' in data:
            raw_a = data.get('assigned_to_id')
            new_assigned_id = int(raw_a) if raw_a else None

        if current_user.role == 'team_lead':
            led_teams = get_user_led_team_ids(current_user)
            if new_team_id and new_team_id not in led_teams:
                return api_error('Team Leads cannot assign tasks outside their authorized scope.', 403)
            if new_assigned_id and new_assigned_id != current_user.id:
                allowed_assignees = get_permitted_assignee_ids_for_user(current_user, team_id=new_team_id)
                if allowed_assignees is not None and new_assigned_id not in allowed_assignees:
                    return api_error('Team Leads cannot assign tasks outside their authorized scope.', 403)

        task.team_id = new_team_id
        task.assigned_to_id = new_assigned_id

    # Update status
    if 'status' in data:
        raw_status = data.get('status')
        new_status = normalize_status(raw_status)
        if not new_status:
            return api_error(f"Invalid status: {raw_status}", 400)

        # Enforce employee status transition rules
        if not is_manager:
            # Employee updating assigned task
            if new_status == STATUS_COMPLETED:
                return api_error('Employees must submit work for review rather than marking assigned tasks completed directly.', 403)
            if new_status not in (STATUS_TODO, STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_IN_REVIEW):
                return api_error(f"Cannot transition to status {new_status}.", 403)

        if new_status != old_status:
            task.status = new_status
            status_changed = True
            if new_status == STATUS_COMPLETED:
                task.completed_at = datetime.now(timezone.utc)
            else:
                task.completed_at = None

    # Log status change in history
    if status_changed:
        comment = data.get('comment') or f"Status updated from {STATUS_LABELS.get(old_status, old_status)} to {task.status_label}"
        history = TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=task.status,
            comment=comment,
        )
        db.session.add(history)

    db.session.commit()
    return api_success(task.to_dict(include_history=True), message='Task updated successfully')


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    if not can_user_manage_task(current_user, task):
        return api_error('You do not have permission to delete this task.', 403)

    db.session.delete(task)
    db.session.commit()
    return api_success(message='Task deleted successfully')


@tasks_bp.route('/<int:task_id>/complete', methods=['PATCH'])
@login_required
def toggle_task_complete(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    is_manager = can_user_manage_task(current_user, task)
    is_personal_task = (task.user_id == current_user.id and (task.assigned_to_id is None or task.assigned_to_id == current_user.id))

    if not is_manager and not is_personal_task:
        return api_error('Employees must submit work for review rather than marking assigned tasks completed directly.', 403)

    data = request.get_json(silent=True) or {}
    explicit_status = data.get('status')
    old_status = task.status

    if explicit_status:
        norm = normalize_status(explicit_status)
        if not norm or norm not in (STATUS_COMPLETED, STATUS_PENDING, STATUS_TODO):
            return api_error('Invalid status', 400)
        task.status = norm
        task.completed_at = datetime.now(timezone.utc) if norm == STATUS_COMPLETED else None
    else:
        # Toggle status
        if task.status == STATUS_COMPLETED:
            task.status = STATUS_PENDING
            task.completed_at = None
        else:
            task.status = STATUS_COMPLETED
            task.completed_at = datetime.now(timezone.utc)

    history = TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=old_status,
        new_status=task.status,
        comment='Task completion toggled',
    )
    db.session.add(history)
    db.session.commit()
    return api_success(task.to_dict(include_history=True), message='Task status updated')


@tasks_bp.route('/<int:task_id>/submit', methods=['POST'])
@login_required
def submit_task_for_review(task_id):
    """Assignee employee or creator submits task work for lead review."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    # Caller must be assignee or creator or lead
    if task.assigned_to_id != current_user.id and not can_user_manage_task(current_user, task):
        return api_error('You do not have permission to submit work for this task.', 403)

    data = request.get_json(silent=True) or {}
    notes = (data.get('notes') or '').strip()

    old_status = task.status
    task.status = STATUS_IN_REVIEW
    task.submission_notes = notes

    history = TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=old_status,
        new_status=STATUS_IN_REVIEW,
        comment=f"Submitted for review: {notes}" if notes else "Submitted work for review",
    )
    db.session.add(history)
    db.session.commit()

    return api_success(task.to_dict(include_history=True), message='Task submitted for review successfully')


@tasks_bp.route('/<int:task_id>/review', methods=['POST'])
@login_required
def review_task(task_id):
    """Team Lead / Manager approves task or requests changes."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    if not can_user_review_task(current_user, task):
        return api_error('You do not have permission to review this task.', 403)

    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip().lower()
    notes = (data.get('notes') or '').strip()

    old_status = task.status

    if action == 'approve':
        task.status = STATUS_COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        task.review_notes = notes
        comment = f"Review approved: {notes}" if notes else "Task approved and marked completed"
        message = 'Task approved and completed'
    elif action in ('request_changes', 'changes_requested', 'reject'):
        task.status = STATUS_CHANGES_REQUESTED
        task.completed_at = None
        task.review_notes = notes
        comment = f"Changes requested: {notes}" if notes else "Changes requested on submitted work"
        message = 'Changes requested on task'
    else:
        return api_error("Action must be either 'approve' or 'request_changes'.", 400)

    history = TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=old_status,
        new_status=task.status,
        comment=comment,
    )
    db.session.add(history)
    db.session.commit()

    return api_success(task.to_dict(include_history=True), message=message)
