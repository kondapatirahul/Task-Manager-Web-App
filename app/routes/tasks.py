"""
Task Management API routes with Enterprise extensions.
Supports list, Kanban board, team assignment, subtasks, recurrence, and lifecycle workflows.
"""
import os
import uuid
from datetime import datetime, date, timedelta, timezone
from werkzeug.utils import secure_filename
from flask import Blueprint, request, current_app, send_file
from flask_login import current_user, login_required
from sqlalchemy import or_, desc, asc, case
from app import db
from app.models import (
    Task, Category, SubTask, User, Team, TeamMember,
    TaskStatusHistory, TaskMessage, TaskAttachment, WorkSubmission,
    STATUS_TODO, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_IN_REVIEW,
    STATUS_CHANGES_REQUESTED, STATUS_COMPLETED, STATUS_PENDING,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE
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
    STATUS_IN_REVIEW, STATUS_CHANGES_REQUESTED, STATUS_COMPLETED, 'pending'
}
VALID_STATUSES = VALID_UPDATE_STATUSES
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx', 'txt'}


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
    if not user or not user.is_authenticated:
        return False
    # Personal tasks are managed exclusively by their owner
    if getattr(task, 'is_personal', False):
        return task.creator_id == user.id or task.assignee_id == user.id or task.user_id == user.id
    if user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return True
    if task.creator_id == user.id:
        return True
    if user.is_team_lead:
        led_teams = Team.query.filter_by(lead_id=user.id).all()
        led_team_ids = {team.id for team in led_teams}
        if task.team_id in led_team_ids or (user.team_id and task.team_id == user.team_id):
            return True
        if task.assignee_id:
            member = TeamMember.query.filter(TeamMember.team_id.in_(led_team_ids), TeamMember.user_id == task.assignee_id).first()
            if member:
                return True
    return False


def can_view_task(task, user):
    """Check if user has permission to view task."""
    if not user or not user.is_authenticated:
        return False
    # Personal tasks are strictly private to their owner
    if getattr(task, 'is_personal', False):
        return task.creator_id == user.id or task.assignee_id == user.id or task.user_id == user.id
    if user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return True
    if task.user_id == user.id or task.creator_id == user.id or task.assignee_id == user.id:
        return True
    if user.is_team_lead:
        led_teams = Team.query.filter_by(lead_id=user.id).all()
        led_team_ids = {team.id for team in led_teams}
        if task.team_id in led_team_ids or (user.team_id and task.team_id == user.team_id):
            return True
        if task.assignee_id:
            member = TeamMember.query.filter(TeamMember.team_id.in_(led_team_ids), TeamMember.user_id == task.assignee_id).first()
            if member:
                return True
            if User.query.filter(User.id == task.assignee_id, User.team_id.in_(led_team_ids)).first():
                return True
    return False


def validate_uploaded_file(file, max_size=None):
    if not file or not file.filename:
        return 'File cannot be empty.'
    filename = secure_filename(file.filename)
    if not filename or '.' not in filename:
        return 'File format is not supported.'
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return 'File format is not supported.'
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size == 0:
        return 'File cannot be empty.'
    limit = max_size or current_app.config.get('MAX_ATTACHMENT_SIZE', 16 * 1024 * 1024)
    if size > limit:
        return 'File exceeds maximum size limit.'
    header = file.read(16)
    file.seek(0)
    if ext == 'pdf':
        if not header.startswith(b'%PDF'):
            return 'File content does not match expected format for the file extension.'
    elif ext == 'png':
        if not header.startswith(b'\x89PNG'):
            return 'File content does not match expected format for the file extension.'
    elif ext in ('jpg', 'jpeg'):
        if not header.startswith(b'\xff\xd8\xff'):
            return 'File content does not match expected format for the file extension.'
    elif ext in ('docx', 'xlsx'):
        if not header.startswith(b'PK\x03\x04'):
            return 'File content does not match expected format for the file extension.'
    elif ext == 'txt':
        try:
            sample = file.read(512)
            file.seek(0)
            sample.decode('utf-8')
        except UnicodeDecodeError:
            return 'File content does not match expected format for the file extension.'
    return None


