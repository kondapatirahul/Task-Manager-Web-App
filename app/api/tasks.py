"""
Task REST API Blueprint (M4).

Endpoints implemented:
- GET    /api/tasks
- POST   /api/tasks
- GET    /api/tasks/<int:task_id>
- PUT    /api/tasks/<int:task_id>
- DELETE /api/tasks/<int:task_id>
- PATCH  /api/tasks/<int:task_id>/complete

Team JSON response contract:
- Success: {"ok": true, "data": {...}}
- Error:   {"ok": false, "error": "message"}

Integration Dependencies (Pending M1, M2, M3):
----------------------------------------------
This module defines clear integration hooks for:
1. M1: Database extension (`db`) and blueprint registration in application factory.
2. M2: Models (`Task`, `Category`).
3. M3: Authentication / Current User context (`current_user` or auth decorator).

When M1, M2, and M3 provide their modules, wire them up via `configure_task_api_dependencies()`
or through standard imports once paths are established.
"""

from datetime import date, datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional
from flask import Blueprint, jsonify, request, g

from app.api.validators import validate_task_payload

tasks_bp = Blueprint("tasks_api", __name__, url_prefix="/api/tasks")


class TaskApiDependencies:
    """
    Registry for external dependencies provided by M1, M2, and M3.
    Decouples M4 API logic until teammate branches are merged.
    """
    db: Any = None
    Task: Any = None
    Category: Any = None
    get_current_user: Optional[Callable[[], Any]] = None
    auth_decorator: Optional[Callable[[Callable], Callable]] = None


def configure_task_api_dependencies(
    db: Any = None,
    Task: Any = None,
    Category: Any = None,
    get_current_user: Optional[Callable[[], Any]] = None,
    auth_decorator: Optional[Callable[[Callable], Callable]] = None,
) -> None:
    """
    Configuration hook called during application factory setup (M1)
    or test setup to inject database, models, and auth providers.
    """
    if db is not None:
        TaskApiDependencies.db = db
    if Task is not None:
        TaskApiDependencies.Task = Task
    if Category is not None:
        TaskApiDependencies.Category = Category
    if get_current_user is not None:
        TaskApiDependencies.get_current_user = get_current_user
    if auth_decorator is not None:
        TaskApiDependencies.auth_decorator = auth_decorator


def get_db() -> Any:
    """
    Retrieve database extension instance.
    Falls back to common application factory import paths if available.
    """
    if TaskApiDependencies.db is not None:
        return TaskApiDependencies.db

    try:
        from app.extensions import db
        return db
    except ImportError:
        pass

    try:
        from app import db
        return db
    except ImportError:
        pass

    raise RuntimeError(
        "M1 Database extension 'db' is not available. "
        "Please connect M1's db via configure_task_api_dependencies(db=...)"
    )


def get_task_model() -> Any:
    """
    Retrieve Task model.
    Falls back to common model import paths if available.
    """
    if TaskApiDependencies.Task is not None:
        return TaskApiDependencies.Task

    try:
        from app.models import Task
        return Task
    except ImportError:
        pass

    try:
        from app.models.task import Task
        return Task
    except ImportError:
        pass

    raise RuntimeError(
        "M2 'Task' model is not available. "
        "Please connect M2's Task model via configure_task_api_dependencies(Task=...)"
    )


def get_category_model() -> Any:
    """
    Retrieve Category model.
    Falls back to common model import paths if available.
    """
    if TaskApiDependencies.Category is not None:
        return TaskApiDependencies.Category

    try:
        from app.models import Category
        return Category
    except ImportError:
        pass

    try:
        from app.models.category import Category
        return Category
    except ImportError:
        pass

    raise RuntimeError(
        "M2 'Category' model is not available. "
        "Please connect M2's Category model via configure_task_api_dependencies(Category=...)"
    )


def resolve_current_user() -> Any:
    """
    Resolve the authenticated user for the current request.
    Integrates with M3's Flask-Login or injected auth provider.
    """
    if TaskApiDependencies.get_current_user is not None:
        return TaskApiDependencies.get_current_user()

    try:
        from flask_login import current_user
        if current_user and getattr(current_user, "is_authenticated", False):
            return current_user
    except ImportError:
        pass

    if hasattr(g, "user") and g.user is not None:
        return g.user

    return None


