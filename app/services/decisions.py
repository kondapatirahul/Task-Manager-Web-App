"""Project decision authorization and serialization."""

from app import db
from app.models import (
    DecisionHistory,
    ProjectDecision,
    Task,
    Team,
    team_members,
)
from app.routes.tasks import can_user_view_task

DECISION_STATUSES = {'proposed', 'accepted', 'superseded', 'rejected'}


def can_view_team(user, team):
    if not team:
        return False
    if user.role == 'super_admin':
        return True
    if user.role in ('admin', 'hr'):
        return user.organization_id is None or team.organization_id == user.organization_id
    if team.lead_id == user.id:
        return True
    return db.session.query(team_members).filter_by(
        team_id=team.id, user_id=user.id
    ).first() is not None


def can_manage_decision(user, decision):
    return bool(
        decision and can_view_team(user, decision.team)
        and (
            user.role in ('super_admin', 'admin', 'hr')
            or decision.author_id == user.id
            or decision.team.lead_id == user.id
        )
    )


def linked_tasks_for_user(user, decision):
    return [
        task for task in decision.linked_tasks.all()
        if can_user_view_task(user, task)
    ]


def serialize_decision(user, decision):
    return {
        'id': decision.id,
        'team_id': decision.team_id,
        'team_name': decision.team.name if decision.team else None,
        'author_id': decision.author_id,
        'author_name': (
            decision.author.full_name or decision.author.username
        ) if decision.author else 'Former member',
        'title': decision.title,
        'details': decision.details,
        'rationale': decision.rationale,
        'status': decision.status,
        'can_edit': can_manage_decision(user, decision),
        'alternatives': decision.alternatives or '',
        'created_at': decision.created_at.isoformat() if decision.created_at else None,
        'updated_at': decision.updated_at.isoformat() if decision.updated_at else None,
        'linked_tasks': [
            {
                'id': task.id,
                'title': task.title,
                'status': task.status,
                'task_url': f'/tasks/{task.id}',
            }
            for task in linked_tasks_for_user(user, decision)
        ],
        'history': [
            {
                'id': entry.id,
                'old_status': entry.old_status,
                'new_status': entry.new_status,
                'title': entry.title,
                'details': entry.details,
                'rationale': entry.rationale,
                'alternatives': entry.alternatives or '',
                'change_note': entry.change_note or '',
                'changed_by_id': entry.changed_by_id,
                'changed_by_name': (
                    entry.changed_by.full_name or entry.changed_by.username
                ) if entry.changed_by else 'System',
                'created_at': entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in decision.history.all()
        ],
    }


def create_history(decision, actor, old_status=None, change_note=None):
    db.session.add(DecisionHistory(
        decision_id=decision.id,
        changed_by_id=actor.id if actor else None,
        old_status=old_status,
        new_status=decision.status,
        title=decision.title,
        details=decision.details,
        rationale=decision.rationale,
        alternatives=decision.alternatives,
        change_note=change_note,
    ))
