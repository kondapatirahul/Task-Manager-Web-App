from datetime import datetime, date, timezone
import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

def utc_now():
    return datetime.now(timezone.utc)

# ── Role constants ─────────────────────────────────────────────────────────────
# Hierarchy (highest → lowest): super_admin > admin > team_lead > employee
ROLE_SUPER_ADMIN = 'super_admin'
ROLE_ADMIN       = 'admin'
ROLE_TEAM_LEAD   = 'team_lead'
ROLE_EMPLOYEE    = 'employee'
ROLE_HR          = 'hr'  # Permission alias / HR role

ALL_ROLES        = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE)
ADMIN_HR_ROLES   = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR}
MANAGEMENT_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD}
# ── Task Status Constants ───────────────────────────────────────────────────────
STATUS_TODO              = 'todo'
STATUS_IN_PROGRESS       = 'in_progress'
STATUS_BLOCKED           = 'blocked'
STATUS_IN_REVIEW         = 'in_review'
STATUS_COMPLETED         = 'completed'
STATUS_CHANGES_REQUESTED = 'changes_requested'
STATUS_PENDING           = 'pending'  # Legacy alias for todo

COMPANY_TASK_STATUSES = (
    STATUS_TODO,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_IN_REVIEW,
    STATUS_COMPLETED,
    STATUS_CHANGES_REQUESTED,
)

STATUS_LABELS = {
    STATUS_TODO:              'To Do',
    STATUS_PENDING:           'To Do',
    STATUS_IN_PROGRESS:       'In Progress',
    STATUS_BLOCKED:           'Blocked',
    STATUS_IN_REVIEW:         'In Review',
    STATUS_COMPLETED:         'Completed',
    STATUS_CHANGES_REQUESTED: 'Changes Requested',
}

<<<<<<< Updated upstream

class TaskHandover(db.Model):
    __tablename__ = 'task_handovers'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    previous_owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    new_owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    initiated_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    current_progress = db.Column(db.Text, nullable=False)
    next_steps = db.Column(db.Text, nullable=False)
    resolution_reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
=======
<<<<<<< Updated upstream
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    slug       = db.Column(db.String(100), unique=True, nullable=True)
>>>>>>> Stashed changes
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    task = db.relationship('Task', back_populates='handovers')
    previous_owner = db.relationship('User', foreign_keys=[previous_owner_id])
    new_owner = db.relationship('User', foreign_keys=[new_owner_id])
    initiated_by = db.relationship('User', foreign_keys=[initiated_by_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])
    attachments = db.relationship(
'TaskHandoverAttachment', back_populates='handover',
lazy='dynamic', cascade='all, delete-orphan',
    )


