"""Authorized workload and capacity calculations."""

from datetime import date, timedelta
from sqlalchemy import or_

from app import db
from app.models import Task, User, Team, team_members

DEFAULT_WEEKLY_CAPACITY_HOURS = 40.0
HIGH_UTILIZATION_PERCENT = 100.0
SUBSTANTIAL_OVERDUE_COUNT = 2
DEFAULT_ESTIMATED_EFFORT_HOURS = 0.0


def employee_tasks(user_id):
    return Task.query.filter(
        or_(
            Task.assigned_to_id == user_id,
            (Task.user_id == user_id) & (
                (Task.assigned_to_id.is_(None)) |
                (Task.assigned_to_id == user_id)
            ),
        )
    ).all()


def authorized_task_query(user):
    """Return tasks visible to a user, including organization boundaries."""
    if user.role == 'super_admin':
        return Task.query
    if user.role == 'admin':
        if user.organization_id is None:
            return Task.query.filter(Task.user_id == user.id)
        organization_user_ids = db.session.query(User.id).filter(
            User.organization_id == user.organization_id
        )
        organization_team_ids = db.session.query(Team.id).filter(
            Team.organization_id == user.organization_id
        )
        return Task.query.filter(or_(
            Task.user_id.in_(organization_user_ids),
            Task.assigned_to_id.in_(organization_user_ids),
            Task.team_id.in_(organization_team_ids),
        ))
    conditions = [Task.user_id == user.id, Task.assigned_to_id == user.id]
    if user.role == 'team_lead':
        team_ids = db.session.query(Team.id).filter(
            Team.lead_id == user.id
        )
        if user.organization_id is not None:
            team_ids = team_ids.filter(Team.organization_id == user.organization_id)
        conditions.append(Task.team_id.in_(team_ids))
    return Task.query.filter(or_(*conditions))


def workload_summary(user, tasks=None, today=None):
    today = today or date.today()
    tasks = list(tasks if tasks is not None else employee_tasks(user.id))
    open_tasks = [task for task in tasks if task.status != 'completed']
    overdue = [task for task in open_tasks if task.due_date and task.due_date < today]
    due_today = [task for task in open_tasks if task.due_date == today]
    in_progress = [task for task in open_tasks if task.status == 'in_progress']
    high_priority = [task for task in open_tasks if task.priority == 'high']
    week_start = today - timedelta(days=today.weekday())
    completed_this_week = [
        task for task in tasks
        if task.status == 'completed' and task.completed_at
        and week_start <= task.completed_at.date() <= today
    ]
    effort_values = [
        task.estimated_effort_hours for task in open_tasks
        if task.estimated_effort_hours is not None and task.estimated_effort_hours >= 0
    ]
    remaining_effort = sum(effort_values)
    capacity = user.weekly_capacity_hours if user.weekly_capacity_hours is not None else DEFAULT_WEEKLY_CAPACITY_HOURS
    utilization = (remaining_effort / capacity * 100) if capacity > 0 else None
    overdue_warning = len(overdue) >= SUBSTANTIAL_OVERDUE_COUNT or bool(overdue and high_priority)
    workload_level = 'over_capacity' if utilization is not None and utilization > HIGH_UTILIZATION_PERCENT else (
        'high' if len(open_tasks) >= 8 or (utilization is not None and utilization >= 80) else 'manageable'
    )
    capacity_state = (
        'unknown' if utilization is None else
        'overloaded' if utilization > 100 else
        'near_capacity' if utilization >= 80 else
        'available'
    )
    recommendations = []
    if overdue:
        recommendations.append('Review overdue work and competing deadlines.')
    if utilization is not None and utilization > HIGH_UTILIZATION_PERCENT:
        recommendations.append('Consider reviewing high-priority assignments before taking on new work.')
    if not effort_values and open_tasks:
        recommendations.append('Add effort estimates to improve capacity accuracy.')
    return {
        'employee_id': user.id,
        'employee_name': user.full_name or user.username,
        'open_tasks': len(open_tasks),
        'in_progress': len(in_progress),
        'due_today': len(due_today),
        'overdue': len(overdue),
        'high_priority': len(high_priority),
        'completed_this_week': len(completed_this_week),
        'open_by_priority': {
            priority: sum(1 for task in open_tasks if task.priority == priority)
            for priority in ('high', 'medium', 'low')
        },
        'open_by_status': {
            status: sum(1 for task in open_tasks if task.status == status)
            for status in ('pending', 'todo', 'in_progress', 'blocked', 'in_review', 'changes_requested')
        },
        'estimated_remaining_effort_hours': remaining_effort,
        'estimated_tasks_count': len(effort_values),
        'unestimated_tasks_count': len(open_tasks) - len(effort_values),
        'weekly_capacity_hours': capacity,
        'utilization_percent': utilization,
        'workload_level': workload_level,
        'capacity_state': capacity_state,
        'overdue_warning': overdue_warning,
        'recommendations': recommendations,
    }


