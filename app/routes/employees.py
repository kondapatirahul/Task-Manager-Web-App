"""
Employee Directory and Administration API endpoints.

Endpoints
---------
GET   /api/employees                 Employee directory with multi-factor search & filters
POST  /api/employees                 Admin/HR creates/invites employee with activation flow
GET   /api/employees/<id>            Employee detail profile with teams & reporting tree
PUT   /api/employees/<id>            Update employee profile, department, teams & role
PATCH /api/employees/<id>/status     Activate or deactivate employee account safely
"""
import re
import secrets
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import (
    User, Department, Organization, Team, team_members, Category,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD, ROLE_EMPLOYEE,
    ALL_ROLES, ADMIN_HR_ROLES, MANAGEMENT_ROLES, utc_now
)
from app.routes.utils import api_success, api_error, roles_required, active_account_required

employees_bp = Blueprint('employees', __name__, url_prefix='/api/employees')

EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _can_assign_role(caller, target_role):
    """Prevent unauthorized users from escalating roles."""
    if caller.is_super_admin:
        return True
    if caller.role == ROLE_ADMIN:
        return target_role in (ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD, ROLE_EMPLOYEE)
    if caller.role == ROLE_HR:
        return target_role in (ROLE_HR, ROLE_TEAM_LEAD, ROLE_EMPLOYEE)
    return False


@employees_bp.route('', methods=['GET'])
@login_required
def get_employees():
    """
    Search and filter employee directory.
    Filters:
      - q: name, username, email, job title
      - department_id: filter by department
      - team_id: filter by team membership
      - role: filter by role
      - status: 'active', 'inactive', 'all'
      - organization_id: filter by organization
    """
    query = User.query

    # Organization boundary
    org_id = request.args.get('organization_id')
    if org_id:
        try:
            query = query.filter(User.organization_id == int(org_id))
        except ValueError:
            pass
    elif not current_user.is_super_admin and current_user.organization_id:
        query = query.filter(User.organization_id == current_user.organization_id)

    # Search keyword
    q = (request.args.get('q') or '').strip()
    if q:
        pat = f'%{q}%'
        query = query.filter(
            or_(
                User.full_name.ilike(pat),
                User.username.ilike(pat),
                User.email.ilike(pat),
                User.job_title.ilike(pat)
            )
        )

    # Department filter
    dept_id = request.args.get('department_id')
    if dept_id:
        try:
            query = query.filter(User.department_id == int(dept_id))
        except ValueError:
            pass

    # Team membership filter
    team_id = request.args.get('team_id')
    if team_id:
        try:
            t_id = int(team_id)
            query = query.join(team_members, User.id == team_members.c.user_id).filter(
                team_members.c.team_id == t_id
            )
        except ValueError:
            pass

    # Role filter
    role = (request.args.get('role') or '').strip().lower()
    if role in ALL_ROLES or role == ROLE_HR:
        query = query.filter(User.role == role)

    # Account status filter
    status = (request.args.get('status') or '').strip().lower()
    if status == 'active':
        query = query.filter(User.account_active == True)
    elif status == 'inactive':
        query = query.filter(User.account_active == False)

    users = query.order_by(User.full_name.asc(), User.username.asc()).all()
    return api_success([u.to_dict() for u in users])