def save_file_safely(file):
    raw_name = file.filename or 'file'
    clean_name = os.path.basename(raw_name).replace('\\', '/').split('/')[-1]
    filename = secure_filename(clean_name) or 'attachment'
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.instance_path, 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    saved_path = os.path.join(upload_dir, unique_name)
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    file.save(saved_path)
    return clean_name, saved_path, size


# ── Task List & Filter ─────────────────────────────────────────────────────────

@tasks_bp.route('', methods=['GET'])
@login_required
@active_account_required
def get_tasks():
    scope = (request.args.get('scope') or '').strip().lower()

    if scope in ('assigned_to_me', 'my_tasks'):
        query = Task.query.filter(or_(Task.assignee_id == current_user.id, Task.user_id == current_user.id))
    elif scope == 'created_by_me':
        query = Task.query.filter(Task.creator_id == current_user.id)
    elif current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        query = Task.query.filter(or_(Task.is_personal.is_(False), Task.is_personal.is_(None), Task.creator_id == current_user.id))
    elif current_user.is_team_lead:
        led_teams = Team.query.filter_by(lead_id=current_user.id).all()
        led_team_ids = [t.id for t in led_teams]
        team_member_ids = [m.user_id for m in TeamMember.query.filter(TeamMember.team_id.in_(led_team_ids)).all()] if led_team_ids else []
        team_scope = [Task.team_id.in_(led_team_ids)] if led_team_ids else []
        member_scope = [Task.assignee_id.in_(team_member_ids), Task.user_id.in_(team_member_ids)] if team_member_ids else []
        query = Task.query.filter(
            or_(
                Task.user_id == current_user.id,
                Task.assignee_id == current_user.id,
                Task.creator_id == current_user.id,
                *team_scope,
                *member_scope
            ),
            or_(Task.is_personal.is_(False), Task.is_personal.is_(None), Task.creator_id == current_user.id)
        )
    else:
        query = Task.query.filter(
            or_(
                Task.user_id == current_user.id,
                Task.assignee_id == current_user.id,
                Task.creator_id == current_user.id
            )
        )

    # Filter by personal vs assigned
    is_personal_param = request.args.get('is_personal')
    if is_personal_param is not None and is_personal_param != '':
        if is_personal_param.lower() in ('true', '1'):
            query = query.filter(Task.is_personal.is_(True))
        elif is_personal_param.lower() in ('false', '0'):
            query = query.filter(or_(Task.is_personal.is_(False), Task.is_personal.is_(None)))

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
    else:
        query = query.order_by(Task.created_at.desc())

    tasks = query.all()
    return api_success([t.to_dict() for t in tasks])


# ── Create Task ────────────────────────────────────────────────────────────────