class TaskHandoverAttachment(db.Model):
    __tablename__ = 'task_handover_attachments'

    id = db.Column(db.Integer, primary_key=True)
    handover_id = db.Column(db.Integer, db.ForeignKey('task_handovers.id', ondelete='CASCADE'), nullable=False)
    attachment_id = db.Column(db.Integer, db.ForeignKey('task_attachments.id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
db.UniqueConstraint('handover_id', 'attachment_id', name='uq_handover_attachment'),
    )

    handover = db.relationship('TaskHandover', back_populates='attachments')
    attachment = db.relationship('TaskAttachment')


<<<<<<< Updated upstream
=======
class Team(db.Model):
    __tablename__ = 'teams'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    department_id   = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    lead_id         = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_teams_lead_id'), nullable=True)
    created_at      = db.Column(db.DateTime, default=utc_now, nullable=False)

    lead    = db.relationship('User', foreign_keys=[lead_id], backref='lead_teams')
    members = db.relationship('TeamMember', backref='team', lazy='dynamic', cascade='all, delete-orphan')
    tasks   = db.relationship('Task', backref='team', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'department_id': self.department_id,
            'department_name': self.department.name if self.department else None,
            'organization_id': self.organization_id,
            'lead_id': self.lead_id,
            'lead_name': self.lead.full_name or self.lead.username if self.lead else None,
            'member_count': self.members.count() if hasattr(self.members, 'count') else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TeamMember(db.Model):
    __tablename__ = 'team_members'

    id        = db.Column(db.Integer, primary_key=True)
    team_id   = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role      = db.Column(db.String(20), nullable=False, default='member')
    joined_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship('User', backref='team_memberships')

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'user_id': self.user_id,
            'role': self.role,
            'user_name': self.user.full_name or self.user.username if self.user else None,
            'user_email': self.user.email if self.user else None,
            'user_role': self.user.role if self.user else None,
            'designation': self.user.designation if self.user else None,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
        }


# Compatibility alias for code that performs association-table inserts.
# This references the existing mapped table; it does not define a second table.
team_members = TeamMember.__table__

# ── User Model ─────────────────────────────────────────────────────────────────
=======

>>>>>>> Stashed changes
>>>>>>> Stashed changes

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    full_name     = db.Column(db.String(100), nullable=False, default='')
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Role-based access control — default: employee (lowest privilege)
    role          = db.Column(db.String(20), nullable=False, default=ROLE_EMPLOYEE)

    # Soft-disable: deactivated accounts cannot log in, historical records preserved
    account_active = db.Column(db.Boolean, nullable=False, default=True)

    # Organization & Department association
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', use_alter=True, name='fk_users_org', ondelete='SET NULL'), nullable=True)
    department_id   = db.Column(db.Integer, db.ForeignKey('departments.id', use_alter=True, name='fk_users_dept', ondelete='SET NULL'), nullable=True)

<<<<<<< Updated upstream
    # Profile & Contact info
    job_title       = db.Column(db.String(100), nullable=True)
    phone           = db.Column(db.String(30), nullable=True)
    weekly_capacity_hours = db.Column(db.Float, nullable=False, default=40.0)
=======
<<<<<<< Updated upstream
    @property
    def job_title(self):
        return self.designation
=======
    # Profile & Contact info
    job_title       = db.Column(db.String(100), nullable=True)
    phone           = db.Column(db.String(30), nullable=True)
>>>>>>> Stashed changes
>>>>>>> Stashed changes

    # Reporting relationship (Manager / Reports To hierarchy)
    reports_to_id   = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_users_reports_to', ondelete='SET NULL'), nullable=True)
    reports_to      = db.relationship('User', remote_side=[id], foreign_keys=[reports_to_id],
                                      backref=db.backref('direct_reports', lazy='dynamic'))

    # Relationships
    organization    = db.relationship('Organization', foreign_keys=[organization_id], back_populates='members')
    department      = db.relationship('Department', foreign_keys=[department_id], back_populates='members')

    tasks      = db.relationship('Task', foreign_keys='Task.user_id', backref='user', lazy='dynamic',
                                 cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='user', lazy='dynamic',
                                 cascade='all, delete-orphan')

    # ── Flask-Login requirement ────────────────────────────────────────────────
    # Override UserMixin.is_active to honour our account_active column.
    # Flask-Login checks is_active and rejects deactivated users at the login gate.
    @property
    def is_active(self):
        return bool(self.account_active)

    # ── Role helper properties ─────────────────────────────────────────────────
    @property
    def is_super_admin(self):
        return self.role == ROLE_SUPER_ADMIN

    @property
    def is_admin(self):
        return self.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN)

    @property
    def is_admin_or_hr(self):
        return self.role in ADMIN_HR_ROLES

    @property
    def is_management(self):
        """True for super_admin, admin, hr, and team_lead."""
        return self.role in MANAGEMENT_ROLES

    def has_role(self, *roles):
        """Return True if this user's role is among the given roles."""
        return self.role in roles

    # ── Credentials ───────────────────────────────────────────────────────────
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self):
        teams_list = []
        if hasattr(self, 'teams') and self.teams:
            try:
                teams_list = [{'id': t.id, 'name': t.name} for t in self.teams]
            except Exception:
                teams_list = []

        return {
            'id':                self.id,
            'full_name':         self.full_name or self.username,
            'username':          self.username,
            'email':             self.email,
            'role':              self.role,
            'account_active':    self.account_active,
            'organization_id':   self.organization_id,
            'organization_name': self.organization.name if self.organization else None,
            'department_id':     self.department_id,
            'department_name':   self.department.name if self.department else None,
            'job_title':         self.job_title or '',
            'phone':             self.phone or '',
            'reports_to_id':     self.reports_to_id,
            'reports_to_name':   (self.reports_to.full_name or self.reports_to.username) if self.reports_to else None,
            'teams':             teams_list,
            'created_at':        self.created_at.isoformat() if self.created_at else None,
        }


<<<<<<< Updated upstream
=======
<<<<<<< Updated upstream
# ── Category Model ─────────────────────────────────────────────────────────────
=======
>>>>>>> Stashed changes
# ── Team members association table ─────────────────────────────────────────────
team_members = db.Table(
    'team_members',
    db.Column('team_id', db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('role', db.String(20), default='member', nullable=False),  # 'lead', 'member'
    db.Column('joined_at', db.DateTime, default=utc_now, nullable=False),
)

<<<<<<< Updated upstream
decision_tasks = db.Table(
    'decision_tasks',
    db.Column('decision_id', db.Integer, db.ForeignKey('project_decisions.id', ondelete='CASCADE'), primary_key=True),
    db.Column('task_id', db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True),
)

=======
>>>>>>> Stashed changes

class Organization(db.Model):
    __tablename__ = 'organizations'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, default=utc_now, nullable=False)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_org_created_by', ondelete='SET NULL'), nullable=True)
    created_by    = db.relationship('User', foreign_keys=[created_by_id])

    departments = db.relationship('Department', back_populates='organization', lazy='dynamic',
                                  cascade='all, delete-orphan')
    teams       = db.relationship('Team', back_populates='organization', lazy='dynamic',
                                  cascade='all, delete-orphan')
    members     = db.relationship('User', back_populates='organization',
                                  foreign_keys='User.organization_id', lazy='dynamic')

    def to_dict(self):
        return {
            'id':                self.id,
            'name':              self.name,
            'description':       self.description or '',
            'created_by_id':     self.created_by_id,
            'created_at':        self.created_at.isoformat() if self.created_at else None,
            'departments_count': self.departments.count() if hasattr(self.departments, 'count') else 0,
            'teams_count':       self.teams.count() if hasattr(self.teams, 'count') else 0,
            'members_count':     self.members.count() if hasattr(self.members, 'count') else 0,
        }