@employees_bp.route('', methods=['POST'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def create_employee():
    """
    Invite or create a new employee with secure account activation credentials.
    Restricted to Admin / HR.
    """
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    full_name = (data.get('full_name') or '').strip()
    username = (data.get('username') or '').strip()
    role = (data.get('role') or ROLE_EMPLOYEE).strip().lower()
    department_id = data.get('department_id')
    organization_id = data.get('organization_id') or current_user.organization_id
    job_title = (data.get('job_title') or '').strip()
    phone = (data.get('phone') or '').strip()
    reports_to_id = data.get('reports_to_id')
    team_ids = data.get('team_ids') or []
    password = data.get('password')

    if not email or not EMAIL_REGEX.match(email):
        return api_error('A valid email address is required.', 400)

    if not full_name:
        return api_error('Full name is required.', 400)

    if len(full_name) > 100:
        return api_error('Full name must be 100 characters or less.', 400)

    # Prevent unauthorized privilege assignment
    if not _can_assign_role(current_user, role):
        return api_error('You do not have permission to assign this role.', 403)

    if User.query.filter_by(email=email).first():
        return api_error('An account with this email already exists.', 409)

    # Generate username if not provided
    if not username:
        base_username = email.split('@')[0]
        username = re.sub(r'[^a-zA-Z0-9_]', '_', base_username)

    if User.query.filter_by(username=username).first():
        username = f'{username}_{User.query.count() + 1}'

    # Secure activation password generation if not explicitly supplied
    activation_token = None
    if not password:
        activation_token = secrets.token_urlsafe(12)
        password = activation_token
    elif len(password) < 6:
        return api_error('Password must be at least 6 characters long.', 400)

    if department_id:
        dept = db.session.get(Department, department_id)
        if not dept:
            return api_error('Department not found.', 404)

    if reports_to_id:
        mgr = db.session.get(User, reports_to_id)
        if not mgr:
            return api_error('Reporting manager user not found.', 404)

    user = User(
        username=username,
        full_name=full_name,
        email=email,
        role=role,
        organization_id=organization_id,
        department_id=department_id,
        job_title=job_title or None,
        phone=phone or None,
        reports_to_id=reports_to_id,
        account_active=True,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.flush()

    # Assign starter categories
    for cat_name in ('Work', 'Personal', 'Projects'):
        db.session.add(Category(name=cat_name, user_id=user.id))

    # Assign to initial teams
    if team_ids and isinstance(team_ids, list):
        for tid in team_ids:
            try:
                tid_int = int(tid)
                team = db.session.get(Team, tid_int)
                if team:
                    db.session.execute(
                        team_members.insert().values(
                            team_id=team.id,
                            user_id=user.id,
                            role='member',
                            joined_at=utc_now()
                        )
                    )
            except (ValueError, TypeError):
                pass

    db.session.commit()

    resp_data = user.to_dict()
    if activation_token:
        resp_data['activation_token'] = activation_token

    return api_success(resp_data, message='Employee account created successfully.', status_code=201)


@employees_bp.route('/<int:user_id>', methods=['GET'])
@login_required
def get_employee(user_id):
    """Retrieve full employee profile, team assignments, and direct reports."""
    user = db.session.get(User, user_id)
    if not user:
        return api_error('Employee not found.', 404)

    # Cross-organization view protection
    if not current_user.is_super_admin and current_user.organization_id and user.organization_id:
        if current_user.organization_id != user.organization_id:
            return api_error('You do not have permission to view employees from other organizations.', 403)

    data = user.to_dict()
    # Direct reports
    data['direct_reports'] = [
        {
            'id': dr.id,
            'full_name': dr.full_name or dr.username,
            'email': dr.email,
            'job_title': dr.job_title or '',
            'role': dr.role,
        }
        for dr in user.direct_reports.all()
    ]
    # Task statistics
    tasks = user.tasks.all()
    data['task_stats'] = {
        'total': len(tasks),
        'completed': sum(1 for t in tasks if t.status == 'completed'),
        'pending': sum(1 for t in tasks if t.status == 'pending'),
    }

    return api_success(data)


@employees_bp.route('/<int:user_id>', methods=['PUT'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def update_employee(user_id):
    """Update employee details, department, role, manager, and team assignments."""
    user = db.session.get(User, user_id)
    if not user:
        return api_error('Employee not found.', 404)

    # Cross-organization restriction
    if not current_user.is_super_admin and current_user.organization_id and user.organization_id:
        if current_user.organization_id != user.organization_id:
            return api_error('You do not have permission to modify employees in other organizations.', 403)

    data = request.get_json(silent=True) or {}
    full_name = data.get('full_name')
    job_title = data.get('job_title')
    phone = data.get('phone')
    department_id = data.get('department_id')
    reports_to_id = data.get('reports_to_id')
    role = data.get('role')
    team_ids = data.get('team_ids')

    if full_name is not None:
        name_str = full_name.strip()
        if not name_str:
            return api_error('Full name cannot be empty.', 400)
        user.full_name = name_str

    if job_title is not None:
        user.job_title = job_title.strip() or None

    if phone is not None:
        user.phone = phone.strip() or None

    if 'department_id' in data:
        if department_id:
            dept = db.session.get(Department, department_id)
            if not dept:
                return api_error('Department not found.', 404)
            user.department_id = department_id
        else:
            user.department_id = None

    if 'reports_to_id' in data:
        if reports_to_id:
            if reports_to_id == user.id:
                return api_error('An employee cannot report to themselves.', 400)
            mgr = db.session.get(User, reports_to_id)
            if not mgr:
                return api_error('Manager user not found.', 404)
            user.reports_to_id = reports_to_id
        else:
            user.reports_to_id = None

    if role:
        role_clean = role.strip().lower()
        if role_clean in ALL_ROLES or role_clean == ROLE_HR:
            if not _can_assign_role(current_user, role_clean):
                return api_error('You do not have permission to assign this role.', 403)
            user.role = role_clean

    # Update team assignments if provided
    if team_ids is not None and isinstance(team_ids, list):
        # Remove existing memberships
        db.session.execute(
            team_members.delete().where(team_members.c.user_id == user.id)
        )
        # Add new memberships
        for tid in team_ids:
            try:
                tid_int = int(tid)
                team = db.session.get(Team, tid_int)
                if team:
                    db.session.execute(
                        team_members.insert().values(
                            team_id=team.id,
                            user_id=user.id,
                            role='member',
                            joined_at=utc_now()
                        )
                    )
            except (ValueError, TypeError):
                pass

    db.session.commit()
    return api_success(user.to_dict(), message='Employee profile updated successfully.')


@employees_bp.route('/<int:user_id>/status', methods=['PATCH'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR)
@active_account_required
def set_employee_status(user_id):
    """
    Deactivate or activate an employee account.
    Deactivating safely preserves historical task records, categories, and logs.
    """
    user = db.session.get(User, user_id)
    if not user:
        return api_error('Employee not found.', 404)

    if user.id == current_user.id:
        return api_error('You cannot deactivate your own account.', 400)

    # Super admin accounts cannot be modified by standard admin/HR
    if user.is_super_admin and not current_user.is_super_admin:
        return api_error('Cannot alter super admin account status.', 403)

    data = request.get_json(silent=True) or {}
    new_status = data.get('account_active')
    if new_status is None:
        # Toggle if not explicitly specified
        new_status = not user.account_active

    user.account_active = bool(new_status)
    db.session.commit()

    action_word = 'activated' if user.account_active else 'deactivated'
    return api_success(
        user.to_dict(),
        message=f'Employee account has been {action_word} successfully.'
    )