@tasks_bp.route('', methods=['POST'])
@login_required
@active_account_required
def create_task():
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    if not request.is_json and not request.form and not request.files:
        return api_error('A JSON object is required', 400)
    if not isinstance(data, dict):
        return api_error('A JSON object is required', 400)

    title = (data.get('title') or '').strip()
    if not title:
        return api_error('Title is required.', 400)
    if len(title) > 200:
        return api_error('Title must be between 1 and 200 characters.', 400)

    priority = (data.get('priority') or 'medium').strip().lower()
    if priority not in VALID_PRIORITIES:
        return api_error(f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}", 400)

    status = (data.get('status') or 'pending').strip().lower()
    if status not in VALID_CREATE_STATUSES:
        return api_error(f"Invalid status: status must be one of: {', '.join(sorted(VALID_CREATE_STATUSES))}", 400)
    if current_user.role == 'employee' and status in ('blocked', 'in_review', 'changes_requested'):
        return api_error(f"Invalid status: employees cannot create tasks with status '{status}'", 400)

    category_id = data.get('category_id')
    if category_id is True or category_id is False:
        return api_error('Category ID must be a positive integer or null', 400)
    if category_id:
        try:
            category_id = int(category_id)
            if category_id <= 0:
                return api_error('Category ID must be a positive integer or null', 400)
            cat = Category.query.filter_by(id=category_id).first()
            if not cat:
                return api_error('Category not found', 404)
        except (ValueError, TypeError):
            return api_error('Category ID must be a positive integer or null', 400)
    else:
        category_id = None

    due_date = parse_date(data.get('due_date'))
    start_date = parse_date(data.get('start_date'))
    completed_at = utc_now() if status == 'completed' else None

    assigned_to_id = data.get('assigned_to_id') or data.get('assignee_id')
    team_id = data.get('team_id')

    # Role-based assignment verification
    is_personal = bool(data.get('is_personal', False))
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD):
        if team_id:
            return api_error('Employees cannot assign tasks to teams', 403)
        if assigned_to_id and int(assigned_to_id) != current_user.id:
            return api_error('Employees cannot assign tasks to other employees', 403)
        assignee_id = current_user.id
        team_id = None
        is_personal = True
    elif current_user.is_team_lead:
        if is_personal:
            team_id = None
            assignee_id = current_user.id
        else:
            led_teams = Team.query.filter_by(lead_id=current_user.id).all()
            led_team_ids = {team.id for team in led_teams}
            if not led_team_ids:
                return api_error('Cannot assign outside authorized scope', 403)

            if team_id:
                try:
                    team_id = int(team_id)
                except (ValueError, TypeError):
                    return api_error('Cannot assign outside authorized scope', 403)
                if team_id not in led_team_ids:
                    return api_error('Cannot assign outside authorized scope', 403)
            else:
                team_id = next(iter(led_team_ids))

            if assigned_to_id:
                try:
                    assignee_id = int(assigned_to_id)
                except (ValueError, TypeError):
                    return api_error('Cannot assign outside authorized scope', 403)
                is_member = (TeamMember.query.filter_by(team_id=team_id, user_id=assignee_id).first()
                             or Team.query.filter_by(id=team_id, lead_id=assignee_id).first()
                             or User.query.filter_by(id=assignee_id, team_id=team_id).first())
                if not is_member:
                    return api_error('Cannot assign outside authorized scope', 403)
            else:
                assignee_id = current_user.id
    else:  # Admin / Super Admin
        if is_personal:
            team_id = None
            assignee_id = current_user.id
        else:
            if assigned_to_id:
                try:
                    assignee_id = int(assigned_to_id)
                except (ValueError, TypeError):
                    return api_error('Select a valid assignee.', 400)
                assignee_user = User.query.filter_by(id=assignee_id, account_active=True).first()
                if not assignee_user:
                    return api_error('The selected assignee is not an active account.', 400)
                if not team_id:
                    team_id = assignee_user.team_id
            else:
                assignee_id = current_user.id
            if team_id:
                try:
                    team_id = int(team_id)
                except (ValueError, TypeError):
                    team_id = None

    acceptance_criteria = (data.get('acceptance_criteria') or '').strip()
    progress = min(100, max(0, int(data.get('progress') or 0)))
    if status == 'completed':
        progress = 100

    is_recurring = bool(data.get('is_recurring', False))
    recurrence_interval = data.get('recurrence_interval') if is_recurring else None

    # Validate uploaded files before creating task
    files = request.files.getlist('files')
    if files:
        max_files = current_app.config.get('MAX_ATTACHMENTS_PER_MESSAGE', 10)
        if len(files) > max_files:
            return api_error(f'Cannot upload more than {max_files} files in a single message.', 400)
        for f in files:
            err = validate_uploaded_file(f)
            if err:
                return api_error(err, 400)

    task = Task(
        title=title,
        description=(data.get('description') or '').strip(),
        priority=priority,
        status=status,
        due_date=due_date,
        start_date=start_date,
        completed_at=completed_at,
        category_id=category_id,
        user_id=assignee_id,
        assignee_id=assignee_id,
        creator_id=current_user.id,
        team_id=team_id,
        organization_id=current_user.organization_id or 1,
        acceptance_criteria=acceptance_criteria,
        progress=progress,
        is_recurring=is_recurring,
        is_personal=is_personal,
        recurrence_interval=recurrence_interval
    )

    db.session.add(task)
    db.session.flush()

    # Create subtasks if provided
    subtasks_data = data.get('subtasks')
    if subtasks_data:
        if isinstance(subtasks_data, str):
            import json
            try:
                subtasks_data = json.loads(subtasks_data)
            except Exception:
                subtasks_data = [s.strip() for s in subtasks_data.split('\n') if s.strip()]
        if isinstance(subtasks_data, list):
            for st_item in subtasks_data:
                st_title = st_item.get('title') if isinstance(st_item, dict) else str(st_item).strip()
                if st_title:
                    db.session.add(SubTask(task_id=task.id, title=st_title))

    # Save uploaded reference files
    if files:
        for f in files:
            fname, fpath, fsize = save_file_safely(f)
            att = TaskAttachment(
                task_id=task.id,
                user_id=current_user.id,
                filename=fname,
                file_path=fpath,
                file_size=fsize,
                content_type=f.content_type,
                attachment_type='reference'
            )
            db.session.add(att)

    # Initial status history record
    db.session.add(TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=None,
        new_status=task.status,
        comment='Task created'
    ))

    db.session.commit()

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
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    task_dict = task.to_dict()
    task_dict['subtasks'] = [st.to_dict() for st in task.subtasks.all()]
    return api_success(task_dict)


