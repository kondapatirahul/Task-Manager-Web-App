"""Task dependency validation, authorization, and graph operations."""

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Task, TaskDependency, User, STATUS_COMPLETED
from app.services.workload import authorized_task_query


def task_is_authorized(user, task_id):
    return authorized_task_query(user).filter(Task.id == task_id).first()


def can_manage_dependency_task(user, task):
    if not task or not task_is_authorized(user, task.id):
        return False
    if user.role in ('super_admin', 'admin'):
        return True
    if user.role == 'team_lead':
        from app.routes.tasks import can_user_manage_task
        return can_user_manage_task(user, task)
    return task.user_id == user.id


def dependency_payload(dependency):
    from app.models import dependency_to_dict
    return {
        'id': dependency.id,
        'blocked_task': dependency_to_dict(dependency, dependency.blocked_task),
        'blocking_task': dependency_to_dict(dependency, dependency.blocking_task),
        'is_cleared': dependency.blocking_task.status == STATUS_COMPLETED,
    }


def dependency_state(task, user=None):
    dependencies = TaskDependency.query.filter_by(blocked_task_id=task.id).all()
    blocked_dependencies = TaskDependency.query.filter_by(blocking_task_id=task.id).all()
    if user is not None:
        dependencies = [
            item for item in dependencies
            if task_is_authorized(user, item.blocking_task_id)
        ]
        blocked_dependencies = [
            item for item in blocked_dependencies
            if task_is_authorized(user, item.blocked_task_id)
        ]
    return {
        'blocked_by': [dependency_payload(item)['blocking_task'] for item in dependencies],
        'blocks': [
            dependency_payload(item)['blocked_task']
            for item in blocked_dependencies
        ],
        'is_blocked': any(
            item.blocking_task.status != STATUS_COMPLETED for item in dependencies
        ),
        'all_blockers_completed': bool(dependencies) and all(
            item.blocking_task.status == STATUS_COMPLETED for item in dependencies
        ),
    }


def notify_dependency_status_change(task, old_status, actor):
    """Notify dependent task owners when a blocker clears or reopens."""
    was_completed = old_status == STATUS_COMPLETED
    is_completed = task.status == STATUS_COMPLETED
    if was_completed == is_completed:
        return

    dependent_dependencies = TaskDependency.query.filter_by(
        blocking_task_id=task.id
    ).all()
    for dependency in dependent_dependencies:
        dependent_task = dependency.blocked_task
        if not dependent_task:
            continue
        if is_completed:
            remaining = TaskDependency.query.filter(
                TaskDependency.blocked_task_id == dependent_task.id,
                TaskDependency.blocking_task_id != task.id,
            ).all()
            if any(item.blocking_task and item.blocking_task.status != STATUS_COMPLETED for item in remaining):
                continue
            event_type = 'dependency_cleared'
            description = (
                f'"{task.title}" completed; "{dependent_task.title}" may now proceed.'
            )
        else:
            event_type = 'dependency_reopened'
            description = (
                f'"{task.title}" was reopened; "{dependent_task.title}" is blocked again.'
            )
        recipient_ids = {
            user_id for user_id in (dependent_task.user_id, dependent_task.assigned_to_id)
            if user_id
        }
        active_ids = {
            row[0] for row in User.query.filter(
                User.id.in_(recipient_ids),
                User.account_active.is_(True),
            ).with_entities(User.id).all()
        }
        from app.services.notifications import notify_task_collaboration_event
        notify_task_collaboration_event(
            event_type,
            dependent_task,
            actor,
            recipients=active_ids,
            metadata={
                'description': description,
                'message': description,
                'event_id': f'dependency-state:{dependency.id}:{task.updated_at.isoformat()}:{event_type}',
            },
        )


def would_create_cycle(blocked_task_id, blocking_task_id):
    pending = [blocking_task_id]
    visited = set()
    while pending:
        current_id = pending.pop()
        if current_id == blocked_task_id:
            return True
        if current_id in visited:
            continue
        visited.add(current_id)
        pending.extend(
            row.blocking_task_id
            for row in TaskDependency.query.filter_by(blocked_task_id=current_id).all()
        )
    return False


def create_dependency(user, blocked_task, blocking_task):
    if not can_manage_dependency_task(user, blocked_task) or not can_manage_dependency_task(user, blocking_task):
        return None, 'Task is outside your authorized scope.', 404
    if blocked_task.id == blocking_task.id:
        return None, 'A task cannot depend on itself.', 400
    if TaskDependency.query.filter_by(
        blocked_task_id=blocked_task.id,
        blocking_task_id=blocking_task.id,
    ).first():
        return None, 'This dependency already exists.', 409
    if would_create_cycle(blocked_task.id, blocking_task.id):
        return None, 'This dependency would create a circular dependency.', 409
    dependency = TaskDependency(
        blocked_task_id=blocked_task.id,
        blocking_task_id=blocking_task.id,
        created_by_id=user.id,
    )
    db.session.add(dependency)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return None, 'This dependency already exists.', 409
    return dependency, None, 201


def remove_dependency(user, blocked_task, blocking_task_id):
    if not can_manage_dependency_task(user, blocked_task):
        return None, 'Task is outside your authorized scope.', 404
    dependency = TaskDependency.query.filter_by(
        blocked_task_id=blocked_task.id,
        blocking_task_id=blocking_task_id,
    ).first()
    if not dependency:
        return None, 'Dependency not found.', 404
    if not can_manage_dependency_task(user, dependency.blocking_task):
        return None, 'Task is outside your authorized scope.', 404
    db.session.delete(dependency)
    db.session.commit()
    return dependency, None, 200
