"""
Organization, Department, Team, and Audit Log API routes.
"""
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import (
    Organization, Department, Team, TeamMember, User, AuditLog,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
)
from app.routes.utils import api_success, api_error, roles_required, active_account_required, log_audit

org_bp = Blueprint('organization', __name__, url_prefix='/api/organization')


@org_bp.route('', methods=['GET'])
@login_required
@active_account_required
def get_organization():
    """Get current user's organization or the default organization."""
    org = None
    if current_user.organization_id:
        org = Organization.query.get(current_user.organization_id)
    if not org:
        org = Organization.query.first()
        if org and not current_user.organization_id:
            current_user.organization_id = org.id
            db.session.commit()

    if not org:
        return api_error('Organization not configured.', 404)

    return api_success(org.to_dict())


# ── Departments ────────────────────────────────────────────────────────────────

@org_bp.route('/departments', methods=['GET', 'POST'])
@login_required
@active_account_required
def departments():
    if request.method == 'GET':
        org_id = current_user.organization_id or 1
        depts = Department.query.filter(
            (Department.organization_id == org_id) | (Department.organization_id.is_(None))
        ).order_by(Department.name.asc()).all()
        return api_success([d.to_dict() for d in depts])

    # POST — create department
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return api_error('Admin permissions required to create departments.', 403)

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name or len(name) < 2 or len(name) > 100:
        return api_error('Department name must be between 2 and 100 characters.', 400)

    org_id = current_user.organization_id or 1
    existing = Department.query.filter_by(name=name, organization_id=org_id).first()
    if existing:
        return api_error('A department with this name already exists.', 409)

    dept = Department(name=name, organization_id=org_id)
    db.session.add(dept)
    db.session.commit()

    log_audit('department_created', 'Department', dept.id, f'Created department: {dept.name}')
    return api_success(dept.to_dict(), message='Department created successfully.', status_code=201)


# ── Teams ──────────────────────────────────────────────────────────────────────

@org_bp.route('/teams', methods=['GET', 'POST'])
@login_required
@active_account_required
def teams():
    if request.method == 'GET':
        org_id = current_user.organization_id or 1
        team_query = Team.query.filter(
            (Team.organization_id == org_id) | (Team.organization_id.is_(None))
        )
        if current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
            pass
        elif current_user.is_team_lead:
            team_query = team_query.filter(Team.lead_id == current_user.id)
        else:
            team_query = team_query.filter(Team.id.in_([m.team_id for m in TeamMember.query.filter_by(user_id=current_user.id).all()]))
        team_list = team_query.order_by(Team.name.asc()).all()
        return api_success([t.to_dict() for t in team_list])

    # POST — create team
    if not current_user.is_management:
        return api_error('Management permissions required to create teams.', 403)

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name or len(name) < 2 or len(name) > 100:
        return api_error('Team name must be between 2 and 100 characters.', 400)

    dept_id = data.get('department_id')
    lead_id = data.get('lead_id') or current_user.id
    org_id = current_user.organization_id or 1

    existing = Team.query.filter_by(name=name, organization_id=org_id).first()
    if existing:
        return api_error('A team with this name already exists.', 409)

    team = Team(
        name=name,
        department_id=int(dept_id) if dept_id else None,
        lead_id=int(lead_id) if lead_id else None,
        organization_id=org_id
    )
    db.session.add(team)
    db.session.flush()

    # Automatically add lead as team member
    if team.lead_id:
        db.session.add(TeamMember(team_id=team.id, user_id=team.lead_id))

    db.session.commit()
    log_audit('team_created', 'Team', team.id, f'Created team: {team.name}')
    return api_success(team.to_dict(), message='Team created successfully.', status_code=201)


# ── Team Members ───────────────────────────────────────────────────────────────

@org_bp.route('/teams/<int:team_id>/members', methods=['GET', 'POST'])
@login_required
@active_account_required
def team_members(team_id):
    team = Team.query.get_or_404(team_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        if current_user.is_team_lead:
            if team.lead_id != current_user.id:
                return api_error('You can only access teams you lead.', 403)
        elif not TeamMember.query.filter_by(team_id=team.id, user_id=current_user.id).first():
            return api_error('You are not a member of this team.', 403)

    if request.method == 'GET':
        members = TeamMember.query.filter_by(team_id=team.id).all()
        return api_success([m.to_dict() for m in members])

    # POST — add member
    if not current_user.is_management:
        return api_error('Permission denied to add team members.', 403)

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return api_error('User ID is required.', 400)

    user = User.query.get(user_id)
    if not user or not user.account_active:
        return api_error('Active user not found.', 404)

    existing = TeamMember.query.filter_by(team_id=team.id, user_id=user.id).first()
    if existing:
        return api_error('User is already a member of this team.', 409)

    membership = TeamMember(team_id=team.id, user_id=user.id)
    user.team_id = team.id
    db.session.add(membership)
    db.session.commit()

    log_audit('team_member_added', 'Team', team.id, f'Added user {user.username} to team {team.name}')
    return api_success(membership.to_dict(), message='Team member added.', status_code=201)


@org_bp.route('/teams/<int:team_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
@active_account_required
def remove_team_member(team_id, user_id):
    if not current_user.is_management:
        return api_error('Permission denied to remove team members.', 403)

    team = Team.query.get_or_404(team_id)
    membership = TeamMember.query.filter_by(team_id=team.id, user_id=user_id).first()
    if not membership:
        return api_error('Team member not found.', 404)

    db.session.delete(membership)
    db.session.commit()

    log_audit('team_member_removed', 'Team', team.id, f'Removed user ID {user_id} from team {team.name}')
    return api_success(message='Team member removed.')


# ── Audit Logs ─────────────────────────────────────────────────────────────────

@org_bp.route('/audit-logs', methods=['GET'])
@login_required
@active_account_required
@roles_required(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def get_audit_logs():
    org_id = current_user.organization_id or 1
    logs = AuditLog.query.filter(
        (AuditLog.organization_id == org_id) | (AuditLog.organization_id.is_(None))
    ).order_by(AuditLog.created_at.desc()).limit(100).all()
    return api_success([log.to_dict() for log in logs])
