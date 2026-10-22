"""
Employee Directory and Account Administration API routes.
"""
import re
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import (
    User, Department, Team, TeamMember, Task, Attendance,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE, ALL_ROLES
)
from app.routes.utils import api_success, api_error, roles_required, active_account_required, log_audit, send_notification

employees_bp = Blueprint('employees', __name__, url_prefix='/api/employees')
EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ── Directory Listing ──────────────────────────────────────────────────────────

@employees_bp.route('', methods=['GET'])
@login_required
@active_account_required
def list_employees():
    """
    List all employees in the organization with search and filter capabilities.
    Accessible to all authenticated employees (Employee Directory).
    """
    query = User.query

    # Directory visibility: admins/HR see the organization; team leads see
    # only members of teams they lead; employees see only their own profile.
    if current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        pass
    elif current_user.is_team_lead:
        led_team_ids = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
        member_ids = {current_user.id}
        if led_team_ids:
            member_ids.update(m.user_id for m in TeamMember.query.filter(TeamMember.team_id.in_(led_team_ids)).all())
            # Include legacy records whose team_id is populated even if the join row is missing.
            member_ids.update(u.id for u in User.query.filter(User.team_id.in_(led_team_ids)).all())
        query = query.filter(User.id.in_(member_ids))
    else:
        query = query.filter(User.id == current_user.id)

    # Scope to current user's organization if assigned
    if current_user.organization_id:
        query = query.filter(
            (User.organization_id == current_user.organization_id) | (User.organization_id.is_(None))
        )

    # Search filter: name, username, email, designation
    q = (request.args.get('q') or '').strip()
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                User.full_name.ilike(pattern),
                User.username.ilike(pattern),
                User.email.ilike(pattern),
                User.designation.ilike(pattern)
            )
        )

    # Department filter
    dept_id = request.args.get('department_id')
    if dept_id:
        try:
            query = query.filter(User.department_id == int(dept_id))
        except ValueError:
            pass

    # Team filter
    team_id = request.args.get('team_id')
    if team_id:
        try:
            query = query.filter(User.team_id == int(team_id))
        except ValueError:
            pass

    # Role filter
    role = (request.args.get('role') or '').strip().lower()
    if role in ALL_ROLES:
        query = query.filter(User.role == role)

    # Status filter: default to active unless specified or admin requests all
    status = (request.args.get('status') or 'active').strip().lower()
    if status == 'active':
        query = query.filter(User.account_active == True)
    elif status == 'inactive':
        query = query.filter(User.account_active == False)
    # 'all' shows both active and inactive

    users = query.order_by(User.full_name.asc(), User.username.asc()).all()
    return api_success([u.to_dict() for u in users])


# ── Employee Profile & Details ────────────────────────────────────────────────

@employees_bp.route('/<int:user_id>', methods=['GET'])
@login_required
@active_account_required
def get_employee(user_id):
    user = User.query.get_or_404(user_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN) and user.id != current_user.id:
        if current_user.is_team_lead:
            led_team_ids = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
            is_member = bool(led_team_ids and TeamMember.query.filter(TeamMember.team_id.in_(led_team_ids), TeamMember.user_id == user.id).first())
            if not is_member:
                return api_error('Employee not found or not in your team.', 404)
        else:
            return api_error('Employee not found.', 404)
    data = user.to_dict()

    # Include recent active task summary
    active_tasks = Task.query.filter(
        (Task.assignee_id == user.id) | (Task.user_id == user.id),
        Task.status != 'completed'
    ).count()
    data['active_tasks_count'] = active_tasks

    # Include attendance summary
    last_attendance = Attendance.query.filter_by(user_id=user.id).order_by(Attendance.check_in.desc()).first()
    data['last_seen'] = last_attendance.check_in.isoformat() if last_attendance else None
    data['current_attendance_status'] = last_attendance.status if last_attendance else 'none'

    return api_success(data)


# ── Create / Provision Employee (Admin / HR) ───────────────────────────────────