# ── Update Task ────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>', methods=['PUT', 'PATCH'])
@login_required
@active_account_required
def update_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return api_error('Task not found.', 404)

    if not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    if not isinstance(data, dict):
        return api_error('A JSON object is required', 400)

    is_manager = can_manage_task(task, current_user)
    is_assigned = (current_user.id in (task.assignee_id, task.user_id))

    if not is_manager and not is_assigned:
        return api_error('Task not found.', 404)

    # Employee security check
    if not is_manager and is_assigned:
        protected_fields = {'title', 'description', 'priority', 'due_date', 'start_date', 'team_id', 'category_id', 'assignee_id', 'assigned_to_id', 'acceptance_criteria'}
        if any(k in data for k in protected_fields):
            return api_error('Employees cannot modify protected task details', 403)
        if data.get('status') == 'completed':
            return api_error('Employees cannot mark tasks as completed directly; submit work for review.', 403)

    if current_user.role == 'employee':
        if 'assignee_id' in data and data['assignee_id'] and int(data['assignee_id']) != current_user.id:
            return api_error('Employees cannot assign tasks to other employees', 403)
        if 'assigned_to_id' in data and data['assigned_to_id'] and int(data['assigned_to_id']) != current_user.id:
            return api_error('Employees cannot assign tasks to other employees', 403)
        if 'team_id' in data and data['team_id']:
            return api_error('Employees cannot assign tasks to teams', 403)

    old_status = task.status
    if 'status' in data:
        status = (data.get('status') or '').strip().lower()
        if status not in VALID_UPDATE_STATUSES:
            return api_error(f"Invalid status: status must be one of: {', '.join(sorted(VALID_UPDATE_STATUSES))}", 400)
        task.status = status
        if status == 'completed':
            task.completed_at = utc_now()
            task.progress = 100
        else:
            task.completed_at = None

    if 'progress' in data:
        try:
            task.progress = min(100, max(0, int(data['progress'])))
            if task.progress == 100 and task.status != 'completed' and is_manager:
                task.status = 'completed'
                task.completed_at = utc_now()
        except (ValueError, TypeError):
            pass

    if is_manager:
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

        if 'assignee_id' in data:
            new_assignee_id = data.get('assignee_id')
            if new_assignee_id:
                try:
                    new_uid = int(new_assignee_id)
                    assignee_user = User.query.get(new_uid)
                    if assignee_user and assignee_user.account_active:
                        task.assignee_id = new_uid
                        task.user_id = new_uid
                except (ValueError, TypeError):
                    pass

        if 'team_id' in data:
            try:
                task.team_id = int(data['team_id']) if data['team_id'] else None
            except (ValueError, TypeError):
                pass

    if task.status != old_status:
        comment_text = data.get('comment') or data.get('reason') or data.get('block_reason') or ('Blocked' if task.status == 'blocked' else 'Status updated')
        db.session.add(TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=task.status,
            comment=comment_text
        ))

        if task.status == 'blocked':
            block_msg = data.get('comment') or data.get('reason') or data.get('block_reason') or 'Task marked as blocked'
            db.session.add(TaskMessage(
                task_id=task.id,
                user_id=current_user.id,
                content=f"[Blocked] {block_msg}"
            ))
            if task.creator_id and task.creator_id != current_user.id:
                send_notification(
                    task.creator_id,
                    f'Task Blocked: "{task.title}"',
                    f"{current_user.full_name or current_user.username} marked '{task.title}' as blocked: {block_msg}",
                    f"/tasks?task_id={task.id}",
                    'task_blocked'
                )

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
    if not task or not can_manage_task(task, current_user):
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
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    is_personal_task = (task.creator_id == current_user.id and task.assignee_id == current_user.id and not task.team_id)
    if not is_personal_task and not can_manage_task(task, current_user):
        return api_error('Employees cannot mark tasks as completed directly; submit work for review.', 403)

    data = request.get_json(silent=True) or {}
    explicit_status = data.get('status')
    old_status = task.status

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

    if task.status != old_status:
        db.session.add(TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=task.status,
            comment='Toggle complete'
        ))

    task.updated_at = utc_now()
    db.session.commit()
    return api_success(task.to_dict(), message='Task status updated')


