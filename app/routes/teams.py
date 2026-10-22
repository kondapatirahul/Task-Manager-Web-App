"""
Team API endpoints.

Endpoints
---------
GET    /api/teams                      List teams (scoped by authorization)
POST   /api/teams                      Create team (admin, hr, team_lead)
GET    /api/teams/<id>                 Get team details
PUT    /api/teams/<id>                 Update team (admin, hr, team lead)
DELETE /api/teams/<id>                 Delete team safely (admin, team lead)
GET    /api/teams/<id>/members         List team members
POST   /api/teams/<id>/members         Add member to team (admin, hr, team lead)
DELETE /api/teams/<id>/members/<uid>   Remove member from team (admin, team lead, self)
GET    /api/teams/<id>/tasks           List team tasks
POST   /api/teams/<id>/tasks           Create task assigned to team
"""
from datetime import datetime, date, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import text
from app import db
from app.models import (
    Team, Organization, Department, User, Task, team_members,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD, ROLE_EMPLOYEE,
    MANAGEMENT_ROLES, ADMIN_HR_ROLES, utc_now
)
from app.routes.utils import api_success, api_error, roles_required, active_account_required

teams_bp = Blueprint('teams', __name__, url_prefix='/api/teams')

VALID_PRIORITIES = {'low', 'medium', 'high'}


def _can_manage_team(team):
    """Return True if current user is admin, HR, or the lead of this specific team."""
    if current_user.is_admin or current_user.role == ROLE_HR:
        # Cross-organization check
        if not current_user.is_super_admin and current_user.organization_id and team.organization_id:
            return current_user.organization_id == team.organization_id
        return True
    return team.lead_id == current_user.id


def _can_view_team(team):
    """Return True if current user can view this team's details."""
    if current_user.is_admin or current_user.role == ROLE_HR:
        if not current_user.is_super_admin and current_user.organization_id and team.organization_id:
            return current_user.organization_id == team.organization_id
        return True
    if team.lead_id == current_user.id:
        return True
    # Member of team
    is_member = db.session.query(team_members).filter_by(team_id=team.id, user_id=current_user.id).first()
    return bool(is_member)


@teams_bp.route('', methods=['GET'])
@login_required
def get_teams():
    """
    List teams.
    - Admins / HR see all teams within their organization.
    - Team leads see ONLY their authorized teams (where they are lead or member).
    - Employees see only teams where they are a member.
    """
    query = Team.query

    # Organization filter
    org_id = request.args.get('organization_id')
    if org_id:
        try:
            query = query.filter(Team.organization_id == int(org_id))
        except ValueError:
            pass
    elif not current_user.is_super_admin and current_user.organization_id:
        query = query.filter(Team.organization_id == current_user.organization_id)

    # Department filter
    dept_id = request.args.get('department_id')
    if dept_id:
        try:
            query = query.filter(Team.department_id == int(dept_id))
        except ValueError:
            pass

    # Search filter
    q = (request.args.get('q') or '').strip()
    if q:
        query = query.filter(Team.name.ilike(f'%{q}%'))

    all_matching = query.order_by(Team.name.asc()).all()

    # Apply strict authorization boundaries
    if current_user.is_admin or current_user.role == ROLE_HR:
        visible_teams = all_matching
    elif current_user.role == ROLE_TEAM_LEAD:
        # Team Leads view only their authorized teams and members
        visible_teams = [t for t in all_matching if _can_view_team(t)]
    else:
        # Regular employee views only joined teams
        visible_teams = [t for t in all_matching if _can_view_team(t)]

    return api_success([t.to_dict() for t in visible_teams])


