"""Saved view APIs with ownership, sharing, and bounded JSON filter definitions."""
import json
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.enterprise_models import SavedView
from app.routes.utils import active_account_required, api_error, api_success, log_audit

views_bp = Blueprint("saved_views", __name__, url_prefix="/api/enterprise/views")
ALLOWED_ENTITIES = {"task", "project", "meeting", "leave", "employee"}
ALLOWED_FILTER_FIELDS = {"status", "priority", "assignee_id", "creator_id", "team_id",
                         "category_id", "due_date", "created_at", "updated_at", "project_id"}
ALLOWED_OPERATORS = {"eq", "ne", "in", "contains", "before", "after", "is_empty", "is_not_empty"}
ALLOWED_COLUMNS = {"title", "status", "priority", "assignee", "creator", "team", "due_date",
                   "created_at", "updated_at", "progress", "category", "project"}

def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}

def _validate_filters(filters):
    if not isinstance(filters, list) or len(filters) > 30:
        return "filters must be a list containing at most 30 items."
    for item in filters:
        if not isinstance(item, dict) or item.get("field") not in ALLOWED_FILTER_FIELDS:
            return "Each filter must reference a supported field."
        if item.get("operator") not in ALLOWED_OPERATORS:
            return "Each filter must use a supported operator."
        if len(json.dumps(item, default=str)) > 2000:
            return "Individual filter is too large."
    return None

@views_bp.get("")
@login_required
@active_account_required
def list_views():
    query = SavedView.query.filter_by(organization_id=current_user.organization_id)
    query = query.filter((SavedView.owner_id == current_user.id) | (SavedView.is_shared.is_(True)))
    entity = request.args.get("entity_type")
    if entity:
        if entity not in ALLOWED_ENTITIES:
            return api_error("Unsupported entity_type.", 400)
        query = query.filter_by(entity_type=entity)
    rows = query.order_by(SavedView.updated_at.desc()).limit(200).all()
    return api_success([v.to_dict() for v in rows])

@views_bp.post("")
@login_required
@active_account_required
def create_view():
    data = _body()
    name = str(data.get("name", "")).strip()
    entity = data.get("entity_type", "task")
    filters = data.get("filters", [])
    columns = data.get("columns", [])
    if not name or len(name) > 100:
        return api_error("name is required and must be at most 100 characters.", 400)
    if entity not in ALLOWED_ENTITIES:
        return api_error("Unsupported entity_type.", 400)
    error = _validate_filters(filters)
    if error:
        return api_error(error, 400)
    if not isinstance(columns, list) or len(columns) > 20 or any(c not in ALLOWED_COLUMNS for c in columns):
        return api_error("columns must contain supported column names.", 400)
    row = SavedView(organization_id=current_user.organization_id, owner_id=current_user.id,
                    name=name, entity_type=entity, filters_json=json.dumps(filters),
                    columns_json=json.dumps(columns), is_shared=bool(data.get("is_shared", False)))
    db.session.add(row)
    db.session.commit()
    log_audit("saved_view.created", "saved_view", row.id, {"entity_type": entity})
    return api_success(row.to_dict(), "Saved view created.", 201)

@views_bp.patch("/<int:view_id>")
@login_required
@active_account_required
def update_view(view_id):
    row = SavedView.query.filter_by(id=view_id, organization_id=current_user.organization_id).first()
    if not row:
        return api_error("Saved view not found.", 404)
    if row.owner_id != current_user.id and not current_user.has_role("admin", "super_admin"):
        return api_error("Only the owner or an administrator can update this view.", 403)
    data = _body()
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 100:
            return api_error("name must be at most 100 characters.", 400)
        row.name = name
    if "filters" in data:
        error = _validate_filters(data["filters"])
        if error:
            return api_error(error, 400)
        row.filters_json = json.dumps(data["filters"])
    if "columns" in data:
        columns = data["columns"]
        if not isinstance(columns, list) or len(columns) > 20 or any(c not in ALLOWED_COLUMNS for c in columns):
            return api_error("columns must contain supported column names.", 400)
        row.columns_json = json.dumps(columns)
    if "is_shared" in data:
        row.is_shared = bool(data["is_shared"])
    db.session.commit()
    return api_success(row.to_dict(), "Saved view updated.")

@views_bp.delete("/<int:view_id>")
@login_required
@active_account_required
def delete_view(view_id):
    row = SavedView.query.filter_by(id=view_id, organization_id=current_user.organization_id).first()
    if not row:
        return api_error("Saved view not found.", 404)
    if row.owner_id != current_user.id and not current_user.has_role("admin", "super_admin"):
        return api_error("Only the owner or an administrator can delete this view.", 403)
    db.session.delete(row)
    db.session.commit()
    log_audit("saved_view.deleted", "saved_view", view_id, {})
    return api_success({"deleted": True})
