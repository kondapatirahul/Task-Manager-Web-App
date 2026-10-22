import os
import shutil
from datetime import datetime, date, timezone
from flask import Blueprint, request, current_app, send_file, make_response
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
    TaskComment,
    TaskSubmission,
    TaskAttachment,
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
from app.file_utils import (
    validate_uploaded_file,
    save_attachment_file,
    get_attachment_filepath,
    delete_attachment_file,
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_MAX_FILES_PER_MESSAGE,
)
from app.services.notifications import notify_task_collaboration_event

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
    if request.is_json:
        data = request.get_json(silent=True) or {}
        files = []
    else:
        data = request.form.to_dict()
        files = request.files.getlist('files') or request.files.getlist('reference_files')

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

    # Validate any uploaded reference files
    max_size = current_app.config.get('MAX_ATTACHMENT_SIZE', DEFAULT_MAX_FILE_SIZE)
    max_files = current_app.config.get('MAX_ATTACHMENTS_PER_MESSAGE', DEFAULT_MAX_FILES_PER_MESSAGE)

    if len(files) > max_files:
        return api_error(f"Cannot upload more than {max_files} reference files at once.", 400)

    validated_files = []
    for f in files:
        if f and f.filename and f.filename.strip():
            ok, err, meta = validate_uploaded_file(f, max_size)
            if not ok:
                return api_error(err, 400)
            validated_files.append((f, meta))

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

    saved_filepaths = []
    try:
        # Save reference files if provided
        upload_root = current_app.config.get('UPLOAD_FOLDER')
        for f, meta in validated_files:
            storage_name, dest_path = save_attachment_file(f, task.id, upload_root, meta['extension'])
            saved_filepaths.append(dest_path)
            attachment = TaskAttachment(
                task_id=task.id,
                uploader_id=current_user.id,
                attachment_type='reference',
                original_filename=meta['original_filename'],
                storage_name=storage_name,
                file_size=meta['file_size'],
                file_type=meta['mime_type'],
                file_extension=meta['extension'],
            )
            db.session.add(attachment)

        # Create initial status history entry
        init_comment = 'Task created'
        if validated_files:
            init_comment += f' with {len(validated_files)} reference attachment(s)'

        history = TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=None,
            new_status=task.status,
            comment=init_comment,
        )
        db.session.add(history)
        db.session.commit()

        if validated_files:
            notify_task_collaboration_event(
                'reference_uploaded',
                task,
                current_user,
                recipients=[task.assigned_to_id] if task.assigned_to_id else [],
                metadata={'count': len(validated_files)}
            )

        return api_success(task.to_dict(include_history=True, include_collaboration=True), message='Task created successfully', status_code=201)
    except Exception as e:
        db.session.rollback()
        for p in saved_filepaths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        raise e


