"""Productivity analytics and personal goal progress."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_

from app import db
from app.models import Goal, Task
from app.services.workload import authorized_task_query

GOAL_TYPES = {'complete_tasks', 'complete_before_deadline', 'reduce_overdue'}


def accessible_tasks(user):
    return authorized_task_query(user)


def parse_period(start_value=None, end_value=None, today=None):
    today = today or date.today()
    if start_value:
        try:
            start = date.fromisoformat(start_value)
        except (TypeError, ValueError):
            raise ValueError('start must be a valid ISO date (YYYY-MM-DD).')
    else:
        start = today - timedelta(days=6)
    if end_value:
        try:
            end = date.fromisoformat(end_value)
        except (TypeError, ValueError):
            raise ValueError('end must be a valid ISO date (YYYY-MM-DD).')
    else:
        end = today
    if start > end:
        raise ValueError('start must be on or before end.')
    if end - start > timedelta(days=366):
        raise ValueError('Analytics date range cannot exceed 366 days.')
    return start, end


def _task_completed_on(task, start, end):
    return (
        task.status == 'completed'
        and task.completed_at is not None
        and start <= task.completed_at.date() <= end
    )


def employee_analytics(user, start, end):
    tasks = accessible_tasks(user).all()
    completed_period = [task for task in tasks if _task_completed_on(task, start, end)]
    period_total = sum(1 for task in tasks if task.created_at and start <= task.created_at.date() <= end)
    open_tasks = [task for task in tasks if task.status != 'completed']
    overdue = [task for task in open_tasks if task.due_date and task.due_date < date.today()]
    durations = [
        (task.completed_at.replace(tzinfo=timezone.utc) - task.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        for task in completed_period if task.created_at and task.completed_at
    ]
    by_status = {status: sum(1 for task in tasks if task.status == status) for status in (
        'todo', 'pending', 'in_progress', 'blocked', 'in_review', 'changes_requested', 'completed'
    )}
    by_priority = {priority: sum(1 for task in tasks if task.priority == priority) for priority in ('high', 'medium', 'low')}
    trend = []
    cursor = start
    while cursor <= end:
        trend.append({
            'date': cursor.isoformat(),
            'completed': sum(1 for task in completed_period if task.completed_at.date() == cursor),
        })
        cursor += timedelta(days=1)
    return {
        'employee_id': user.id,
        'employee_name': user.full_name or user.username,
        'start': start.isoformat(),
        'end': end.isoformat(),
        'completed': len(completed_period),
        'open': len(open_tasks),
        'overdue': len(overdue),
        'completion_rate': round(len(completed_period) / period_total * 100, 1) if period_total else 0,
        'completion_rate_definition': 'Tasks completed in the period divided by tasks created in the period.',
        'average_completion_hours': round(sum(durations) / len(durations), 1) if durations else None,
        'by_status': by_status,
        'by_priority': by_priority,
        'trend': trend,
        'goals': [goal_to_dict(goal, user, tasks) for goal in Goal.query.filter_by(user_id=user.id).order_by(Goal.target_date.asc()).all()],
    }


def goal_progress(goal, tasks=None, today=None):
    today = today or date.today()
    tasks = list(tasks if tasks is not None else Task.query.filter(
        or_(Task.user_id == goal.user_id, Task.assigned_to_id == goal.user_id)
    ).all())
    scoped = [task for task in tasks if task.completed_at and goal.start_date <= task.completed_at.date() <= goal.target_date]
    if goal.goal_type == 'reduce_overdue':
        current = sum(1 for task in tasks if task.status != 'completed' and task.due_date and goal.start_date <= task.due_date <= min(goal.target_date, today) and task.due_date < today)
    elif goal.goal_type == 'complete_before_deadline':
        current = sum(1 for task in scoped if task.due_date and task.completed_at.date() <= task.due_date)
    else:
        current = len(scoped)
    current = min(current, goal.target_value)
    return current, round(current / goal.target_value * 100, 1) if goal.target_value else 0


def goal_to_dict(goal, user, tasks=None):
    current, percent = goal_progress(goal, tasks)
    status = 'completed' if current >= goal.target_value else goal.status
    return {
        'id': goal.id, 'title': goal.title, 'description': goal.description or '',
        'goal_type': goal.goal_type, 'target_value': goal.target_value, 'current_progress': current,
        'progress_percent': percent, 'start_date': goal.start_date.isoformat(),
        'target_date': goal.target_date.isoformat(), 'status': status,
        'created_at': goal.created_at.isoformat() if goal.created_at else None,
    }
