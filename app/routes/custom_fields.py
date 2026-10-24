"""Organization-scoped custom-field definitions and values."""
import json
import re
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.enterprise_models import CustomFieldDefinition, CustomFieldValue, Project
from app.models import Task, Meeting, LeaveRequest, User
from app.routes.utils import active_account_required, api_error, api_success, log_audit
from app.services.enterprise import validate_custom_field

custom_fields_bp = Blueprint("custom_fields", __name__, url_prefix="/api/enterprise/custom-fields")
ENTITY_TYPES = {"task", "project", "meeting", "leave", "employee"}
FIELD_TYPES = {"text", "number", "boolean", "date", "select", "multi_select", "url"}


def _entity_in_scope(entity_type, entity_id):
    """Require the target entity to exist inside the active organization."""
    org_id = current_user.organization_id
    if entity_type == "task":
        row = Task.query.filter_by(id=entity_id, organization_id=org_id).first()
    elif entity_type == "project":
        row = Project.query.filter_by(id=entity_id, organization_id=org_id).first()
    elif entity_type == "meeting":
        row = Meeting.query.filter_by(id=entity_id, organization_id=org_id).first()
    elif entity_type == "leave":
        row = LeaveRequest.query.filter_by(id=entity_id).first()
        row = row if row and row.user and row.user.organization_id == org_id else None
    elif entity_type == "employee":
        row = User.query.filter_by(id=entity_id, organization_id=org_id).first()
    else:
        row = None
    return row is not None

def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}

def _org_query():
    return CustomFieldDefinition.query.filter_by(organization_id=current_user.organization_id)

def _parse_options(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("options must be a list of at most 100 strings.")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 100 for item in value):
        raise ValueError("Each option must be non-empty text up to 100 characters.")
    if len(set(value)) != len(value):
        raise ValueError("options cannot contain duplicates.")
    return value

@custom_fields_bp.get("")
@login_required
@active_account_required
def list_definitions():
    entity = request.args.get("entity_type")
    query = _org_query()
    if entity:
        if entity not in ENTITY_TYPES:
            return api_error("Unsupported entity_type.", 400)
        query = query.filter_by(entity_type=entity)
    if request.args.get("include_inactive") != "1":
        query = query.filter_by(active=True)
    return api_success([row.to_dict() for row in query.order_by(CustomFieldDefinition.id.asc()).all()])

@custom_fields_bp.post("")
@login_required
@active_account_required
def create_definition():
    if not current_user.has_role("admin", "super_admin", "hr"):
        return api_error("Administrator or HR permission required.", 403)
    data = _body()
    entity = data.get("entity_type", "task")
    kind = data.get("field_type")
    label = str(data.get("label", "")).strip()
    key = str(data.get("field_key", "")).strip().lower()
    if entity not in ENTITY_TYPES or kind not in FIELD_TYPES:
        return api_error("Unsupported entity_type or field_type.", 400)
    if not label or len(label) > 100:
        return api_error("label is required and must be at most 100 characters.", 400)
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", key):
        return api_error("field_key must use lowercase letters, digits, and underscores.", 400)
    try:
        options = _parse_options(data.get("options", []))
    except ValueError as exc:
        return api_error(str(exc), 400)
    if kind in {"select", "multi_select"} and not options:
        return api_error("Select fields require at least one option.", 400)
    if kind not in {"select", "multi_select"} and options:
        return api_error("options are only supported for select fields.", 400)
    existing = _org_query().filter_by(entity_type=entity, field_key=key).first()
    if existing:
        return api_error("field_key already exists for this entity type.", 409)
    row = CustomFieldDefinition(organization_id=current_user.organization_id, entity_type=entity,
                                field_key=key, label=label, field_type=kind,
                                required=bool(data.get("required", False)),
                                options_json=json.dumps(options), created_by=current_user.id)
    db.session.add(row)
    db.session.commit()
    log_audit("custom_field.created", "custom_field", row.id, {"entity_type": entity, "field_key": key})
    return api_success(row.to_dict(), "Custom field created.", 201)