def api_auth_required(f: Callable) -> Callable:
    """
    Authentication wrapper for M4 endpoints.
    Returns JSON 401 response for unauthenticated requests:
    {"ok": false, "error": "Authentication required"}
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if TaskApiDependencies.auth_decorator is not None:
            return TaskApiDependencies.auth_decorator(f)(*args, **kwargs)

        user = resolve_current_user()
        if not user or not getattr(user, "is_authenticated", True):
            return jsonify({"ok": False, "error": "Authentication required"}), 401

        # Confirm user has a valid identifier
        user_id = getattr(user, "id", None)
        if user_id is None:
            return jsonify({"ok": False, "error": "Authentication required"}), 401

        return f(*args, **kwargs)

    return decorated


def serialize_task(task: Any) -> Dict[str, Any]:
    """
    Serialize Task instance to dict matching shared API contract.
    Uses task.to_dict() if defined by M2, otherwise falls back to standard model attributes.
    """
    if hasattr(task, "to_dict") and callable(task.to_dict):
        return task.to_dict()

    due_date_val = getattr(task, "due_date", None)
    if isinstance(due_date_val, (date, datetime)):
        due_date_str = due_date_val.isoformat()
    elif due_date_val:
        due_date_str = str(due_date_val)
    else:
        due_date_str = None

    created_at_val = getattr(task, "created_at", None)
    created_at_str = created_at_val.isoformat() if isinstance(created_at_val, (date, datetime)) else None

    updated_at_val = getattr(task, "updated_at", None)
    updated_at_str = updated_at_val.isoformat() if isinstance(updated_at_val, (date, datetime)) else None

    return {
        "id": task.id,
        "title": task.title,
        "description": getattr(task, "description", None),
        "status": task.status,
        "priority": task.priority,
        "due_date": due_date_str,
        "category_id": getattr(task, "category_id", None),
        "user_id": task.user_id,
        "created_at": created_at_str,
        "updated_at": updated_at_str,
    }


# ============================================================================
# API Routes
# ============================================================================

@tasks_bp.route("", methods=["GET"])
@tasks_bp.route("/", methods=["GET"])
@api_auth_required
def list_tasks() -> Any:
    """
    GET /api/tasks
    Retrieve all tasks owned by the authenticated user.
    """
    user = resolve_current_user()
    Task = get_task_model()

    # Scoped to authenticated user; safe SQLAlchemy query construction
    query = Task.query.filter_by(user_id=user.id)
    if hasattr(Task, "id") and hasattr(Task.id, "desc"):
        query = query.order_by(Task.id.desc())
    tasks = query.all()
    data = [serialize_task(task) for task in tasks]
    return jsonify({"ok": True, "data": data}), 200


@tasks_bp.route("", methods=["POST"])
@tasks_bp.route("/", methods=["POST"])
@api_auth_required
def create_task() -> Any:
    """
    POST /api/tasks
    Create a new task for the authenticated user.
    """
    user = resolve_current_user()

    if not request.is_json:
        return jsonify({"ok": False, "error": "Request body must be JSON"}), 400

    payload = request.get_json(silent=True)
    is_valid, err_msg, cleaned = validate_task_payload(payload, is_partial=False)
    if not is_valid:
        return jsonify({"ok": False, "error": err_msg}), 400

    db = get_db()
    Task = get_task_model()
    Category = get_category_model()

    category_id = cleaned.get("category_id")
    if category_id is not None:
        # Verify category exists and belongs to the authenticated user
        category = Category.query.filter_by(id=category_id, user_id=user.id).first()
        if not category:
            return jsonify({"ok": False, "error": "Invalid category or access denied"}), 400

    task = Task(
        title=cleaned["title"],
        description=cleaned.get("description"),
        status=cleaned.get("status", "pending"),
        priority=cleaned.get("priority", "medium"),
        due_date=cleaned.get("due_date"),
        category_id=category_id,
        user_id=user.id,
    )
    db.session.add(task)
    db.session.commit()

    return jsonify({"ok": True, "data": serialize_task(task)}), 201


@tasks_bp.route("/<int:task_id>", methods=["GET"])
@api_auth_required
def get_task(task_id: int) -> Any:
    """
    GET /api/tasks/<int:task_id>
    Retrieve a specific task owned by the authenticated user.
    Returns 404 for nonexistent tasks or tasks belonging to another user.
    """
    user = resolve_current_user()
    Task = get_task_model()

    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404

    return jsonify({"ok": True, "data": serialize_task(task)}), 200


@tasks_bp.route("/<int:task_id>", methods=["PUT"])
@api_auth_required
def update_task(task_id: int) -> Any:
    """
    PUT /api/tasks/<int:task_id>
    Update an existing task owned by the authenticated user.
    Returns 404 for nonexistent tasks or tasks belonging to another user.
    """
    user = resolve_current_user()

    if not request.is_json:
        return jsonify({"ok": False, "error": "Request body must be JSON"}), 400

    payload = request.get_json(silent=True)
    is_valid, err_msg, cleaned = validate_task_payload(payload, is_partial=False)
    if not is_valid:
        return jsonify({"ok": False, "error": err_msg}), 400

    db = get_db()
    Task = get_task_model()
    Category = get_category_model()

    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404

    category_id = cleaned.get("category_id")
    if category_id is not None:
        category = Category.query.filter_by(id=category_id, user_id=user.id).first()
        if not category:
            return jsonify({"ok": False, "error": "Invalid category or access denied"}), 400

    task.title = cleaned["title"]
    task.description = cleaned.get("description")
    task.status = cleaned.get("status", "pending")
    task.priority = cleaned.get("priority", "medium")
    task.due_date = cleaned.get("due_date")
    task.category_id = category_id

    db.session.commit()
    return jsonify({"ok": True, "data": serialize_task(task)}), 200


@tasks_bp.route("/<int:task_id>", methods=["DELETE"])
@api_auth_required
def delete_task(task_id: int) -> Any:
    """
    DELETE /api/tasks/<int:task_id>
    Delete an existing task owned by the authenticated user.
    Returns 404 for nonexistent tasks or tasks belonging to another user.
    """
    user = resolve_current_user()
    db = get_db()
    Task = get_task_model()

    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404

    db.session.delete(task)
    db.session.commit()
    return jsonify({"ok": True, "data": {"id": task_id, "message": "Task deleted successfully"}}), 200


@tasks_bp.route("/<int:task_id>/complete", methods=["PATCH"])
@api_auth_required
def complete_task(task_id: int) -> Any:
    """
    PATCH /api/tasks/<int:task_id>/complete
    Mark a task owned by the authenticated user as completed.
    Returns 404 for nonexistent tasks or tasks belonging to another user.
    """
    user = resolve_current_user()
    db = get_db()
    Task = get_task_model()

    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404

    task.status = "completed"
    db.session.commit()
    return jsonify({"ok": True, "data": serialize_task(task)}), 200