@employees_bp.route('', methods=['POST'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def create_employee():
    data      = request.get_json(silent=True) or {}
    email     = (data.get('email') or '').strip().lower()
    full_name = (data.get('full_name') or '').strip()
    username  = (data.get('username') or '').strip()
    password  = data.get('password') or 'Welcome123!'
    role      = (data.get('role') or ROLE_EMPLOYEE).strip().lower()
    designation = (data.get('designation') or 'Employee').strip()
    dept_id   = data.get('department_id')
    team_id   = data.get('team_id')
    manager_id = data.get('manager_id')
    phone     = (data.get('phone') or '').strip()

    if not email or not EMAIL_REGEX.match(email):
        return api_error('A valid email address is required.', 400)
    if not full_name:
        return api_error('Employee full name is required.', 400)
    if role not in ALL_ROLES:
        return api_error(f"Invalid role. Must be one of: {', '.join(ALL_ROLES)}", 400)

    # Super admin assignment protection
    if role == ROLE_SUPER_ADMIN and not current_user.is_super_admin:
        return api_error('Only super administrators can assign the Super Admin role.', 403)

    if User.query.filter_by(email=email).first():
        return api_error('An account with this email already exists.', 409)

    if not username:
        base_username = email.split('@')[0]
        username = re.sub(r'[^a-zA-Z0-9_]', '_', base_username)

    if User.query.filter_by(username=username).first():
        username = f'{username}_{User.query.count() + 1}'

    emp = User(
        full_name=full_name,
        username=username,
        email=email,
        role=role,
        designation=designation,
        department_id=int(dept_id) if dept_id else None,
        team_id=int(team_id) if team_id else None,
        manager_id=int(manager_id) if manager_id else None,
        organization_id=current_user.organization_id or 1,
        phone=phone,
        account_active=True
    )
    emp.set_password(password)

    db.session.add(emp)
    db.session.flush()

    # Assign employee ID code e.g. EMP-0042
    emp.employee_id_code = f"EMP-{emp.id:04d}"

    # If team specified, add to team members
    if emp.team_id:
        db.session.add(TeamMember(team_id=emp.team_id, user_id=emp.id))

    db.session.commit()

    log_audit('employee_created', 'User', emp.id, f'Created employee account {emp.username} ({emp.email}) with role {emp.role}')
    send_notification(
        emp.id,
        'Welcome to TaskNest Enterprise',
        f'Your account has been provisioned as {emp.designation}. Please review your settings and change your password.',
        '/settings',
        'system'
    )

    return api_success(emp.to_dict(), message='Employee account created successfully.', status_code=201)


# ── Update Employee (Admin / HR) ───────────────────────────────────────────────

@employees_bp.route('/<int:user_id>', methods=['PUT'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def update_employee(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}

    if 'full_name' in data:
        name = (data['full_name'] or '').strip()
        if name:
            user.full_name = name

    if 'designation' in data:
        user.designation = (data['designation'] or '').strip()

    if 'phone' in data:
        user.phone = (data['phone'] or '').strip()

    if 'department_id' in data:
        dept_val = data['department_id']
        user.department_id = int(dept_val) if dept_val else None

    if 'team_id' in data:
        team_val = data['team_id']
        new_team_id = int(team_val) if team_val else None
        if new_team_id != user.team_id:
            user.team_id = new_team_id
            if new_team_id and not TeamMember.query.filter_by(team_id=new_team_id, user_id=user.id).first():
                db.session.add(TeamMember(team_id=new_team_id, user_id=user.id))

    if 'manager_id' in data:
        mgr_val = data['manager_id']
        if mgr_val and int(mgr_val) != user.id:
            user.manager_id = int(mgr_val)
        else:
            user.manager_id = None

    if 'role' in data:
        new_role = (data['role'] or '').strip().lower()
        if new_role in ALL_ROLES:
            if new_role == ROLE_SUPER_ADMIN and not current_user.is_super_admin:
                return api_error('Only super administrators can assign the Super Admin role.', 403)
            user.role = new_role

    db.session.commit()
    log_audit('employee_updated', 'User', user.id, f'Updated employee record for {user.username}')
    return api_success(user.to_dict(), message='Employee record updated successfully.')


# ── Account Status (Activation / Deactivation) ─────────────────────────────────

@employees_bp.route('/<int:user_id>/status', methods=['PATCH'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def set_employee_status(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return api_error('You cannot deactivate your own account.', 400)

    data = request.get_json(silent=True) or {}
    if 'active' not in data:
        return api_error('Active state (true/false) is required.', 400)

    new_active = bool(data['active'])
    user.account_active = new_active
    db.session.commit()

    action = 'activated' if new_active else 'deactivated'
    log_audit(f'employee_{action}', 'User', user.id, f'{action.capitalize()} account for {user.username}')

    return api_success(
        user.to_dict(),
        message=f'Employee account has been {action}. Historical records preserved.'
    )