@teams_bp.route('', methods=['POST'])
@login_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD)
@active_account_required
def create_team():
    """Create a new team. Allowed for Admin, HR, and Team Leads."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    organization_id = data.get('organization_id') or current_user.organization_id
    department_id = data.get('department_id')
    lead_id = data.get('lead_id')

    if not name:
        return api_error('Team name is required.', 400)

    if len(name) > 100:
        return api_error('Team name must be 100 characters or less.', 400)

    # Cross-organization verification
    if organization_id:
        org = db.session.get(Organization, organization_id)
        if not org:
            return api_error('Organization not found.', 404)
        if not current_user.is_super_admin and current_user.organization_id and current_user.organization_id != org.id:
            return api_error('You do not have permission to create teams in this organization.', 403)

    if department_id:
        dept = db.session.get(Department, department_id)
        if not dept:
            return api_error('Department not found.', 404)
        if organization_id and dept.organization_id and dept.organization_id != organization_id:
            return api_error('Department does not belong to the specified organization.', 400)

    # If creator is a team lead and no lead_id specified, assign themselves as lead
    if not lead_id and current_user.role == ROLE_TEAM_LEAD:
        lead_id = current_user.id

    if lead_id:
        lead_user = db.session.get(User, lead_id)
        if not lead_user:
            return api_error('Designated team lead not found.', 404)
        if not lead_user.account_active:
            return api_error('Cannot assign a deactivated user as team lead.', 400)

    team = Team(
        name=name,
        description=description or None,
        organization_id=organization_id,
        department_id=department_id,
        lead_id=lead_id,
    )
    db.session.add(team)
    db.session.flush()

    # Automatically add lead and/or creator to team_members
    initial_member_ids = {current_user.id}
    if lead_id:
        initial_member_ids.add(lead_id)

    for uid in initial_member_ids:
        role_in_team = 'lead' if uid == lead_id else 'member'
        db.session.execute(
            team_members.insert().values(
                team_id=team.id,
                user_id=uid,
                role=role_in_team,
                joined_at=utc_now()
            )
        )

    db.session.commit()
    return api_success(team.to_dict(), message='Team created successfully', status_code=201)


@teams_bp.route('/<int:team_id>', methods=['GET'])
@login_required
def get_team(team_id):
    """Retrieve team details if authorized."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    if not _can_view_team(team):
        return api_error('You do not have permission to view this team.', 403)

    data = team.to_dict()
    # Include member list and task statistics
    members_q = db.session.query(
        User, team_members.c.role, team_members.c.joined_at
    ).join(team_members, User.id == team_members.c.user_id).filter(
        team_members.c.team_id == team.id
    ).all()

    data['members'] = [
        {
            'id': u.id,
            'full_name': u.full_name or u.username,
            'username': u.username,
            'email': u.email,
            'system_role': u.role,
            'team_role': tm_role,
            'job_title': u.job_title or '',
            'account_active': u.account_active,
            'joined_at': tm_joined.isoformat() if tm_joined else None,
        }
        for u, tm_role, tm_joined in members_q
    ]
    return api_success(data)


@teams_bp.route('/<int:team_id>', methods=['PUT'])
@login_required
@active_account_required
def update_team(team_id):
    """Update team info. Restricted to Admin, HR, or the specific Team Lead."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    if not _can_manage_team(team):
        return api_error('You do not have permission to modify this team.', 403)

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = data.get('description')
    department_id = data.get('department_id')
    lead_id = data.get('lead_id')

    if name:
        if len(name) > 100:
            return api_error('Team name must be 100 characters or less.', 400)
        team.name = name

    if description is not None:
        team.description = description.strip() or None

    if 'department_id' in data:
        if department_id:
            dept = db.session.get(Department, department_id)
            if not dept:
                return api_error('Department not found.', 404)
            team.department_id = department_id
        else:
            team.department_id = None

    if 'lead_id' in data:
        if lead_id:
            lead_user = db.session.get(User, lead_id)
            if not lead_user:
                return api_error('Designated lead user not found.', 404)
            if not lead_user.account_active:
                return api_error('Cannot assign a deactivated user as team lead.', 400)
            team.lead_id = lead_id

            # Ensure new lead is in team_members
            existing_tm = db.session.query(team_members).filter_by(team_id=team.id, user_id=lead_id).first()
            if not existing_tm:
                db.session.execute(
                    team_members.insert().values(
                        team_id=team.id,
                        user_id=lead_id,
                        role='lead',
                        joined_at=utc_now()
                    )
                )
            else:
                db.session.execute(
                    team_members.update().where(
                        team_members.c.team_id == team.id,
                        team_members.c.user_id == lead_id
                    ).values(role='lead')
                )
        else:
            team.lead_id = None

    db.session.commit()
    return api_success(team.to_dict(), message='Team updated successfully')


@teams_bp.route('/<int:team_id>', methods=['DELETE'])
@login_required
@active_account_required
def delete_team(team_id):
    """Safely delete team and preserve all historical tasks and user records."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    if not _can_manage_team(team):
        return api_error('You do not have permission to delete this team.', 403)

    # Safe unassign of tasks: preserve task records by nullifying team_id
    Task.query.filter_by(team_id=team.id).update(
        {Task.team_id: None},
        synchronize_session='fetch'
    )

    # Delete team memberships
    db.session.execute(
        team_members.delete().where(team_members.c.team_id == team.id)
    )

    db.session.delete(team)
    db.session.commit()

    return api_success(message='Team deleted and historical tasks safely preserved.')


# ── Team Memberships ──────────────────────────────────────────────────────────

