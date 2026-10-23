"""Task handover authorization, validation, and serialization."""

from datetime import datetime, timezone

from app import db
from app.models import (
    Task,
    TaskAttachment,
    TaskHandover,
    TaskHandoverAttachment,
    User,
    STATUS_COMPLETED,
    team_members,
)
from app.services.dependencies import dependency_state
from app.services.workload import authorized_task_query

HANDOVER_PENDING = 'pending'
HANDOVER_ACCEPTED = 'accepted'
HANDOVER_DECLINED = 'declined'
HANDOVER_CANCELLED = 'cancelled'
HANDOVER_EXPIRED = 'expired'
TERMINAL_HANDOVER_STATUSES = {
    HANDOVER_ACCEPTED,
    HANDOVER_DECLINED,
    HANDOVER_CANCELLED,
    HANDOVER_EXPIRED,
}


def task_can_be_viewed(user, task):
    from app.routes.tasks import can_user_view_task
    return bool(task and can_user_view_task(user, task))


def task_can_be_managed(user, task):
    from app.routes.tasks import can_user_manage_task
    return bool(task and can_user_manage_task(user, task))


def eligible_new_owner_ids(user, task):
    if user.role == 'super_admin':
        query = User.query.filter(User.role == 'employee')
    elif user.role == 'admin':
        query = User.query.filter(
            User.role == 'employee',
            User.organization_id == user.organization_id,
        )
    elif user.role == 'team_lead':
        from app.routes.tasks import get_permitted_assignee_ids_for_user
        permitted = get_permitted_assignee_ids_for_user(user, task.team_id)
        query = User.query.filter(User.id.in_(permitted or []), User.role == 'employee')
    else:
        query = User.query.filter(User.role == 'employee')
        if user.organization_id is not None:
            query = query.filter(User.organization_id == user.organization_id)
    query = query.filter(User.account_active.is_(True), User.id != task.assigned_to_id)
    if task.team_id:
        member_ids = db.session.query(team_members.c.user_id).filter(
            team_members.c.team_id == task.team_id
        )
        query = query.filter(User.id.in_(member_ids))
    return {row[0] for row in query.with_entities(User.id).all()}


def can_initiate_handover(user, task):
    if not task_can_be_viewed(user, task) or not task.assigned_to_id:
        return False
    return task.assigned_to_id == user.id or task_can_be_managed(user, task)


def pending_handover(task_id):
    return TaskHandover.query.filter_by(
        task_id=task_id, status=HANDOVER_PENDING
    ).first()


def serialize_handover(handover, viewer):
    state = dependency_state(handover.task, viewer)

    def user_payload(user):
        return {
            'id': user.id,
            'name': user.full_name or user.username,
            'email': user.email,
        } if user else None

    return {
        'id': handover.id,
        'task_id': handover.task_id,
        'previous_owner': user_payload(handover.previous_owner),
        'new_owner': user_payload(handover.new_owner),
        'initiated_by': user_payload(handover.initiated_by),
        'resolved_by': user_payload(handover.resolved_by),
        'reason': handover.reason,
        'current_progress': handover.current_progress,
        'next_steps': handover.next_steps,
        'resolution_reason': handover.resolution_reason or '',
        'status': handover.status,
        'acknowledged_at': handover.acknowledged_at.isoformat() if handover.acknowledged_at else None,
        'created_at': handover.created_at.isoformat() if handover.created_at else None,
        'updated_at': handover.updated_at.isoformat() if handover.updated_at else None,
        'blockers': state['blocked_by'],
        'attachments': [
            item.attachment.to_dict()
            for item in handover.attachments.all()
            if item.attachment
        ],
    }


def expire_stale_handover(handover, reason):
    handover.status = HANDOVER_EXPIRED
    handover.resolution_reason = reason
    handover.resolved_by_id = None
    handover.acknowledged_at = datetime.now(timezone.utc)


def validate_handover_attachments(task_id, attachment_ids):
    if not attachment_ids:
        return []
    try:
        ids = {int(value) for value in attachment_ids}
    except (TypeError, ValueError):
        return None
    attachments = TaskAttachment.query.filter(
        TaskAttachment.id.in_(ids),
        TaskAttachment.task_id == task_id,
    ).all()
    if len(attachments) != len(ids):
        return None
    return attachments


def authorized_task_for_user(user, task_id):
    return authorized_task_query(user).filter(Task.id == task_id).first()