class Department(db.Model):
    __tablename__ = 'departments'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    description     = db.Column(db.Text, nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True)
    head_id         = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_dept_head', ondelete='SET NULL'), nullable=True)
    created_at      = db.Column(db.DateTime, default=utc_now, nullable=False)

    organization = db.relationship('Organization', back_populates='departments', foreign_keys=[organization_id])
    head         = db.relationship('User', foreign_keys=[head_id])
    members      = db.relationship('User', back_populates='department',
                                   foreign_keys='User.department_id', lazy='dynamic')
    teams        = db.relationship('Team', back_populates='department', lazy='dynamic')

    def to_dict(self):
        return {
            'id':                self.id,
            'name':              self.name,
            'description':       self.description or '',
            'organization_id':   self.organization_id,
            'organization_name': self.organization.name if self.organization else None,
            'head_id':           self.head_id,
            'head_name':         (self.head.full_name or self.head.username) if self.head else None,
            'members_count':     self.members.count() if hasattr(self.members, 'count') else 0,
            'teams_count':       self.teams.count() if hasattr(self.teams, 'count') else 0,
            'created_at':        self.created_at.isoformat() if self.created_at else None,
        }


class Team(db.Model):
    __tablename__ = 'teams'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    description     = db.Column(db.Text, nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True)
    department_id   = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True)
    lead_id         = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at      = db.Column(db.DateTime, default=utc_now, nullable=False)

    organization = db.relationship('Organization', back_populates='teams', foreign_keys=[organization_id])
    department   = db.relationship('Department', back_populates='teams', foreign_keys=[department_id])
    lead         = db.relationship('User', foreign_keys=[lead_id])
    members      = db.relationship('User', secondary=team_members,
                                   backref=db.backref('teams', lazy='dynamic'), lazy='dynamic')
    tasks        = db.relationship('Task', back_populates='team', lazy='dynamic')
<<<<<<< Updated upstream
    decisions    = db.relationship(
        'ProjectDecision', back_populates='team', lazy='dynamic',
        cascade='all, delete-orphan',
    )
=======
>>>>>>> Stashed changes

    def to_dict(self):
        return {
            'id':                self.id,
            'name':              self.name,
            'description':       self.description or '',
            'organization_id':   self.organization_id,
            'organization_name': self.organization.name if self.organization else None,
            'department_id':     self.department_id,
            'department_name':   self.department.name if self.department else None,
            'lead_id':           self.lead_id,
            'lead_name':         (self.lead.full_name or self.lead.username) if self.lead else None,
            'lead_email':        self.lead.email if self.lead else None,
            'members_count':     self.members.count() if hasattr(self.members, 'count') else 0,
            'tasks_count':       self.tasks.count() if hasattr(self.tasks, 'count') else 0,
            'created_at':        self.created_at.isoformat() if self.created_at else None,
        }

<<<<<<< Updated upstream
=======
>>>>>>> Stashed changes
>>>>>>> Stashed changes

class Category(db.Model):
    __tablename__ = 'categories'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(50), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    tasks = db.relationship('Task', backref='category', lazy='dynamic')

    def to_dict(self):
        return {
            'id':         self.id,
            'name':       self.name,
            'user_id':    self.user_id,
            'task_count': self.tasks.count() if hasattr(self.tasks, 'count') else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


<<<<<<< Updated upstream
class Goal(db.Model):
    __tablename__ = 'goals'
=======
<<<<<<< Updated upstream
# ── Task & Lifecycle Models ────────────────────────────────────────────────────
>>>>>>> Stashed changes

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    goal_type = db.Column(db.String(40), nullable=False)
    target_value = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    owner = db.relationship('User', backref=db.backref('goals', lazy='dynamic'))


class FocusSession(db.Model):
    __tablename__ = 'focus_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='active', index=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_resumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    paused_at = db.Column(db.DateTime(timezone=True), nullable=True)
    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)
    active_seconds = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    user = db.relationship('User', backref=db.backref('focus_sessions', lazy='dynamic'))
    task = db.relationship('Task', backref=db.backref('focus_sessions', lazy='dynamic'))

    __table_args__ = (
        db.CheckConstraint("status IN ('active', 'paused', 'finished', 'interrupted')", name='ck_focus_session_status'),
        db.CheckConstraint('active_seconds >= 0', name='ck_focus_session_seconds'),
    )