@teams_bp.route('/<int:team_id>/members', methods=['GET'])
@login_required
def get_team_members(team_id):
    """List members of an authorized team."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    if not _can_view_team(team):
        return api_error('You do not have permission to view members of this team.', 403)

    members_q = db.session.query(
        User, team_members.c.role, team_members.c.joined_at
    ).join(team_members, User.id == team_members.c.user_id).filter(
        team_members.c.team_id == team.id
    ).order_by(User.full_name.asc()).all()

    return api_success([
        {
            'id': u.id,
            'full_name': u.full_name or u.username,
            'username': u.username,
            'email': u.email,
            'system_role': u.role,
            'team_role': tm_role,
            'job_title': u.job_title or '',
            'account_active': u.account_active,
            'joined_at': tm_joined.isoformat() if tm_joined else None,
        }
        for u, tm_role, tm_joined in members_q
    ])


@teams_bp.route('/<int:team_id>/members', methods=['POST'])
@login_required
@active_account_required
def add_team_member(team_id):
    """Add an employee to this team. Restricted to Admin, HR, or the specific Team Lead."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    if not _can_manage_team(team):
        return api_error('You do not have permission to manage members for this team.', 403)

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    email = (data.get('email') or '').strip().lower()
    role_in_team = (data.get('role') or 'member').strip().lower()
    if role_in_team not in ('lead', 'member'):
        role_in_team = 'member'

    user = None
    if user_id:
        user = db.session.get(User, user_id)
    elif email:
        user = User.query.filter_by(email=email).first()

    if not user:
        return api_error('User not found.', 404)

    if not user.account_active:
        return api_error('Cannot add an inactive employee to a team.', 400)

    # Cross-organization verification
    if team.organization_id and user.organization_id and team.organization_id != user.organization_id:
        return api_error('Cannot add an employee from another organization to this team.', 403)

    # Check for duplicate membership
    existing = db.session.query(team_members).filter_by(team_id=team.id, user_id=user.id).first()
    if existing:
        return api_error('Employee is already a member of this team.', 409)

    # If user has no organization yet and team belongs to one, attach them
    if not user.organization_id and team.organization_id:
        user.organization_id = team.organization_id

    db.session.execute(
        team_members.insert().values(
            team_id=team.id,
            user_id=user.id,
            role=role_in_team,
            joined_at=utc_now()
        )
    )
    db.session.commit()

    return api_success({
        'user_id': user.id,
        'team_id': team.id,
        'role': role_in_team,
        'full_name': user.full_name or user.username,
        'email': user.email,
    }, message=f'{user.full_name or user.username} added to team successfully.', status_code=201)


@teams_bp.route('/<int:team_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
@active_account_required
def remove_team_member(team_id, user_id):
    """Remove member from team. Admin, HR, team lead, or self."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    # Self-leave or manager removal
    if current_user.id != user_id and not _can_manage_team(team):
        return api_error('You do not have permission to remove members from this team.', 403)

    membership = db.session.query(team_members).filter_by(team_id=team.id, user_id=user_id).first()
    if not membership:
        return api_error('User is not a member of this team.', 404)

    db.session.execute(
        team_members.delete().where(
            team_members.c.team_id == team.id,
            team_members.c.user_id == user_id
        )
    )

    # If removed member was the lead, clear team.lead_id
    if team.lead_id == user_id:
        team.lead_id = None

    db.session.commit()
    return api_success(message='Member removed from team successfully.')


# ── Team Tasks ────────────────────────────────────────────────────────────────

@teams_bp.route('/<int:team_id>/tasks', methods=['GET'])
@login_required
def get_team_tasks(team_id):
    """List tasks assigned to this team."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    if not _can_view_team(team):
        return api_error('You do not have permission to view tasks for this team.', 403)

    tasks = Task.query.filter_by(team_id=team.id).order_by(Task.created_at.desc()).all()
    return api_success([t.to_dict() for t in tasks])


@teams_bp.route('/<int:team_id>/tasks', methods=['POST'])
@login_required
@active_account_required
def create_team_task(team_id):
    """Create a task assigned to this team."""
    team = db.session.get(Team, team_id)
    if not team:
        return api_error('Team not found.', 404)

    if not _can_view_team(team):
        return api_error('You do not have permission to create tasks for this team.', 403)

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = (data.get('priority') or 'medium').strip().lower()
    due_date_str = data.get('due_date')
    assigned_to_id = data.get('assigned_to_id')

    if not title:
        return api_error('Task title is required.', 400)

    if len(title) > 200:
        return api_error('Task title must be 200 characters or less.', 400)

    if priority not in VALID_PRIORITIES:
        return api_error('Invalid priority. Choose low, medium, or high.', 400)

    parsed_due_date = None
    if due_date_str:
        try:
            parsed_due_date = datetime.strptime(due_date_str.split('T')[0], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return api_error('Invalid date format. Use YYYY-MM-DD.', 400)

    if assigned_to_id:
        assignee = db.session.get(User, assigned_to_id)
        if not assignee:
            return api_error('Assigned user not found.', 404)
        if not assignee.account_active:
            return api_error('Cannot assign task to a deactivated user.', 400)

    task = Task(
        title=title,
        description=description or None,
        priority=priority,
        status='pending',
        due_date=parsed_due_date,
        user_id=current_user.id,
        team_id=team.id,
        assigned_to_id=assigned_to_id
    )
    db.session.add(task)
    db.session.commit()

    return api_success(task.to_dict(), message='Team task created successfully.', status_code=201)