@custom_fields_bp.patch("/<int:field_id>")
@login_required
@active_account_required
def update_definition(field_id):
    if not current_user.has_role("admin", "super_admin", "hr"):
        return api_error("Administrator or HR permission required.", 403)
    row = _org_query().filter_by(id=field_id).first()
    if not row:
        return api_error("Custom field not found.", 404)
    data = _body()
    if "label" in data:
        label = str(data["label"]).strip()
        if not label or len(label) > 100:
            return api_error("label must be at most 100 characters.", 400)
        row.label = label
    if "required" in data:
        row.required = bool(data["required"])
    if "active" in data:
        row.active = bool(data["active"])
    if "options" in data:
        try:
            options = _parse_options(data["options"])
        except ValueError as exc:
            return api_error(str(exc), 400)
        if row.field_type in {"select", "multi_select"} and not options:
            return api_error("Select fields require at least one option.", 400)
        row.options_json = json.dumps(options)
    db.session.commit()
    return api_success(row.to_dict(), "Custom field updated.")

@custom_fields_bp.delete("/<int:field_id>")
@login_required
@active_account_required
def deactivate_definition(field_id):
    if not current_user.has_role("admin", "super_admin", "hr"):
        return api_error("Administrator or HR permission required.", 403)
    row = _org_query().filter_by(id=field_id).first()
    if not row:
        return api_error("Custom field not found.", 404)
    row.active = False
    db.session.commit()
    return api_success({"id": row.id, "active": False}, "Custom field deactivated.")

@custom_fields_bp.get("/<entity_type>/<int:entity_id>")
@login_required
@active_account_required
def get_values(entity_type, entity_id):
    if entity_type not in ENTITY_TYPES or entity_id < 1:
        return api_error("Invalid entity reference.", 400)
    if not _entity_in_scope(entity_type, entity_id):
        return api_error("Entity not found in your organization.", 404)
    definitions = _org_query().filter_by(entity_type=entity_type, active=True).all()
    values = CustomFieldValue.query.filter(CustomFieldValue.definition_id.in_([d.id for d in definitions]),
                                           CustomFieldValue.entity_id == entity_id).all() if definitions else []
    by_id = {v.definition_id: json.loads(v.value_json) for v in values}
    return api_success({d.field_key: {"definition": d.to_dict(), "value": by_id.get(d.id)} for d in definitions})

@custom_fields_bp.put("/<entity_type>/<int:entity_id>")
@login_required
@active_account_required
def set_values(entity_type, entity_id):
    if entity_type not in ENTITY_TYPES or entity_id < 1:
        return api_error("Invalid entity reference.", 400)
    if not _entity_in_scope(entity_type, entity_id):
        return api_error("Entity not found in your organization.", 404)
    data = _body()
    if len(data) > 100:
        return api_error("At most 100 custom-field values can be updated at once.", 400)
    definitions = _org_query().filter_by(entity_type=entity_type, active=True).all()
    by_key = {d.field_key: d for d in definitions}
    unknown = set(data) - set(by_key)
    if unknown:
        return api_error("Unknown custom field key(s): " + ", ".join(sorted(unknown)[:10]), 400)
    normalized = {}
    for key, value in data.items():
        definition = by_key[key]
        options = json.loads(definition.options_json or "[]")
        valid, clean, error = validate_custom_field(definition.field_type, value, options)
        if not valid:
            return api_error(f"{key}: {error}", 400)
        if definition.required and clean in (None, ""):
            return api_error(f"{key} is required.", 400)
        normalized[definition.id] = clean
    for definition_id, value in normalized.items():
        row = CustomFieldValue.query.filter_by(definition_id=definition_id, entity_id=entity_id).first()
        if row is None:
            row = CustomFieldValue(definition_id=definition_id, entity_id=entity_id,
                                   value_json=json.dumps(value), updated_by=current_user.id)
            db.session.add(row)
        else:
            row.value_json = json.dumps(value)
            row.updated_by = current_user.id
    db.session.commit()
    log_audit("custom_field.values_updated", entity_type, entity_id, {"keys": sorted(data.keys())})
    return api_success({"updated": sorted(data.keys())}, "Custom field values saved.")
