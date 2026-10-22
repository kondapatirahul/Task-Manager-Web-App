"""
Organization API endpoints.

Endpoints
---------
GET  /api/organizations             List organizations
POST /api/organizations             Create organization (admin, super_admin, hr)
GET  /api/organizations/<id>        Get organization details with departments and teams
PUT  /api/organizations/<id>        Update organization (admin, super_admin, hr)
POST /api/organizations/<id>/members Add user to organization (admin, super_admin, hr)
"""
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import (
    Organization, User,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR,
)
from app.routes.utils import api_success, api_error, roles_required, active_account_required

organizations_bp = Blueprint('organizations', __name__, url_prefix='/api/organizations')


@organizations_bp.route('', methods=['GET'])
@login_required
def get_organizations():
    """List organizations accessible to current user."""
    # Super admins and admins see all organizations
    if current_user.is_admin:
        orgs = Organization.query.order_by(Organization.name.asc()).all()
    elif current_user.organization_id:
        orgs = Organization.query.filter_by(id=current_user.organization_id).all()
    else:
        orgs = Organization.query.order_by(Organization.name.asc()).all()

    return api_success([o.to_dict() for o in orgs])


@organizations_bp.route('', methods=['POST'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def create_organization():
    """Create a new organization. Restricted to Admin/HR/Super Admin."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()

    if not name:
        return api_error('Organization name is required.', 400)

    if len(name) > 100:
        return api_error('Organization name must be 100 characters or less.', 400)

    existing = Organization.query.filter(Organization.name.ilike(name)).first()
    if existing:
        return api_error('An organization with this name already exists.', 409)

    org = Organization(
        name=name,
        description=description or None,
        created_by_id=current_user.id
    )
    db.session.add(org)
    db.session.flush()

    # If current user does not belong to any organization, attach them
    if not current_user.organization_id:
        current_user.organization_id = org.id

    db.session.commit()
    return api_success(org.to_dict(), message='Organization created successfully', status_code=201)


@organizations_bp.route('/<int:org_id>', methods=['GET'])
@login_required
def get_organization(org_id):
    """Retrieve organization profile with department and team lists."""
    org = db.session.get(Organization, org_id)
    if not org:
        return api_error('Organization not found.', 404)

    # Cross-organization access control: employees/leads can only view their own organization
    if not current_user.is_admin and current_user.organization_id and current_user.organization_id != org.id:
        return api_error('You do not have permission to view this organization.', 403)

    data = org.to_dict()
    data['departments'] = [d.to_dict() for d in org.departments.all()]
    data['teams'] = [t.to_dict() for t in org.teams.all()]
    return api_success(data)


@organizations_bp.route('/<int:org_id>', methods=['PUT'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def update_organization(org_id):
    """Update organization details. Restricted to Admin/HR."""
    org = db.session.get(Organization, org_id)
    if not org:
        return api_error('Organization not found.', 404)

    # Cross-organization restriction
    if not current_user.is_super_admin and current_user.organization_id and current_user.organization_id != org.id:
        return api_error('You do not have permission to modify this organization.', 403)

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = data.get('description')

    if name:
        if len(name) > 100:
            return api_error('Organization name must be 100 characters or less.', 400)
        existing = Organization.query.filter(
            Organization.name.ilike(name),
            Organization.id != org.id
        ).first()
        if existing:
            return api_error('An organization with this name already exists.', 409)
        org.name = name

    if description is not None:
        org.description = description.strip() or None

    db.session.commit()
    return api_success(org.to_dict(), message='Organization updated successfully')


@organizations_bp.route('/<int:org_id>/members', methods=['POST'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def add_organization_member(org_id):
    """Assign an employee or team lead to this organization."""
    org = db.session.get(Organization, org_id)
    if not org:
        return api_error('Organization not found.', 404)

    if not current_user.is_super_admin and current_user.organization_id and current_user.organization_id != org.id:
        return api_error('You do not have permission to manage this organization.', 403)

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    email = (data.get('email') or '').strip().lower()

    user = None
    if user_id:
        user = db.session.get(User, user_id)
    elif email:
        user = User.query.filter_by(email=email).first()

    if not user:
        return api_error('User not found.', 404)

    if not user.account_active:
        return api_error('Cannot add a deactivated user to an organization.', 400)

    user.organization_id = org.id
    db.session.commit()

    return api_success(user.to_dict(), message=f'User {user.username} added to organization successfully')