class WorkflowTemplate(db.Model):
    __tablename__ = 'workflow_templates'

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    checklist_json = db.Column(db.Text, nullable=False, default='[]')
    default_priority = db.Column(db.String(10), nullable=False, default='medium')
    visibility = db.Column(db.String(20), nullable=False, default='private', index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    owner = db.relationship('User', foreign_keys=[owner_id])
    organization = db.relationship('Organization')
    generated_tasks = db.relationship(
        'WorkflowTemplateTask', back_populates='template',
        lazy='dynamic', cascade='all, delete-orphan',
    )

    @property
    def checklist(self):
        try:
            value = json.loads(self.checklist_json or '[]')
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []


class WorkflowTemplateTask(db.Model):
    __tablename__ = 'workflow_template_tasks'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('workflow_templates.id', ondelete='CASCADE'), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, unique=True)
    item_index = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    template = db.relationship('WorkflowTemplate', back_populates='generated_tasks')
    task = db.relationship('Task')


class AutomationRule(db.Model):
    __tablename__ = 'automation_rules'

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    source_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=True, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('workflow_templates.id', ondelete='SET NULL'), nullable=True)
    rule_type = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    schedule = db.Column(db.String(20), nullable=True)
    next_run_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    config_json = db.Column(db.Text, nullable=False, default='{}')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    owner = db.relationship('User', foreign_keys=[owner_id])
    organization = db.relationship('Organization')
    source_task = db.relationship('Task', foreign_keys=[source_task_id])
    template = db.relationship('WorkflowTemplate')
    executions = db.relationship(
        'AutomationExecution', back_populates='rule',
        lazy='dynamic', cascade='all, delete-orphan',
    )


class AutomationExecution(db.Model):
    __tablename__ = 'automation_executions'

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('automation_rules.id', ondelete='CASCADE'), nullable=False, index=True)
    execution_key = db.Column(db.String(255), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default='running')
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    result_json = db.Column(db.Text, nullable=True)

    rule = db.relationship('AutomationRule', back_populates='executions')


=======
>>>>>>> Stashed changes
class TaskStatusHistory(db.Model):
    __tablename__ = 'task_status_history'

    id            = db.Column(db.Integer, primary_key=True)
    task_id       = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    old_status    = db.Column(db.String(30), nullable=True)
    new_status    = db.Column(db.String(30), nullable=False)
    comment       = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, default=utc_now, nullable=False)

    task       = db.relationship('Task', backref=db.backref('status_history', lazy='dynamic', cascade='all, delete-orphan', order_by='TaskStatusHistory.created_at.desc()'))
    changed_by = db.relationship('User', foreign_keys=[changed_by_id])

    def to_dict(self):
        return {
            'id':              self.id,
            'task_id':         self.task_id,
            'changed_by_id':   self.changed_by_id,
            'changed_by_name': (self.changed_by.full_name or self.changed_by.username) if self.changed_by else 'System',
            'changed_by_role': self.changed_by.role if self.changed_by else None,
            'old_status':      self.old_status,
            'new_status':      self.new_status,
            'comment':         self.comment or '',
            'created_at':      self.created_at.isoformat() if self.created_at else None,
        }


<<<<<<< Updated upstream
class TaskDependency(db.Model):
    __tablename__ = 'task_dependencies'

    id = db.Column(db.Integer, primary_key=True)
    blocked_task_id = db.Column(
        db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    blocking_task_id = db.Column(
        db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            'blocked_task_id', 'blocking_task_id',
            name='uq_task_dependency_pair',
        ),
        db.CheckConstraint(
            'blocked_task_id != blocking_task_id',
            name='ck_task_dependency_not_self',
        ),
    )

    blocked_task = db.relationship(
        'Task', foreign_keys=[blocked_task_id],
        back_populates='blocking_dependencies',
    )
    blocking_task = db.relationship(
        'Task', foreign_keys=[blocking_task_id],
        back_populates='blocked_dependencies',
    )
    created_by = db.relationship('User', foreign_keys=[created_by_id])


class Notification(db.Model):
    __tablename__ = 'notifications'
=======
<<<<<<< Updated upstream
class SubTask(db.Model):
    __tablename__ = 'subtasks'
>>>>>>> Stashed changes

    id           = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    actor_id     = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    task_id      = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=True, index=True)
    notification_type = db.Column(db.String(50), nullable=False, index=True)
    title        = db.Column(db.String(120), nullable=False)
    message      = db.Column(db.String(500), nullable=False)
    event_key    = db.Column(db.String(255), nullable=True, unique=True)
    is_read      = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    recipient = db.relationship('User', foreign_keys=[recipient_id])
    actor = db.relationship('User', foreign_keys=[actor_id])
    task = db.relationship('Task', foreign_keys=[task_id])

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.notification_type,
            'title': self.title,
            'message': self.message,
            'task_id': self.task_id,
            'actor_name': (self.actor.full_name or self.actor.username) if self.actor else None,
            'is_read': bool(self.is_read),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Activity(db.Model):
    __tablename__ = 'activities'