@tasks_bp.route('/<int:task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    return api_success(task.to_dict(include_history=True, include_collaboration=True))


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

    # Clean up attachment files from disk
    upload_root = current_app.config.get('UPLOAD_FOLDER')
    if upload_root:
        task_dir = os.path.join(upload_root, f"task_{task.id}")
        if os.path.isdir(task_dir):
            try:
                shutil.rmtree(task_dir)
            except OSError:
                pass

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
    return api_success(task.to_dict(include_history=True, include_collaboration=True), message='Task status updated')


@tasks_bp.route('/<int:task_id>/submit', methods=['POST'])
@login_required
def submit_task_for_review(task_id):
    """Assignee employee or creator submits task work for lead review with deliverable files."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    # Caller must be assignee or creator or lead
    if task.assigned_to_id != current_user.id and not can_user_manage_task(current_user, task):
        return api_error('You do not have permission to submit work for this task.', 403)

    if request.is_json:
        data = request.get_json(silent=True) or {}
        notes = (data.get('notes') or '').strip()
        files = []
    else:
        notes = (request.form.get('notes') or '').strip()
        files = request.files.getlist('files') or request.files.getlist('deliverables')

    max_size = current_app.config.get('MAX_ATTACHMENT_SIZE', DEFAULT_MAX_FILE_SIZE)
    max_files = current_app.config.get('MAX_ATTACHMENTS_PER_MESSAGE', DEFAULT_MAX_FILES_PER_MESSAGE)

    if len(files) > max_files:
        return api_error(f"Cannot upload more than {max_files} deliverable files at once.", 400)

    # Validate deliverable files
    validated_files = []
    for f in files:
        if f and f.filename and f.filename.strip():
            ok, err, meta = validate_uploaded_file(f, max_size)
            if not ok:
                return api_error(err, 400)
            validated_files.append((f, meta))

    saved_filepaths = []
    try:
        old_status = task.status
        task.status = STATUS_IN_REVIEW
        task.submission_notes = notes

        # Create structured submission record
        submission = TaskSubmission(
            task_id=task.id,
            submitted_by_id=current_user.id,
            summary=notes,
            status='pending_review',
        )
        db.session.add(submission)
        db.session.flush()

        # Save deliverable attachments
        upload_root = current_app.config.get('UPLOAD_FOLDER')
        for f, meta in validated_files:
            storage_name, dest_path = save_attachment_file(f, task.id, upload_root, meta['extension'])
            saved_filepaths.append(dest_path)
            attachment = TaskAttachment(
                task_id=task.id,
                uploader_id=current_user.id,
                submission_id=submission.id,
                attachment_type='submission',
                original_filename=meta['original_filename'],
                storage_name=storage_name,
                file_size=meta['file_size'],
                file_type=meta['mime_type'],
                file_extension=meta['extension'],
            )
            db.session.add(attachment)

        deliverable_count = len(validated_files)
        hist_comment = f"Submitted work for review ({deliverable_count} deliverable(s)): {notes}" if deliverable_count else (f"Submitted for review: {notes}" if notes else "Submitted work for review")

        history = TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=STATUS_IN_REVIEW,
            comment=hist_comment,
        )
        db.session.add(history)
        db.session.commit()

        notify_task_collaboration_event(
            'submission_created',
            task,
            current_user,
            recipients=[task.user_id] if task.user_id != current_user.id else [],
            metadata={'deliverable_count': deliverable_count}
        )

        return api_success(task.to_dict(include_history=True, include_collaboration=True), message='Task submitted for review successfully')
    except Exception as e:
        db.session.rollback()
        for p in saved_filepaths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        raise e


@tasks_bp.route('/<int:task_id>/review', methods=['POST'])
@login_required
def review_task(task_id):
    """Team Lead / Manager approves task or requests changes and preserves review history."""
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
        new_status = STATUS_COMPLETED
        task.status = STATUS_COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        task.review_notes = notes
        submission_status = 'approved'
        comment = f"Review approved: {notes}" if notes else "Task approved and marked completed"
        message = 'Task approved and completed'
        event_type = 'review_approved'
    elif action in ('request_changes', 'changes_requested', 'reject'):
        new_status = STATUS_CHANGES_REQUESTED
        task.status = STATUS_CHANGES_REQUESTED
        task.completed_at = None
        task.review_notes = notes
        submission_status = 'changes_requested'
        comment = f"Changes requested: {notes}" if notes else "Changes requested on submitted work"
        message = 'Changes requested on task'
        event_type = 'review_changes_requested'
    else:
        return api_error("Action must be either 'approve' or 'request_changes'.", 400)

    # Update latest pending submission record if available
    latest_sub = task.submissions.filter_by(status='pending_review').first()
    if not latest_sub:
        latest_sub = task.submissions.first()
    if latest_sub:
        latest_sub.status = submission_status
        latest_sub.reviewed_by_id = current_user.id
        latest_sub.reviewed_at = datetime.now(timezone.utc)
        latest_sub.review_feedback = notes

    history = TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=old_status,
        new_status=new_status,
        comment=comment,
    )
    db.session.add(history)
    db.session.commit()

    notify_task_collaboration_event(
        event_type,
        task,
        current_user,
        recipients=[task.assigned_to_id] if task.assigned_to_id else [],
        metadata={'review_action': action}
    )

    return api_success(task.to_dict(include_history=True, include_collaboration=True), message=message)


@tasks_bp.route('/<int:task_id>/comments', methods=['GET'])
@login_required
def get_task_comments(task_id):
    """Retrieve chronological discussion messages for a task."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    comments = task.comments.all()
    return api_success([c.to_dict() for c in comments])


@tasks_bp.route('/<int:task_id>/comments', methods=['POST'])
@login_required
def post_task_comment(task_id):
    """Post a discussion message with optional file attachments."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    if request.is_json:
        data = request.get_json(silent=True) or {}
        content = (data.get('content') or '').strip()
        files = []
    else:
        content = (request.form.get('content') or '').strip()
        files = request.files.getlist('files') or request.files.getlist('attachments')

    if not content and not files:
        return api_error('Comment content or file attachment is required.', 400)

    max_size = current_app.config.get('MAX_ATTACHMENT_SIZE', DEFAULT_MAX_FILE_SIZE)
    max_files = current_app.config.get('MAX_ATTACHMENTS_PER_MESSAGE', DEFAULT_MAX_FILES_PER_MESSAGE)

    if len(files) > max_files:
        return api_error(f"Cannot upload more than {max_files} files at once.", 400)

    validated_files = []
    for f in files:
        if f and f.filename and f.filename.strip():
            ok, err, meta = validate_uploaded_file(f, max_size)
            if not ok:
                return api_error(err, 400)
            validated_files.append((f, meta))

    saved_filepaths = []
    try:
        comment = TaskComment(
            task_id=task.id,
            user_id=current_user.id,
            content=content,
        )
        db.session.add(comment)
        db.session.flush()

        upload_root = current_app.config.get('UPLOAD_FOLDER')
        for f, meta in validated_files:
            storage_name, dest_path = save_attachment_file(f, task.id, upload_root, meta['extension'])
            saved_filepaths.append(dest_path)
            attachment = TaskAttachment(
                task_id=task.id,
                uploader_id=current_user.id,
                comment_id=comment.id,
                attachment_type='comment',
                original_filename=meta['original_filename'],
                storage_name=storage_name,
                file_size=meta['file_size'],
                file_type=meta['mime_type'],
                file_extension=meta['extension'],
            )
            db.session.add(attachment)

        # Activity log in TaskStatusHistory
        act_comment = f"Posted message with {len(validated_files)} attachment(s)" if validated_files else "Added comment to task discussion"
        history = TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=task.status,
            new_status=task.status,
            comment=act_comment,
        )
        db.session.add(history)
        db.session.commit()

        notify_task_collaboration_event(
            'comment_created',
            task,
            current_user,
            recipients=[task.user_id, task.assigned_to_id],
            metadata={'comment_id': comment.id, 'attachments_count': len(validated_files)}
        )

        return api_success(comment.to_dict(), message='Comment posted successfully', status_code=201)
    except Exception as e:
        db.session.rollback()
        for p in saved_filepaths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        raise e


@tasks_bp.route('/<int:task_id>/attachments', methods=['GET'])
@login_required
def get_task_attachments(task_id):
    """Retrieve all attachments for a task, optionally filtered by type."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    query = task.attachments
    att_type = request.args.get('type')
    if att_type:
        query = query.filter_by(attachment_type=att_type.strip().lower())

    attachments = query.all()
    return api_success([a.to_dict() for a in attachments])


@tasks_bp.route('/<int:task_id>/attachments', methods=['POST'])
@login_required
def upload_task_attachments(task_id):
    """Upload task reference attachments (team leads and managers)."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    if not can_user_manage_task(current_user, task):
        return api_error('Only managers or team leads can upload task reference attachments.', 403)

    files = request.files.getlist('files') or request.files.getlist('reference_files')
    if not files:
        return api_error('No files provided for upload.', 400)

    max_size = current_app.config.get('MAX_ATTACHMENT_SIZE', DEFAULT_MAX_FILE_SIZE)
    max_files = current_app.config.get('MAX_ATTACHMENTS_PER_MESSAGE', DEFAULT_MAX_FILES_PER_MESSAGE)

    if len(files) > max_files:
        return api_error(f"Cannot upload more than {max_files} files at once.", 400)

    validated_files = []
    for f in files:
        if f and f.filename and f.filename.strip():
            ok, err, meta = validate_uploaded_file(f, max_size)
            if not ok:
                return api_error(err, 400)
            validated_files.append((f, meta))

    if not validated_files:
        return api_error('No valid files provided.', 400)

    attachment_type = (request.form.get('attachment_type') or 'reference').strip().lower()
    if attachment_type not in ('reference', 'comment', 'submission'):
        attachment_type = 'reference'

    saved_filepaths = []
    created_attachments = []
    try:
        upload_root = current_app.config.get('UPLOAD_FOLDER')
        for f, meta in validated_files:
            storage_name, dest_path = save_attachment_file(f, task.id, upload_root, meta['extension'])
            saved_filepaths.append(dest_path)
            att = TaskAttachment(
                task_id=task.id,
                uploader_id=current_user.id,
                attachment_type=attachment_type,
                original_filename=meta['original_filename'],
                storage_name=storage_name,
                file_size=meta['file_size'],
                file_type=meta['mime_type'],
                file_extension=meta['extension'],
            )
            db.session.add(att)
            created_attachments.append(att)

        filenames = [m['original_filename'] for _, m in validated_files]
        hist_comment = f"Uploaded reference attachment(s): {', '.join(filenames)}"
        history = TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=task.status,
            new_status=task.status,
            comment=hist_comment,
        )
        db.session.add(history)
        db.session.commit()

        notify_task_collaboration_event(
            'reference_uploaded',
            task,
            current_user,
            recipients=[task.assigned_to_id] if task.assigned_to_id else [],
            metadata={'count': len(created_attachments)}
        )

        return api_success([a.to_dict() for a in created_attachments], message='Attachments uploaded successfully', status_code=201)
    except Exception as e:
        db.session.rollback()
        for p in saved_filepaths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        raise e


@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>/download', methods=['GET'])
@login_required
def download_task_attachment(task_id, attachment_id):
    """Authorized file download with safe content disposition and nosniff header."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    attachment = db.session.get(TaskAttachment, attachment_id)
    if not attachment or attachment.task_id != task.id:
        return api_error('Attachment not found.', 404)

    upload_root = current_app.config.get('UPLOAD_FOLDER')
    filepath = get_attachment_filepath(task.id, attachment.storage_name, upload_root)
    if not filepath or not os.path.isfile(filepath):
        return api_error('File not found on storage.', 404)

    response = make_response(send_file(
        filepath,
        as_attachment=True,
        download_name=attachment.original_filename,
        mimetype=attachment.file_type or 'application/octet-stream'
    ))
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
    return response


@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>/preview', methods=['GET'])
@login_required
def preview_task_attachment(task_id, attachment_id):
    """Authorized inline preview for safe file formats with sandboxing header."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    attachment = db.session.get(TaskAttachment, attachment_id)
    if not attachment or attachment.task_id != task.id:
        return api_error('Attachment not found.', 404)

    ext = (attachment.file_extension or '').lower()
    if ext not in ('png', 'jpg', 'jpeg', 'pdf', 'txt'):
        return api_error('Inline preview not supported for this file type. Please download the file.', 400)

    upload_root = current_app.config.get('UPLOAD_FOLDER')
    filepath = get_attachment_filepath(task.id, attachment.storage_name, upload_root)
    if not filepath or not os.path.isfile(filepath):
        return api_error('File not found on storage.', 404)

    response = make_response(send_file(
        filepath,
        as_attachment=False,
        download_name=attachment.original_filename,
        mimetype=attachment.file_type
    ))
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    response.headers['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
    return response


@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@login_required
def delete_task_attachment(task_id, attachment_id):
    """Delete an attachment (uploader or manager only)."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    attachment = db.session.get(TaskAttachment, attachment_id)
    if not attachment or attachment.task_id != task.id:
        return api_error('Attachment not found.', 404)

    # Permission check: must be the uploader or a manager
    is_uploader = (attachment.uploader_id == current_user.id)
    is_manager = can_user_manage_task(current_user, task)
    if not is_uploader and not is_manager:
        return api_error('You do not have permission to delete this attachment.', 403)

    upload_root = current_app.config.get('UPLOAD_FOLDER')
    delete_attachment_file(task.id, attachment.storage_name, upload_root)

    filename = attachment.original_filename
    db.session.delete(attachment)

    history = TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=task.status,
        new_status=task.status,
        comment=f"Deleted attachment: {filename}",
    )
    db.session.add(history)
    db.session.commit()

    return api_success(message='Attachment deleted successfully')


@tasks_bp.route('/<int:task_id>/submissions', methods=['GET'])
@login_required
def get_task_submissions(task_id):
    """Retrieve full submission and review history for a task."""
    task = db.session.get(Task, task_id)
    if not task or not can_user_view_task(current_user, task):
        return api_error('Task not found.', 404)

    submissions = task.submissions.all()
    return api_success([s.to_dict() for s in submissions])

