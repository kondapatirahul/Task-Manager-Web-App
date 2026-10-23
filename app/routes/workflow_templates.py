"""Workflow template library and instantiation endpoints."""

from datetime import date
import json

from flask import Blueprint, request
from flask_login import current_user, login_required

from app import db
from app.models import WorkflowTemplate
from app.routes.utils import active_account_required, api_error, api_success
from app.services.workflow_templates import (
    VALID_PRIORITIES,
    VALID_VISIBILITY,
    can_create_shared,
    can_manage_template,
    can_view_template,
    instantiate_template,
    serialize_template,
    validate_checklist,
)

templates_bp = Blueprint('workflow_templates', __name__, url_prefix='/api/workflow-templates')


def _text(data, key, maximum, required=True):
    value = str(data.get(key) or '').strip()
    if required and not value:
        return None, f'{key.replace("_", " ").capitalize()} is required.'
    if len(value) > maximum:
        return None, f'{key.replace("_", " ").capitalize()} cannot exceed {maximum} characters.'
    return value, None


def _template(template_id):
    template = db.session.get(WorkflowTemplate, template_id)
    return template if template and can_view_template(current_user, template) else None


def _payload(data, existing=None):
    name, error = _text(data, 'name', 200)
    if error:
        return None, error
    description, error = _text(data, 'description', 10000, required=False)
    if error:
        return None, error
    checklist, error = validate_checklist(data.get('checklist'))
    if error:
        return None, error
    priority = str(data.get('default_priority') or 'medium').strip().lower()
    if priority not in VALID_PRIORITIES:
        return None, 'default_priority must be low, medium, or high.'
    visibility = str(data.get('visibility') or 'private').strip().lower()
    if visibility not in VALID_VISIBILITY:
        return None, 'visibility must be private or organization.'
    if visibility == 'organization' and not can_create_shared(current_user):
        return None, 'Only authorized managers can create shared templates.'
    if visibility == 'organization' and current_user.organization_id is None:
        return None, 'Organization-visible templates require an organization.', 
    return {
        'name': name,
        'description': description or None,
        'checklist_json': json.dumps(checklist),
        'default_priority': priority,
        'visibility': visibility,
    }, None


@templates_bp.get('')
@active_account_required
@login_required
def list_templates():
    query = WorkflowTemplate.query.filter_by(is_archived=False)
    if current_user.role != 'super_admin':
        query = query.filter(
            (WorkflowTemplate.owner_id == current_user.id)
            | (
                (WorkflowTemplate.visibility == 'organization')
                & (WorkflowTemplate.organization_id == current_user.organization_id)
            )
        )
    return api_success([
        serialize_template(item, viewer=current_user)
        for item in query.order_by(WorkflowTemplate.updated_at.desc()).all()
    ])


@templates_bp.post('')
@active_account_required
@login_required
def create_template():
    payload, error = _payload(request.get_json(silent=True) or {})
    if error:
        return api_error(error, 400)
    organization_id = current_user.organization_id if payload['visibility'] == 'organization' else None
    template = WorkflowTemplate(owner_id=current_user.id, organization_id=organization_id, **payload)
    db.session.add(template)
    db.session.commit()
    return api_success(serialize_template(template, viewer=current_user), message='Workflow template created.', status_code=201)


@templates_bp.get('/<int:template_id>')
@active_account_required
@login_required
def get_template(template_id):
    template = _template(template_id)
    if not template:
        return api_error('Template not found.', 404)
    return api_success(serialize_template(template, include_generated=True, viewer=current_user))


@templates_bp.put('/<int:template_id>')
@active_account_required
@login_required
def update_template(template_id):
    template = _template(template_id)
    if not template or not can_manage_template(current_user, template):
        return api_error('Template not found.', 404)
    payload, error = _payload(request.get_json(silent=True) or {}, template)
    if error:
        return api_error(error, 400)
    template.name = payload['name']
    template.description = payload['description']
    template.checklist_json = payload['checklist_json']
    template.default_priority = payload['default_priority']
    template.visibility = payload['visibility']
    template.organization_id = current_user.organization_id if template.visibility == 'organization' else None
    db.session.commit()
    return api_success(serialize_template(template, viewer=current_user), message='Workflow template updated.')


@templates_bp.post('/<int:template_id>/duplicate')
@active_account_required
@login_required
def duplicate_template(template_id):
    source = _template(template_id)
    if not source:
        return api_error('Template not found.', 404)
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or f'{source.name} (Copy)').strip()
    if not name or len(name) > 200:
        return api_error('A duplicate name of 1 to 200 characters is required.', 400)
    copy = WorkflowTemplate(
        owner_id=current_user.id,
        organization_id=None,
        name=name,
        description=source.description,
        checklist_json=source.checklist_json,
        default_priority=source.default_priority,
        visibility='private',
    )
    db.session.add(copy)
    db.session.commit()
    return api_success(serialize_template(copy, viewer=current_user), message='Workflow template duplicated.', status_code=201)


@templates_bp.post('/<int:template_id>/archive')
@active_account_required
@login_required
def archive_template(template_id):
    template = _template(template_id)
    if not template or not can_manage_template(current_user, template):
        return api_error('Template not found.', 404)
    template.is_archived = True
    db.session.commit()
    return api_success(serialize_template(template, viewer=current_user), message='Workflow template archived.')


@templates_bp.post('/<int:template_id>/instantiate')
@active_account_required
@login_required
def instantiate(template_id):
    template = _template(template_id)
    if not template:
        return api_error('Template not found.', 404)
    data = request.get_json(silent=True) or {}
    raw_date = data.get('base_due_date')
    try:
        base_date = date.fromisoformat(raw_date) if raw_date else None
    except (TypeError, ValueError):
        return api_error('base_due_date must be a valid ISO date.', 400)
    created, error, status = instantiate_template(current_user, template, base_date)
    if error:
        return api_error(error, status)
    return api_success({
        'template_id': template.id,
        'tasks': [task.to_dict(dependency_user=current_user) for task in created],
    }, message='Tasks created from workflow template.', status_code=201)
