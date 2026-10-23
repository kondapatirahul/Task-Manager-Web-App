"""Controlled workflow rule configuration and inspection APIs."""

import json
from datetime import datetime, timezone

from flask import Blueprint, request
from flask_login import current_user, login_required

from app import db
from app.models import AutomationExecution, AutomationRule, Task, WorkflowTemplate
from app.routes.tasks import can_user_manage_task
from app.routes.utils import active_account_required, api_error, api_success
from app.services.automation import (
    VALID_RULE_TYPES,
    VALID_SCHEDULES,
    rule_manageable_by,
    rule_visible_to,
)
from app.services.workflow_templates import can_view_template

automation_bp = Blueprint('automation', __name__, url_prefix='/api/automation')


def serialize_rule(rule):
    return {
        'id': rule.id,
        'name': rule.name,
        'rule_type': rule.rule_type,
        'schedule': rule.schedule,
        'source_task_id': rule.source_task_id,
        'template_id': rule.template_id,
        'enabled': bool(rule.enabled),
        'next_run_at': rule.next_run_at.isoformat() if rule.next_run_at else None,
        'created_at': rule.created_at.isoformat() if rule.created_at else None,
    }


def serialize_execution(item):
    return {
        'id': item.id,
        'rule_id': item.rule_id,
        'execution_key': item.execution_key,
        'status': item.status,
        'started_at': item.started_at.isoformat() if item.started_at else None,
        'completed_at': item.completed_at.isoformat() if item.completed_at else None,
        'error_message': item.error_message,
        'result': json.loads(item.result_json or '{}'),
    }


@automation_bp.get('/rules')
@active_account_required
@login_required
def list_rules():
    rules = AutomationRule.query.order_by(AutomationRule.updated_at.desc()).all()
    return api_success([serialize_rule(rule) for rule in rules if rule_visible_to(current_user, rule)])


@automation_bp.post('/rules')
@active_account_required
@login_required
def create_rule():
    data = request.get_json(silent=True) or {}
    rule_type = str(data.get('rule_type') or '').strip().lower()
    if rule_type not in VALID_RULE_TYPES:
        return api_error('Unsupported automation rule type.', 400)
    name = str(data.get('name') or '').strip()
    if not name or len(name) > 200:
        return api_error('Rule name is required and must be at most 200 characters.', 400)
    if rule_type == 'overdue_notification':
        return api_error('Overdue notifications are processed by the runner and need no per-user rule.', 400)
    schedule = str(data.get('schedule') or '').strip().lower()
    if schedule not in VALID_SCHEDULES:
        return api_error('schedule must be daily, weekly, or monthly.', 400)
    try:
        next_run_at = datetime.fromisoformat(data.get('next_run_at')).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return api_error('next_run_at must be a valid ISO timestamp.', 400)
    source_task_id = data.get('source_task_id')
    template_id = data.get('template_id')
    if bool(source_task_id) == bool(template_id):
        return api_error('Choose exactly one source_task_id or template_id.', 400)
    source_task = db.session.get(Task, source_task_id) if source_task_id else None
    template = db.session.get(WorkflowTemplate, template_id) if template_id else None
    if source_task and not can_user_manage_task(current_user, source_task):
        return api_error('Task is outside your authorized scope.', 404)
    if template and not can_view_template(current_user, template):
        return api_error('Template is outside your authorized scope.', 404)
    if not source_task and not template:
        return api_error('Source task or template was not found.', 404)
    rule = AutomationRule(
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
        source_task_id=source_task.id if source_task else None,
        template_id=template.id if template else None,
        rule_type=rule_type,
        name=name,
        schedule=schedule,
        next_run_at=next_run_at,
        config_json='{}',
    )
    db.session.add(rule)
    db.session.commit()
    return api_success(serialize_rule(rule), message='Automation rule created.', status_code=201)


@automation_bp.patch('/rules/<int:rule_id>')
@active_account_required
@login_required
def update_rule(rule_id):
    rule = db.session.get(AutomationRule, rule_id)
    if not rule or not rule_manageable_by(current_user, rule):
        return api_error('Automation rule not found.', 404)
    data = request.get_json(silent=True) or {}
    if 'enabled' in data:
        if not isinstance(data['enabled'], bool):
            return api_error('enabled must be boolean.', 400)
        rule.enabled = data['enabled']
    if 'name' in data:
        name = str(data.get('name') or '').strip()
        if not name or len(name) > 200:
            return api_error('Rule name is required and must be at most 200 characters.', 400)
        rule.name = name
    db.session.commit()
    return api_success(serialize_rule(rule))


@automation_bp.get('/rules/<int:rule_id>/executions')
@active_account_required
@login_required
def executions(rule_id):
    rule = db.session.get(AutomationRule, rule_id)
    if not rule or not rule_visible_to(current_user, rule):
        return api_error('Automation rule not found.', 404)
    items = rule.executions.order_by(AutomationExecution.started_at.desc()).limit(100).all()
    return api_success([serialize_execution(item) for item in items])