# ── Submit Work ────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/submit', methods=['POST'])
@login_required
@active_account_required
def submit_task_work(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    notes = (data.get('notes') or data.get('summary') or data.get('message') or '').strip()
    if not notes:
        return api_error('Submission notes/summary are required.', 400)

    files = request.files.getlist('files')
    if files:
        max_files = current_app.config.get('MAX_ATTACHMENTS_PER_MESSAGE', 10)
        if len(files) > max_files:
            return api_error(f'Cannot upload more than {max_files} files in a single message.', 400)
        for f in files:
            err = validate_uploaded_file(f)
            if err:
                return api_error(err, 400)

    sub = WorkSubmission(
        task_id=task.id,
        user_id=current_user.id,
        notes=notes,
        status='submitted'
    )
    db.session.add(sub)
    db.session.flush()

    if files:
        for f in files:
            fname, fpath, fsize = save_file_safely(f)
            att = TaskAttachment(
                task_id=task.id,
                submission_id=sub.id,
                user_id=current_user.id,
                filename=fname,
                file_path=fpath,
                file_size=fsize,
                content_type=f.content_type,
                attachment_type='submission'
            )
            db.session.add(att)

    old_status = task.status
    task.status = STATUS_IN_REVIEW
    task.completed_at = None

    db.session.add(TaskStatusHistory(
        task_id=task.id,
        changed_by_id=current_user.id,
        old_status=old_status,
        new_status=STATUS_IN_REVIEW,
        comment=notes
    ))

    db.session.commit()

    reviewer_id = task.creator_id or task.user_id
    if reviewer_id and reviewer_id != current_user.id:
        send_notification(
            reviewer_id,
            f'Work Submitted for Review: "{task.title}"',
            f"{current_user.full_name or current_user.username} submitted deliverables for your review.",
            f"/tasks?task_id={task.id}",
            'submission_review'
        )

    log_audit('work_submitted', 'Task', task.id, f'Submitted work for task {task.title}')
    return api_success(task.to_dict(), message='Work submitted for review.')


# ── Review Work ────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/review', methods=['POST'])
@login_required
@active_account_required
def review_task_work(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    # Submitter or assignee cannot approve their own work
    sub = task.submissions.order_by(WorkSubmission.created_at.desc()).first()
    is_self = False
    if task.assignee_id and current_user.id == task.assignee_id:
        is_self = True
    elif not task.assignee_id and task.user_id == current_user.id:
        is_self = True
    if sub and sub.user_id == current_user.id:
        is_self = True

    if is_self:
        return api_error('Employees cannot approve their own work.', 403)

    if not can_manage_task(task, current_user):
        return api_error('Permission denied to review task submissions.', 403)

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    action = (data.get('action') or data.get('decision') or '').strip().lower()
    notes = (data.get('notes') or data.get('review_notes') or '').strip()

    if action not in ('approve', 'approved', 'request_changes', 'changes_requested'):
        return api_error("Action must be either 'approve' or 'request_changes'.", 400)

    sub = task.submissions.order_by(WorkSubmission.created_at.desc()).first()
    now = utc_now()
    old_status = task.status

    if action in ('approve', 'approved'):
        task.status = STATUS_COMPLETED
        task.completed_at = now
        task.progress = 100
        if sub:
            sub.status = 'approved'
            sub.reviewed_by = current_user.id
            sub.reviewed_at = now
            sub.review_notes = notes
        db.session.add(TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=STATUS_COMPLETED,
            comment=notes
        ))
    else:
        task.status = STATUS_CHANGES_REQUESTED
        task.completed_at = None
        if sub:
            sub.status = 'changes_requested'
            sub.reviewed_by = current_user.id
            sub.reviewed_at = now
            sub.review_notes = notes
        db.session.add(TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=STATUS_CHANGES_REQUESTED,
            comment=notes
        ))

    db.session.commit()

    if sub and sub.user_id != current_user.id:
        send_notification(
            sub.user_id,
            f'Review decision on "{task.title}"',
            f"Review: {action}. Notes: {notes[:80]}",
            f"/tasks?task_id={task.id}",
            'submission_review'
        )

    log_audit('task_reviewed', 'Task', task.id, f'Review decision: {task.status}')
    return api_success(task.to_dict(), message='Review decision recorded.')


