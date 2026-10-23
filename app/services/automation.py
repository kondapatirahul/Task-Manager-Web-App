"""Controlled, idempotent workflow automation.

This module is intentionally invoked by an explicit runner. The application
does not start a background scheduler, so production must invoke the runner
from cron, a platform job, or another approved scheduler.
"""

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (
    AutomationExecution,
    AutomationRule,
    Notification,
    Task,
    TaskStatusHistory,
    User,
    STATUS_PENDING,
)
from app.services.notifications import notify_task_collaboration_event
from app.services.workflow_templates import can_view_template, instantiate_template
from app.routes.tasks import can_user_manage_task

VALID_RULE_TYPES = {'overdue_notification', 'recurring_task'}
VALID_SCHEDULES = {'daily', 'weekly', 'monthly'}


def now_utc():
    return datetime.now(timezone.utc)


def next_run(value, schedule):
    if schedule == 'daily':
        return value + timedelta(days=1)
    if schedule == 'weekly':
        return value + timedelta(days=7)
    if schedule == 'monthly':
        month = value.month % 12 + 1
        year = value.year + (1 if value.month == 12 else 0)
        day = min(value.day, 28)
        return value.replace(year=year, month=month, day=day)
    raise ValueError('Unsupported recurrence schedule.')


def rule_visible_to(user, rule):
    return bool(
        rule and (
            user.role == 'super_admin'
            or rule.owner_id == user.id
            or (
                rule.organization_id is not None
                and rule.organization_id == user.organization_id
                and user.role in {'admin', 'hr', 'team_lead'}
            )
        )
    )


def rule_manageable_by(user, rule):
    return bool(
        rule_visible_to(user, rule)
        and (
            user.role == 'super_admin'
            or rule.owner_id == user.id
            or user.role in {'admin', 'hr'}
        )
    )


def create_execution(rule, key):
    execution = AutomationExecution(
        rule_id=rule.id,
        execution_key=key,
        status='running',
        started_at=now_utc(),
    )
    db.session.add(execution)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return None
    return execution


def finish_execution(execution, status, result=None, error=None):
    execution.status = status
    execution.completed_at = now_utc()
    execution.result_json = json.dumps(result or {})
    execution.error_message = error


def process_overdue(today=None):
    today = today or date.today()
    created = 0
    tasks = Task.query.filter(
        Task.status != 'completed',
        Task.due_date.isnot(None),
        Task.due_date < today,
    ).all()
    for task in tasks:
        recipient_ids = {item for item in (task.assigned_to_id, task.user_id) if item}
        recipient_ids = {
            row[0] for row in User.query.filter(
                User.id.in_(recipient_ids),
                User.account_active.is_(True),
            ).with_entities(User.id).all()
        }
        key = f'overdue:{task.id}:{task.due_date.isoformat()}'
        delivered = {
            row[0] for row in Notification.query.filter(
                Notification.event_key.like(f'{key}:user:%')
            ).with_entities(Notification.recipient_id).all()
        }
        recipient_ids -= delivered
        if not recipient_ids:
            continue
        notify_task_collaboration_event(
            'task_overdue',
            task,
            recipients=recipient_ids,
            metadata={
                'event_key': key,
                'message': f'"{task.title}" is overdue.',
                'description': f'Overdue task notification for "{task.title}".',
            },
            event_key=key,
        )
        created += 1
    return created


def run_recurring_rules(at=None):
    at = at or now_utc()
    generated = 0
    rules = AutomationRule.query.filter(
        AutomationRule.rule_type == 'recurring_task',
        AutomationRule.enabled.is_(True),
        AutomationRule.next_run_at.isnot(None),
        AutomationRule.next_run_at <= at,
    ).all()
    for rule in rules:
        if not rule.owner or not rule.owner.account_active:
            rule.enabled = False
            db.session.commit()
            continue
        key = f'recurrence:{rule.id}:{rule.next_run_at.isoformat()}'
        execution = create_execution(rule, key)
        if execution is None:
            continue
        try:
            if rule.template_id and rule.template and can_view_template(rule.owner, rule.template):
                created, error, status = instantiate_template(rule.owner, rule.template)
                if error:
                    raise ValueError(error)
            elif rule.source_task and can_user_manage_task(rule.owner, rule.source_task):
                source = rule.source_task
                task = Task(
                    title=source.title,
                    description=source.description,
                    status=STATUS_PENDING,
                    priority=source.priority,
                    estimated_effort_hours=source.estimated_effort_hours,
                    due_date=source.due_date,
                    start_date=source.start_date,
                    category_id=source.category_id,
                    team_id=source.team_id,
                    assigned_to_id=source.assigned_to_id,
                    user_id=rule.owner_id,
                )
                db.session.add(task)
                db.session.flush()
                db.session.add(TaskStatusHistory(
                    task_id=task.id,
                    changed_by_id=rule.owner_id,
                    old_status=None,
                    new_status=STATUS_PENDING,
                    comment=f'Created by recurring rule: {rule.name}',
                ))
                created = [task]
            else:
                raise ValueError('Recurring rule has no valid source task or template.')
            rule.next_run_at = next_run(rule.next_run_at, rule.schedule)
            finish_execution(execution, 'succeeded', {'task_ids': [task.id for task in created]})
            db.session.commit()
            generated += len(created)
        except Exception as error:
            db.session.rollback()
            execution = create_execution(rule, f'{key}:failure')
            if execution:
                finish_execution(execution, 'failed', error=str(error))
                db.session.commit()
    return generated


def run_automation(at=None):
    return {
        'overdue_notifications': process_overdue(),
        'recurring_tasks': run_recurring_rules(at),
    }