<<<<<<< Updated upstream
    id          = db.Column(db.Integer, primary_key=True)
    actor_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    task_id     = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=True, index=True)
    activity_type = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(500), nullable=False)
    event_key   = db.Column(db.String(255), nullable=True, unique=True)
    created_at  = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    actor = db.relationship('User', foreign_keys=[actor_id])
    task = db.relationship('Task', foreign_keys=[task_id])

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.activity_type,
            'description': self.description,
            'actor_name': (self.actor.full_name or self.actor.username) if self.actor else 'System',
            'task_id': self.task_id,
            'task_title': self.task.title if self.task else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TaskComment(db.Model):
    __tablename__ = 'task_comments'
=======
class TaskMessage(db.Model):
    __tablename__ = 'task_messages'
=======
class TaskComment(db.Model):
    __tablename__ = 'task_comments'
>>>>>>> Stashed changes
>>>>>>> Stashed changes

    id         = db.Column(db.Integer, primary_key=True)
    task_id    = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    user        = db.relationship('User', foreign_keys=[user_id])
    attachments = db.relationship('TaskAttachment', backref='comment', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        from app.file_utils import extract_mentions
        raw_mentions = extract_mentions(self.content)
        mention_users = []
        if raw_mentions:
            matched = User.query.filter(User.username.in_(raw_mentions)).all()
            mention_users = [{'id': u.id, 'username': u.username, 'full_name': u.full_name or u.username} for u in matched]

        return {
            'id':          self.id,
            'task_id':     self.task_id,
            'user_id':     self.user_id,
            'author_name': (self.user.full_name or self.user.username) if self.user else 'Former Member',
            'author_role': self.user.role if self.user else None,
            'content':     self.content,
            'mentions':    mention_users,
            'attachments': [a.to_dict() for a in self.attachments.all()] if hasattr(self, 'attachments') else [],
            'created_at':  self.created_at.isoformat() if self.created_at else None,
            'updated_at':  self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskSubmission(db.Model):
    __tablename__ = 'task_submissions'

    id              = db.Column(db.Integer, primary_key=True)
    task_id         = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    summary         = db.Column(db.Text, nullable=False)
    status          = db.Column(db.String(30), default='pending_review', nullable=False)  # 'pending_review', 'approved', 'changes_requested'
    reviewed_by_id  = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at     = db.Column(db.DateTime, nullable=True)
    review_feedback = db.Column(db.Text, nullable=True)
    created_at      = db.Column(db.DateTime, default=utc_now, nullable=False)

    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    reviewed_by  = db.relationship('User', foreign_keys=[reviewed_by_id])
    attachments  = db.relationship('TaskAttachment', backref='submission', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':                self.id,
            'task_id':           self.task_id,
            'submitted_by_id':   self.submitted_by_id,
            'submitted_by_name': (self.submitted_by.full_name or self.submitted_by.username) if self.submitted_by else 'Unknown',
            'submitted_by_role': self.submitted_by.role if self.submitted_by else None,
            'summary':           self.summary,
            'status':            self.status,
            'reviewed_by_id':    self.reviewed_by_id,
            'reviewed_by_name':  (self.reviewed_by.full_name or self.reviewed_by.username) if self.reviewed_by else None,
            'reviewed_by_role':  self.reviewed_by.role if self.reviewed_by else None,
            'reviewed_at':       self.reviewed_at.isoformat() if self.reviewed_at else None,
            'review_feedback':   self.review_feedback or '',
            'attachments':       [a.to_dict() for a in self.attachments.all()] if hasattr(self, 'attachments') else [],
            'created_at':        self.created_at.isoformat() if self.created_at else None,
        }


class TaskAttachment(db.Model):
    __tablename__ = 'task_attachments'

    id                = db.Column(db.Integer, primary_key=True)
    task_id           = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    uploader_id       = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    comment_id        = db.Column(db.Integer, db.ForeignKey('task_comments.id', ondelete='CASCADE'), nullable=True)
    submission_id     = db.Column(db.Integer, db.ForeignKey('task_submissions.id', ondelete='CASCADE'), nullable=True)

    attachment_type   = db.Column(db.String(20), default='comment', nullable=False)  # 'reference', 'comment', 'submission'
    original_filename = db.Column(db.String(255), nullable=False)
    storage_name      = db.Column(db.String(255), unique=True, nullable=False)
    file_size         = db.Column(db.Integer, nullable=False)
    file_type         = db.Column(db.String(100), nullable=False)
    file_extension    = db.Column(db.String(20), nullable=False)
    created_at        = db.Column(db.DateTime, default=utc_now, nullable=False)

    uploader = db.relationship('User', foreign_keys=[uploader_id])

    def to_dict(self):
        from app.file_utils import format_file_size
        ext = (self.file_extension or '').lower()
        return {
            'id':                self.id,
            'task_id':           self.task_id,
            'uploader_id':       self.uploader_id,
            'uploader_name':     (self.uploader.full_name or self.uploader.username) if self.uploader else 'Unknown',
            'uploader_role':     self.uploader.role if self.uploader else None,
            'comment_id':        self.comment_id,
            'submission_id':     self.submission_id,
            'attachment_type':   self.attachment_type,
            'original_filename': self.original_filename,
            'file_size':         self.file_size,
            'file_size_human':   format_file_size(self.file_size),
            'file_type':         self.file_type,
            'file_extension':    ext,
            'is_image':          ext in ('png', 'jpg', 'jpeg'),
            'is_previewable':    ext in ('png', 'jpg', 'jpeg', 'pdf', 'txt'),
            'download_url':      f"/api/tasks/{self.task_id}/attachments/{self.id}/download",
            'preview_url':       f"/api/tasks/{self.task_id}/attachments/{self.id}/preview",
            'created_at':        self.created_at.isoformat() if self.created_at else None,
        }


class Task(db.Model):
    __tablename__ = 'tasks'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text, nullable=True)
    status       = db.Column(db.String(30), default='pending', nullable=False)
    priority     = db.Column(db.String(10), default='medium', nullable=False)   # 'low', 'medium', 'high'
    start_date   = db.Column(db.Date, nullable=True)
    due_date     = db.Column(db.Date, nullable=True)
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False)
<<<<<<< Updated upstream
    updated_at   = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    estimated_effort_hours = db.Column(db.Float, nullable=True)