def permitted_team_employee_ids(user):
    if user.role == 'super_admin':
        return [row[0] for row in db.session.query(User.id).filter(User.role == 'employee').all()]
    if user.role == 'admin':
        query = db.session.query(User.id).filter(User.role == 'employee')
        if user.organization_id is None:
            query = query.filter(User.id == user.id)
        else:
            query = query.filter(User.organization_id == user.organization_id)
        return [row[0] for row in query.all()]
    if user.role != 'team_lead':
        return []
    lead_team_query = db.session.query(team_members.c.team_id).join(
        Team, Team.id == team_members.c.team_id
    ).filter(
        team_members.c.user_id == user.id,
        team_members.c.role == 'lead',
    )
    if user.organization_id is not None:
        lead_team_query = lead_team_query.filter(Team.organization_id == user.organization_id)
    team_ids = set(row[0] for row in lead_team_query.all())
    led_team_query = Team.query.filter_by(lead_id=user.id)
    if user.organization_id is not None:
        led_team_query = led_team_query.filter(Team.organization_id == user.organization_id)
    led_teams = led_team_query.all()
    team_ids.update(team.id for team in led_teams)
    if not team_ids:
        return []
    member_ids = {row[0] for row in db.session.query(team_members.c.user_id).filter(
        team_members.c.team_id.in_(team_ids)
    ).distinct().all()}
    member_ids.update(team.lead_id for team in led_teams if team.lead_id)
    return list(member_ids)


def eligible_assignment_employee_ids(user, team_id=None):
    """Return active employee IDs this manager may assign within a team."""
    permitted = permitted_team_employee_ids(user)
    if user.role == 'employee':
        permitted = [user.id]
    if not permitted:
        return []
    query = User.query.filter(
        User.id.in_(permitted),
        User.role == 'employee',
        User.account_active.is_(True),
    )
    if team_id is not None:
        team = db.session.get(Team, team_id)
        if not team:
            return []
        member_ids = db.session.query(team_members.c.user_id).filter(
            team_members.c.team_id == team_id
        )
        query = query.filter(User.id.in_(member_ids))
    return [employee.id for employee in query.all()]


def _employee_assignment_snapshot(employee, proposed_effort, exclude_task_id=None):
    tasks = [
        task for task in employee_tasks(employee.id)
        if task.status != 'completed' and task.id != exclude_task_id
    ]
    current_effort = sum(
        task.estimated_effort_hours
        for task in tasks
        if task.estimated_effort_hours is not None
        and task.estimated_effort_hours >= 0
    )
    planned_effort = current_effort + proposed_effort
    capacity = (
        employee.weekly_capacity_hours
        if employee.weekly_capacity_hours is not None
        else DEFAULT_WEEKLY_CAPACITY_HOURS
    )
    utilization = planned_effort / capacity * 100 if capacity > 0 else None
    return {
        'current_workload_hours': current_effort,
        'proposed_effort_hours': proposed_effort,
        'planned_workload_hours': planned_effort,
        'capacity_hours': capacity,
        'planned_utilization_percent': utilization,
        'would_exceed_capacity': capacity <= 0 or (
            utilization is not None and planned_effort > capacity
        ),
        'unestimated_open_tasks': sum(
            1 for task in tasks if task.estimated_effort_hours is None
        ),
    }


def assignment_recommendations(user, task=None, team_id=None,
                               proposed_effort=None):
    """Build deterministic, explainable assignment recommendations."""
    if task is not None:
        team_id = task.team_id if team_id is None else team_id
        if proposed_effort is None:
            proposed_effort = task.estimated_effort_hours
    if proposed_effort is None:
        proposed_effort = DEFAULT_ESTIMATED_EFFORT_HOURS
    if proposed_effort < 0:
        raise ValueError('Estimated effort must be non-negative.')
    employee_ids = eligible_assignment_employee_ids(user, team_id)
    employees = User.query.filter(User.id.in_(employee_ids)).all() if employee_ids else []
    recommendations = []
    for employee in employees:
        snapshot = _employee_assignment_snapshot(
            employee,
            proposed_effort,
            exclude_task_id=task.id if task else None,
        )
        reasons = []
        if team_id is not None:
            reasons.append('matching team membership')
        reasons.append(
            'lower estimated workload'
            if not snapshot['would_exceed_capacity']
            else 'capacity would be exceeded'
        )
        if employee.weekly_capacity_hours is None:
            reasons.append('default capacity of 40 hours used')
        if proposed_effort == DEFAULT_ESTIMATED_EFFORT_HOURS and (
            task is None or task.estimated_effort_hours is None
        ):
            reasons.append('missing estimate treated as 0 hours')
        recommendations.append({
            'employee_id': employee.id,
            'employee_name': employee.full_name or employee.username,
            'employee_email': employee.email,
            'reasons': reasons,
            **snapshot,
        })
    recommendations.sort(key=lambda item: (
        item['would_exceed_capacity'],
        item['planned_utilization_percent'] is None,
        item['planned_utilization_percent'] if item['planned_utilization_percent'] is not None else float('inf'),
        item['planned_workload_hours'],
        item['employee_id'],
    ))
    return recommendations


def team_workload(user, employee_id=None, filters=None):
    filters = filters or {}
    employee_ids = permitted_team_employee_ids(user)
    if employee_id is not None and employee_id not in employee_ids:
        return None
    if employee_id is not None:
        employee_ids = [employee_id]
    employees = User.query.filter(User.id.in_(employee_ids), User.account_active.is_(True)).all() if employee_ids else []
    results = []
    for employee in employees:
        tasks = employee_tasks(employee.id)
        if filters.get('status'):
            tasks = [task for task in tasks if task.status == filters['status']]
        if filters.get('priority'):
            tasks = [task for task in tasks if task.priority == filters['priority']]
        if filters.get('overdue') == 'true':
            tasks = [task for task in tasks if task.status != 'completed' and task.due_date and task.due_date < date.today()]
        results.append(workload_summary(employee, tasks=tasks))
    return results


def workload_state_counts(results):
    """Summarize capacity signals without inferring health or wellbeing."""
    return {
        state: sum(1 for item in results if item['capacity_state'] == state)
        for state in ('overloaded', 'near_capacity', 'available', 'unknown')
    }
