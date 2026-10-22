"""
Department API endpoints.

Endpoints
---------
GET    /api/departments             List departments
POST   /api/departments             Create department (admin, super_admin, hr)
GET    /api/departments/<id>        Get department details
PUT    /api/departments/<id>        Update department (admin, super_admin, hr)
DELETE /api/departments/<id>        Delete department safely (unassigns members/teams)
"""
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import (
    Department, Organization, User, Team,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR,
)
from app.routes.utils import api_success, api_error, roles_required, active_account_required

departments_bp = Blueprint('departments', __name__, url_prefix='/api/departments')


@departments_bp.route('', methods=['GET'])
@login_required
def get_departments():
    """List departments. Scoped to user's organization unless admin."""
    query = Department.query

    org_id = request.args.get('organization_id')
    if org_id:
        try:
            query = query.filter(Department.organization_id == int(org_id))
        except ValueError:
            pass
    elif not current_user.is_admin and current_user.organization_id:
        query = query.filter(Department.organization_id == current_user.organization_id)

    departments = query.order_by(Department.name.asc()).all()
    return api_success([d.to_dict() for d in departments])


@departments_bp.route('', methods=['POST'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def create_department():
    """Create a new department within an organization."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    organization_id = data.get('organization_id') or current_user.organization_id
    head_id = data.get('head_id')

    if not name:
        return api_error('Department name is required.', 400)

    if len(name) > 100:
        return api_error('Department name must be 100 characters or less.', 400)

    if organization_id:
        org = db.session.get(Organization, organization_id)
        if not org:
            return api_error('Organization not found.', 404)
        if not current_user.is_super_admin and current_user.organization_id and current_user.organization_id != org.id:
            return api_error('You do not have permission to manage this organization.', 403)

        # Unique name within organization
        existing = Department.query.filter_by(organization_id=organization_id, name=name).first()
        if existing:
            return api_error('A department with this name already exists in this organization.', 409)

    if head_id:
        head_user = db.session.get(User, head_id)
        if not head_user:
            return api_error('Department head user not found.', 404)
        if not head_user.account_active:
            return api_error('Cannot assign a deactivated user as department head.', 400)

    dept = Department(
        name=name,
        description=description or None,
        organization_id=organization_id,
        head_id=head_id,
    )
    db.session.add(dept)
    db.session.commit()

    return api_success(dept.to_dict(), message='Department created successfully', status_code=201)


@departments_bp.route('/<int:dept_id>', methods=['GET'])
@login_required
def get_department(dept_id):
    """Retrieve department details with member and team rosters."""
    dept = db.session.get(Department, dept_id)
    if not dept:
        return api_error('Department not found.', 404)

    # Cross-organization access control
    if not current_user.is_admin and current_user.organization_id and dept.organization_id and current_user.organization_id != dept.organization_id:
        return api_error('You do not have permission to view this department.', 403)

    data = dept.to_dict()
    data['members'] = [
        {
            'id': u.id,
            'full_name': u.full_name or u.username,
            'username': u.username,
            'email': u.email,
            'role': u.role,
            'job_title': u.job_title or '',
            'account_active': u.account_active,
        }
        for u in dept.members.all()
    ]
    data['teams'] = [t.to_dict() for t in dept.teams.all()]
    return api_success(data)


@departments_bp.route('/<int:dept_id>', methods=['PUT'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def update_department(dept_id):
    """Update department information."""
    dept = db.session.get(Department, dept_id)
    if not dept:
        return api_error('Department not found.', 404)

    if not current_user.is_super_admin and current_user.organization_id and dept.organization_id and current_user.organization_id != dept.organization_id:
        return api_error('You do not have permission to modify this department.', 403)

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = data.get('description')
    head_id = data.get('head_id')

    if name:
        if len(name) > 100:
            return api_error('Department name must be 100 characters or less.', 400)
        existing = Department.query.filter(
            Department.organization_id == dept.organization_id,
            Department.name == name,
            Department.id != dept.id
        ).first()
        if existing:
            return api_error('A department with this name already exists in this organization.', 409)
        dept.name = name

    if description is not None:
        dept.description = description.strip() or None

    if 'head_id' in data:
        if head_id:
            head_user = db.session.get(User, head_id)
            if not head_user:
                return api_error('Department head user not found.', 404)
            if not head_user.account_active:
                return api_error('Cannot assign a deactivated user as department head.', 400)
            dept.head_id = head_id
        else:
            dept.head_id = None

    db.session.commit()
    return api_success(dept.to_dict(), message='Department updated successfully')


@departments_bp.route('/<int:dept_id>', methods=['DELETE'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def delete_department(dept_id):
    """Safely delete department and unassign associated users and teams."""
    dept = db.session.get(Department, dept_id)
    if not dept:
        return api_error('Department not found.', 404)

    if not current_user.is_super_admin and current_user.organization_id and dept.organization_id and current_user.organization_id != dept.organization_id:
        return api_error('You do not have permission to delete this department.', 403)

    # Safely unassign members and teams without deleting them
    User.query.filter_by(department_id=dept.id).update(
        {User.department_id: None},
        synchronize_session='fetch'
    )
    Team.query.filter_by(department_id=dept.id).update(
        {Team.department_id: None},
        synchronize_session='fetch'
    )

    db.session.delete(dept)
    db.session.commit()

    return api_success(message='Department deleted and associated members unassigned successfully')