=======
<<<<<<< Updated upstream
=======
    updated_at   = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
>>>>>>> Stashed changes
>>>>>>> Stashed changes

    # Workflow & company fields
    acceptance_criteria  = db.Column(db.Text, nullable=True)
    submission_notes     = db.Column(db.Text, nullable=True)
    review_notes         = db.Column(db.Text, nullable=True)
    is_recurring         = db.Column(db.Boolean, default=False, nullable=False)
    recurrence_interval  = db.Column(db.String(20), nullable=True)

<<<<<<< Updated upstream
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id    = db.Column(db.Integer,
                               db.ForeignKey('categories.id', ondelete='SET NULL'),
                               nullable=True)
    team_id        = db.Column(db.Integer,
                               db.ForeignKey('teams.id', ondelete='SET NULL'),
                               nullable=True)
    assigned_to_id = db.Column(db.Integer,
                               db.ForeignKey('users.id', ondelete='SET NULL'),
                               nullable=True)

    team        = db.relationship('Team', back_populates='tasks', foreign_keys=[team_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id],
                                  backref=db.backref('assigned_tasks', lazy='dynamic'))

    comments    = db.relationship('TaskComment', backref='task', lazy='dynamic', cascade='all, delete-orphan', order_by='TaskComment.created_at.asc()')
    attachments = db.relationship('TaskAttachment', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    submissions = db.relationship('TaskSubmission', backref='task', lazy='dynamic', cascade='all, delete-orphan', order_by='TaskSubmission.created_at.desc()')
    blocking_dependencies = db.relationship(
        'TaskDependency', foreign_keys='TaskDependency.blocked_task_id',
        back_populates='blocked_task', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    blocked_dependencies = db.relationship(
        'TaskDependency', foreign_keys='TaskDependency.blocking_task_id',
        back_populates='blocking_task', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    handovers = db.relationship(
        'TaskHandover', back_populates='task', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    decisions = db.relationship(
        'ProjectDecision', secondary=decision_tasks,
        back_populates='linked_tasks', lazy='dynamic',
    )

    @property
    def is_overdue(self):
        if self.status != 'completed' and self.due_date:
            return self.due_date < date.today()
        return False

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status.replace('_', ' ').title())

    def to_dict(self, include_history=False, include_collaboration=False, dependency_user=None):
        data = {
            'id':                  self.id,
            'title':               self.title,
            'description':         self.description or '',
            'status':              self.status,
            'status_label':        self.status_label,
            'priority':            self.priority,
            'start_date':          self.start_date.isoformat() if self.start_date else None,
            'due_date':            self.due_date.isoformat() if self.due_date else None,
            'estimated_effort_hours': self.estimated_effort_hours,
            'created_at':          self.created_at.isoformat() if self.created_at else None,
            'updated_at':          self.updated_at.isoformat() if self.updated_at else None,
            'completed_at':        self.completed_at.isoformat() if self.completed_at else None,
            'is_overdue':          self.is_overdue,
            'acceptance_criteria': self.acceptance_criteria or '',
            'submission_notes':    self.submission_notes or '',
            'review_notes':        self.review_notes or '',
            'is_recurring':        bool(self.is_recurring),
            'recurrence_interval': self.recurrence_interval or '',
            'user_id':             self.user_id,
            'creator_id':          self.user_id,
            'creator_name':        (self.user.full_name or self.user.username) if self.user else None,
            'creator_role':        self.user.role if self.user else None,
            'category_id':         self.category_id,
            'category_name':       self.category.name if self.category else None,
            'team_id':             self.team_id,
            'team_name':           self.team.name if self.team else None,
            'assigned_to_id':      self.assigned_to_id,
            'assigned_to_name':    (self.assigned_to.full_name or self.assigned_to.username) if self.assigned_to else None,
            'assigned_to_email':   self.assigned_to.email if self.assigned_to else None,
            'assigned_to_role':    self.assigned_to.role if self.assigned_to else None,
=======
<<<<<<< Updated upstream
    def to_dict(self):
        submitter_name = (self.submitter.full_name or self.submitter.username) if self.submitter else None
        reviewer_name = (self.reviewer.full_name or self.reviewer.username) if self.reviewer else None
        return {
            'id': self.id,
            'task_id': self.task_id,
            'user_id': self.user_id,
            'submitter_name': submitter_name,
            'notes': self.notes or '',
            'summary': self.notes or '',
            'status': self.status,
            'review_notes': self.review_notes or '',
            'review_feedback': self.review_notes or '',
            'reviewed_by': self.reviewed_by,
            'reviewer_name': reviewer_name,
            'reviewed_by_name': reviewer_name,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'attachments': [a.to_dict() for a in self.attachments] if self.attachments else [],
>>>>>>> Stashed changes
        }

        blocking = self.blocking_dependencies.all()
        blocked = self.blocked_dependencies.all()
        if dependency_user is not None:
            from app.services.workload import authorized_task_query
            visible_ids = {
                row[0] for row in authorized_task_query(dependency_user).with_entities(Task.id).filter(
                    Task.id.in_([
                        dependency.blocking_task_id for dependency in blocking
                    ] + [
                        dependency.blocked_task_id for dependency in blocked
                    ])
                ).all()
            }
            blocking = [
                dependency for dependency in blocking
                if dependency.blocking_task_id in visible_ids
            ]
            blocked = [
                dependency for dependency in blocked
                if dependency.blocked_task_id in visible_ids
            ]
        unfinished_blockers = [
            dependency.blocking_task for dependency in blocking
            if dependency.blocking_task and dependency.blocking_task.status != STATUS_COMPLETED
        ]
        data['dependency_count'] = len(blocking) + len(blocked)
        data['is_blocked_by_dependencies'] = any(
            dependency.blocking_task and dependency.blocking_task.status != STATUS_COMPLETED
            for dependency in blocking
        )
        data['dependency_ready'] = bool(blocking) and not unfinished_blockers
        data['dependency_blockers'] = [
            {
                'id': blocker.id,
                'title': blocker.title,
                'status': blocker.status,
                'status_label': blocker.status_label,
                'task_url': f'/tasks/{blocker.id}',
            }
            for blocker in unfinished_blockers
        ]

        # Collaboration counts & reference attachments
        if hasattr(self, 'attachments'):
            ref_attachments = self.attachments.filter_by(attachment_type='reference').all()
            data['reference_attachments'] = [a.to_dict() for a in ref_attachments]
            data['attachments_count'] = self.attachments.count()
        else:
            data['reference_attachments'] = []
            data['attachments_count'] = 0

        data['comments_count'] = self.comments.count() if hasattr(self, 'comments') else 0
        data['submissions_count'] = self.submissions.count() if hasattr(self, 'submissions') else 0

        if include_history and hasattr(self, 'status_history'):
            data['status_history'] = [h.to_dict() for h in self.status_history.all()]

        if include_collaboration:
            data['comments'] = [c.to_dict() for c in self.comments.all()] if hasattr(self, 'comments') else []
            data['submissions'] = [s.to_dict() for s in self.submissions.all()] if hasattr(self, 'submissions') else []
            data['attachments'] = [a.to_dict() for a in self.attachments.all()] if hasattr(self, 'attachments') else []
            data['dependencies'] = {
                'blocked_by': [
                    dependency_to_dict(dependency, dependency.blocking_task)
                    for dependency in blocking if dependency.blocking_task
                ],
                'blocks': [
                    dependency_to_dict(dependency, dependency.blocked_task)
                    for dependency in blocked if dependency.blocked_task
                ],
            }

        return data


class ProjectDecision(db.Model):
    __tablename__ = 'project_decisions'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=False)
    rationale = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='proposed', index=True)
    alternatives = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    team = db.relationship('Team', back_populates='decisions')
    author = db.relationship('User', foreign_keys=[author_id])
    linked_tasks = db.relationship(
        'Task', secondary=decision_tasks,
        back_populates='decisions', lazy='dynamic',
    )
    history = db.relationship(
        'DecisionHistory', back_populates='decision',
        lazy='dynamic', cascade='all, delete-orphan',
        order_by='DecisionHistory.created_at.desc()',
    )


class DecisionHistory(db.Model):
    __tablename__ = 'decision_history'

    id = db.Column(db.Integer, primary_key=True)
    decision_id = db.Column(db.Integer, db.ForeignKey('project_decisions.id', ondelete='CASCADE'), nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=False)
    rationale = db.Column(db.Text, nullable=False)
    alternatives = db.Column(db.Text, nullable=True)
    change_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    decision = db.relationship('ProjectDecision', back_populates='history')
    changed_by = db.relationship('User', foreign_keys=[changed_by_id])


<<<<<<< Updated upstream
def dependency_to_dict(dependency, task):
    return {
        'id': dependency.id,
        'task_id': task.id,
        'title': task.title,
        'status': task.status,
        'status_label': task.status_label,
        'task_url': f'/tasks/{task.id}',
        'created_at': dependency.created_at.isoformat() if dependency.created_at else None,
    }
=======
=======
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id    = db.Column(db.Integer,
                               db.ForeignKey('categories.id', ondelete='SET NULL'),
                               nullable=True)
    team_id        = db.Column(db.Integer,
                               db.ForeignKey('teams.id', ondelete='SET NULL'),
                               nullable=True)
    assigned_to_id = db.Column(db.Integer,
                               db.ForeignKey('users.id', ondelete='SET NULL'),
                               nullable=True)

    team        = db.relationship('Team', back_populates='tasks', foreign_keys=[team_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id],
                                  backref=db.backref('assigned_tasks', lazy='dynamic'))

    comments    = db.relationship('TaskComment', backref='task', lazy='dynamic', cascade='all, delete-orphan', order_by='TaskComment.created_at.asc()')
    attachments = db.relationship('TaskAttachment', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    submissions = db.relationship('TaskSubmission', backref='task', lazy='dynamic', cascade='all, delete-orphan', order_by='TaskSubmission.created_at.desc()')

    @property
    def is_overdue(self):
        if self.status != 'completed' and self.due_date:
            return self.due_date < date.today()
        return False

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status.replace('_', ' ').title())

    def to_dict(self, include_history=False, include_collaboration=False):
        data = {
            'id':                  self.id,
            'title':               self.title,
            'description':         self.description or '',
            'status':              self.status,
            'status_label':        self.status_label,
            'priority':            self.priority,
            'start_date':          self.start_date.isoformat() if self.start_date else None,
            'due_date':            self.due_date.isoformat() if self.due_date else None,
            'created_at':          self.created_at.isoformat() if self.created_at else None,
            'updated_at':          self.updated_at.isoformat() if self.updated_at else None,
            'completed_at':        self.completed_at.isoformat() if self.completed_at else None,
            'is_overdue':          self.is_overdue,
            'acceptance_criteria': self.acceptance_criteria or '',
            'submission_notes':    self.submission_notes or '',
            'review_notes':        self.review_notes or '',
            'is_recurring':        bool(self.is_recurring),
            'recurrence_interval': self.recurrence_interval or '',
            'user_id':             self.user_id,
            'creator_id':          self.user_id,
            'creator_name':        (self.user.full_name or self.user.username) if self.user else None,
            'creator_role':        self.user.role if self.user else None,
            'category_id':         self.category_id,
            'category_name':       self.category.name if self.category else None,
            'team_id':             self.team_id,
            'team_name':           self.team.name if self.team else None,
            'assigned_to_id':      self.assigned_to_id,
            'assigned_to_name':    (self.assigned_to.full_name or self.assigned_to.username) if self.assigned_to else None,
            'assigned_to_email':   self.assigned_to.email if self.assigned_to else None,
            'assigned_to_role':    self.assigned_to.role if self.assigned_to else None,
        }

        # Collaboration counts & reference attachments
        if hasattr(self, 'attachments'):
            ref_attachments = self.attachments.filter_by(attachment_type='reference').all()
            data['reference_attachments'] = [a.to_dict() for a in ref_attachments]
            data['attachments_count'] = self.attachments.count()
        else:
            data['reference_attachments'] = []
            data['attachments_count'] = 0

        data['comments_count'] = self.comments.count() if hasattr(self, 'comments') else 0
        data['submissions_count'] = self.submissions.count() if hasattr(self, 'submissions') else 0

        if include_history and hasattr(self, 'status_history'):
            data['status_history'] = [h.to_dict() for h in self.status_history.all()]

        if include_collaboration:
            data['comments'] = [c.to_dict() for c in self.comments.all()] if hasattr(self, 'comments') else []
            data['submissions'] = [s.to_dict() for s in self.submissions.all()] if hasattr(self, 'submissions') else []
            data['attachments'] = [a.to_dict() for a in self.attachments.all()] if hasattr(self, 'attachments') else []

        return data
>>>>>>> Stashed changes
>>>>>>> Stashed changes
