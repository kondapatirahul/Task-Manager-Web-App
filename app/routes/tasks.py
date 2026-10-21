from datetime import datetime, date, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_, desc, asc, case
from app import db
from app.models import Task, Category
from app.routes.utils import api_success, api_error

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')

VALID_PRIORITIES = {'low', 'medium', 'high'}
VALID_STATUSES = {'pending', 'completed'}

def parse_date(date_str):
    if not date_str:
        return None
    try:
        if isinstance(date_str, date):
            return date_str
        # Strip time part if present (e.g. 2026-10-21T00:00:00)
        clean_str = date_str.split('T')[0].strip()
        return datetime.strptime(clean_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None

@tasks_bp.route('', methods=['GET'])
@login_required
def get_tasks():
    query = Task.query.filter_by(user_id=current_user.id)

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

    # Filter by status
    status = (request.args.get('status') or '').strip().lower()
    if status in VALID_STATUSES:
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
        # Put null due dates at the end
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
    else:  # default created_at_desc
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
        return api_error(f"Priority must be one of: {', '.join(VALID_PRIORITIES)}", 400)

    status = (data.get('status') or 'pending').strip().lower()
    if status not in VALID_STATUSES:
        return api_error(f"Status must be one of: {', '.join(VALID_STATUSES)}", 400)

    category_id = data.get('category_id')
    if category_id:
        try:
            category_id = int(category_id)
            cat = Category.query.filter_by(id=category_id, user_id=current_user.id).first()
            if not cat:
                return api_error('Category not found or does not belong to you.', 404)
        except (ValueError, TypeError):
            category_id = None
    else:
        category_id = None

    due_date = parse_date(data.get('due_date'))
    completed_at = datetime.now(timezone.utc) if status == 'completed' else None

    task = Task(
        title=title,
        description=(data.get('description') or '').strip(),
        priority=priority,
        status=status,
        due_date=due_date,
        completed_at=completed_at,
        category_id=category_id,
        user_id=current_user.id
    )

    db.session.add(task)
    db.session.commit()
    return api_success(task.to_dict(), message='Task created successfully', status_code=201)

@tasks_bp.route('/<int:task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        return api_error('Task not found.', 404)
    return api_success(task.to_dict())

@tasks_bp.route('/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
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
            return api_error(f"Priority must be one of: {', '.join(VALID_PRIORITIES)}", 400)
        task.priority = priority

    if 'status' in data:
        status = (data.get('status') or '').strip().lower()
        if status not in VALID_STATUSES:
            return api_error(f"Status must be one of: {', '.join(VALID_STATUSES)}", 400)
        if status == 'completed' and task.status != 'completed':
            task.completed_at = datetime.now(timezone.utc)
        elif status == 'pending':
            task.completed_at = None
        task.status = status

    if 'due_date' in data:
        raw_due = data.get('due_date')
        task.due_date = parse_date(raw_due) if raw_due else None

    if 'category_id' in data:
        cat_id = data.get('category_id')
        if cat_id:
            try:
                cat_id = int(cat_id)
                cat = Category.query.filter_by(id=cat_id, user_id=current_user.id).first()
                if not cat:
                    return api_error('Category not found.', 404)
                task.category_id = cat_id
            except (ValueError, TypeError):
                task.category_id = None
        else:
            task.category_id = None

    db.session.commit()
    return api_success(task.to_dict(), message='Task updated successfully')

@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        return api_error('Task not found.', 404)

    db.session.delete(task)
    db.session.commit()
    return api_success(message='Task deleted successfully')

@tasks_bp.route('/<int:task_id>/complete', methods=['PATCH'])
@login_required
def toggle_task_complete(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        return api_error('Task not found.', 404)

    data = request.get_json(silent=True) or {}
    explicit_status = data.get('status')

    if explicit_status:
        if explicit_status not in VALID_STATUSES:
            return api_error('Invalid status', 400)
        task.status = explicit_status
        task.completed_at = datetime.now(timezone.utc) if explicit_status == 'completed' else None
    else:
        # Toggle current status
        if task.status == 'completed':
            task.status = 'pending'
            task.completed_at = None
        else:
            task.status = 'completed'
            task.completed_at = datetime.now(timezone.utc)

    db.session.commit()
    return api_success(task.to_dict(), message='Task status updated')
