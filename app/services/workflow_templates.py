"""Authorization, validation, and task generation for workflow templates."""

import json
from datetime import date, timedelta

from app import db
from app.models import (
    Task,
    TaskDependency,
    TaskStatusHistory,
    User,
    WorkflowTemplate,
    WorkflowTemplateTask,
    STATUS_PENDING,
)

VALID_PRIORITIES = {'low', 'medium', 'high'}
VALID_VISIBILITY = {'private', 'organization'}
MAX_CHECKLIST_ITEMS = 50


def can_view_template(user, template):
    if not template or not user.is_authenticated:
        return False
    if user.role == 'super_admin' or template.owner_id == user.id:
        return True
    return (
        template.visibility == 'organization'
        and template.organization_id is not None
        and template.organization_id == user.organization_id
    )


def can_manage_template(user, template):
    if not can_view_template(user, template):
        return False
    if template.owner_id == user.id or user.role == 'super_admin':
        return True
    return user.role in {'admin', 'hr'} and (
        user.organization_id is None
        or template.organization_id == user.organization_id
    )


def can_create_shared(user):
    return user.role in {'super_admin', 'admin', 'hr', 'team_lead'}


def validate_checklist(value):
    if not isinstance(value, list) or not value or len(value) > MAX_CHECKLIST_ITEMS:
        return None, f'checklist must contain 1 to {MAX_CHECKLIST_ITEMS} items.'
    cleaned = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            return None, f'Checklist item {index + 1} must be an object.'
        title = str(item.get('title') or '').strip()
        if not title or len(title) > 200:
            return None, f'Checklist item {index + 1} needs a title of 1 to 200 characters.'
        description = str(item.get('description') or '').strip()
        if len(description) > 5000:
            return None, f'Checklist item {index + 1} description is too long.'
        raw_offset = item.get('due_offset_days')
        try:
            offset = int(raw_offset) if raw_offset not in (None, '') else None
        except (TypeError, ValueError):
            return None, f'Checklist item {index + 1} due_offset_days must be an integer.'
        if offset is not None and not -3650 <= offset <= 3650:
            return None, f'Checklist item {index + 1} due_offset_days is out of range.'
        raw_effort = item.get('estimated_effort_hours')
        try:
            effort = float(raw_effort) if raw_effort not in (None, '') else None
        except (TypeError, ValueError):
            return None, f'Checklist item {index + 1} estimated effort must be a number.'
        if effort is not None and not 0 <= effort <= 10000:
            return None, f'Checklist item {index + 1} estimated effort is out of range.'
        cleaned.append({
            'title': title,
            'description': description,
            'due_offset_days': offset,
            'estimated_effort_hours': effort,
        })
    return cleaned, None


def serialize_template(template, include_generated=False, viewer=None):
    data = {
        'id': template.id,
        'owner_id': template.owner_id,
        'owner_name': (
            template.owner.full_name or template.owner.username
        ) if template.owner else None,
        'organization_id': template.organization_id,
        'name': template.name,
        'description': template.description or '',
        'checklist': template.checklist,
        'default_priority': template.default_priority,
        'visibility': template.visibility,
        'is_archived': bool(template.is_archived),
        'created_at': template.created_at.isoformat() if template.created_at else None,
        'updated_at': template.updated_at.isoformat() if template.updated_at else None,
        'can_edit': can_manage_template(viewer, template) if viewer else False,
    }
    if include_generated:
        data['generated_tasks'] = [
            {
                'task_id': link.task_id,
                'item_index': link.item_index,
                'title': link.task.title if link.task else None,
                'status': link.task.status if link.task else None,
            }
            for link in template.generated_tasks.order_by(WorkflowTemplateTask.item_index.asc()).all()
        ]
    return data


def instantiate_template(user, template, base_due_date=None):
    if not can_view_template(user, template) or template.is_archived:
        return None, 'Template is not available.', 404
    if base_due_date is not None and not isinstance(base_due_date, date):
        return None, 'base_due_date must be a valid date.', 400
    created = []
    previous = None
    try:
        for index, item in enumerate(template.checklist):
            due_date = (
                base_due_date + timedelta(days=item['due_offset_days'])
                if base_due_date is not None and item.get('due_offset_days') is not None
                else None
            )
            task = Task(
                title=item['title'],
                description=item.get('description') or template.description or '',
                status=STATUS_PENDING,
                priority=template.default_priority,
                due_date=due_date,
                estimated_effort_hours=item.get('estimated_effort_hours'),
                user_id=user.id,
            )
            db.session.add(task)
            db.session.flush()
            db.session.add(TaskStatusHistory(
                task_id=task.id,
                changed_by_id=user.id,
                old_status=None,
                new_status=STATUS_PENDING,
                comment=f'Created from workflow template: {template.name}',
            ))
            db.session.add(WorkflowTemplateTask(
                template_id=template.id,
                task_id=task.id,
                item_index=index,
            ))
            if previous is not None:
                db.session.add(TaskDependency(
                    blocked_task_id=task.id,
                    blocking_task_id=previous.id,
                    created_by_id=user.id,
                ))
            previous = task
            created.append(task)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return created, None, 201