# ── Task Status & Activity History ─────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/history', methods=['GET'])
@login_required
@active_account_required
def get_task_history(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    history = task.status_history.order_by(TaskStatusHistory.created_at.desc()).all()
    return api_success([h.to_dict() for h in history])


# ── Submissions List ───────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/submissions', methods=['GET'])
@login_required
@active_account_required
def get_task_submissions(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    subs = task.submissions.order_by(WorkSubmission.created_at.desc()).all()
    return api_success([s.to_dict() for s in subs])


# ── Comments / Messages ────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/comments', methods=['GET', 'POST'])
@login_required
@active_account_required
def task_comments(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    if request.method == 'GET':
        msgs = TaskMessage.query.filter_by(task_id=task.id).order_by(TaskMessage.created_at.asc()).all()
        return api_success([m.to_dict() for m in msgs])

    # POST comment
    content = (request.form.get('content') or (request.get_json(silent=True) or {}).get('content') or '').strip()
    if not content:
        return api_error('Message content cannot be empty.', 400)
    if len(content) > 5000:
        return api_error('Message must be 5000 characters or fewer.', 400)

    files = request.files.getlist('files')
    if files:
        max_files = current_app.config.get('MAX_ATTACHMENTS_PER_MESSAGE', 10)
        if len(files) > max_files:
            return api_error(f'Cannot upload more than {max_files} files in a single message.', 400)
        for f in files:
            err = validate_uploaded_file(f)
            if err:
                return api_error(err, 400)

    msg = TaskMessage(task_id=task.id, user_id=current_user.id, content=content)
    db.session.add(msg)
    db.session.flush()

    if files:
        for f in files:
            fname, fpath, fsize = save_file_safely(f)
            att = TaskAttachment(
                task_id=task.id,
                message_id=msg.id,
                user_id=current_user.id,
                filename=fname,
                file_path=fpath,
                file_size=fsize,
                content_type=f.content_type,
                attachment_type='message'
            )
            db.session.add(att)

    # Notify other task participants and mentions
    target_users = set()
    if task.assignee_id and task.assignee_id != current_user.id:
        target_users.add(task.assignee_id)
    if task.creator_id and task.creator_id != current_user.id:
        target_users.add(task.creator_id)
    for m in (msg.mentions or []):
        if m.get('id') and m['id'] != current_user.id:
            target_users.add(m['id'])

    commenter_name = current_user.full_name or current_user.username
    snippet = content[:80] + '...' if len(content) > 80 else content
    for uid in target_users:
        send_notification(
            uid,
            f'New Comment on "{task.title}"',
            f'{commenter_name}: {snippet}',
            f'/tasks/{task.id}',
            'task_message'
        )

    db.session.commit()
    log_audit('comment_added', 'Task', task.id, f'Comment posted on task {task.id}')
    return api_success(msg.to_dict(), message='Comment posted.', status_code=201)


# ── Attachments Direct Management ──────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/attachments', methods=['POST'])
@login_required
@active_account_required
def task_attachments_upload(task_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    if not can_manage_task(task, current_user):
        return api_error('Employees cannot upload reference attachments directly.', 403)

    is_single_file = ('file' in request.files and 'files' not in request.files)
    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return api_error('No files provided.', 400)

    for f in files:
        err = validate_uploaded_file(f)
        if err:
            return api_error(err, 400)

    att_type = request.form.get('attachment_type') or 'reference'
    created = []
    for f in files:
        fname, fpath, fsize = save_file_safely(f)
        att = TaskAttachment(
            task_id=task.id,
            user_id=current_user.id,
            filename=fname,
            file_path=fpath,
            file_size=fsize,
            content_type=f.content_type,
            attachment_type=att_type
        )
        db.session.add(att)
        created.append(att)

    db.session.commit()
    if is_single_file and created:
        return api_success(created[0].to_dict(), status_code=201)
    return api_success([a.to_dict() for a in created], status_code=201)


@tasks_bp.route('/<int:task_id>/attachments/<int:file_id>/download', methods=['GET'])
@login_required
@active_account_required
def download_task_attachment(task_id, file_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    att = TaskAttachment.query.filter_by(id=file_id, task_id=task.id).first()
    if not att or not os.path.isfile(att.file_path):
        return api_error('File not found.', 404)

    res = send_file(
        att.file_path,
        as_attachment=True,
        download_name=att.filename,
        mimetype=att.file_type
    )
    res.headers['X-Content-Type-Options'] = 'nosniff'
    return res


@tasks_bp.route('/<int:task_id>/attachments/<int:file_id>/preview', methods=['GET'])
@login_required
@active_account_required
def preview_task_attachment(task_id, file_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    att = TaskAttachment.query.filter_by(id=file_id, task_id=task.id).first()
    if not att or not os.path.isfile(att.file_path):
        return api_error('File not found.', 404)

    res = send_file(
        att.file_path,
        as_attachment=False,
        download_name=att.filename,
        mimetype=att.file_type
    )
    res.headers['Content-Disposition'] = f'inline; filename="{att.filename}"'
    res.headers['X-Content-Type-Options'] = 'nosniff'
    res.headers['Content-Security-Policy'] = 'sandbox allow-scripts'
    return res


@tasks_bp.route('/<int:task_id>/attachments/<int:file_id>', methods=['DELETE'])
@login_required
@active_account_required
def delete_task_attachment(task_id, file_id):
    task = db.session.get(Task, task_id)
    if not task or not can_view_task(task, current_user):
        return api_error('Task not found.', 404)

    att = TaskAttachment.query.filter_by(id=file_id, task_id=task.id).first()
    if not att:
        return api_error('Attachment not found.', 404)

    if att.user_id != current_user.id and not can_manage_task(task, current_user):
        return api_error('Unauthorized to delete this attachment.', 403)

    try:
        if os.path.isfile(att.file_path):
            os.remove(att.file_path)
    except OSError:
        pass

    db.session.delete(att)
    db.session.commit()
    log_audit('attachment_deleted', 'Task', task.id, f'Deleted attachment {att.filename}')
    return api_success(message='Attachment deleted.')


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
    today = date.today()
    recurring_tasks = Task.query.filter(
        Task.is_recurring == True,
        Task.status == 'completed'
    ).all()

    created_count = 0
    for t in recurring_tasks:
        interval = t.recurrence_interval or 'weekly'
        next_due = None
        if t.due_date:
            if interval == 'daily':
                next_due = t.due_date + timedelta(days=1)
            elif interval == 'monthly':
                next_due = t.due_date + timedelta(days=30)
            else:
                next_due = t.due_date + timedelta(days=7)

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
        t.is_recurring = False
        db.session.add(next_task)
        created_count += 1

    db.session.commit()
    return api_success({'spawned_count': created_count}, message=f'Spawned {created_count} recurring tasks.')
