from datetime import datetime, date, timezone
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

    # Profile & Contact info
    job_title       = db.Column(db.String(100), nullable=True)
    phone           = db.Column(db.String(30), nullable=True)

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


# ── Team members association table ─────────────────────────────────────────────
team_members = db.Table(
    'team_members',
    db.Column('team_id', db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('role', db.String(20), default='member', nullable=False),  # 'lead', 'member'
    db.Column('joined_at', db.DateTime, default=utc_now, nullable=False),
)


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


class Task(db.Model):
    __tablename__ = 'tasks'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text, nullable=True)
    status       = db.Column(db.String(20), default='pending', nullable=False)  # 'pending', 'completed'
    priority     = db.Column(db.String(10), default='medium', nullable=False)   # 'low', 'medium', 'high'
    due_date     = db.Column(db.Date, nullable=True)
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

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

    @property
    def is_overdue(self):
        if self.status != 'completed' and self.due_date:
            return self.due_date < date.today()
        return False

    def to_dict(self):
        return {
            'id':               self.id,
            'title':            self.title,
            'description':      self.description or '',
            'status':           self.status,
            'priority':         self.priority,
            'due_date':         self.due_date.isoformat() if self.due_date else None,
            'created_at':       self.created_at.isoformat() if self.created_at else None,
            'completed_at':     self.completed_at.isoformat() if self.completed_at else None,
            'is_overdue':       self.is_overdue,
            'user_id':          self.user_id,
            'category_id':      self.category_id,
            'category_name':    self.category.name if self.category else None,
            'team_id':          self.team_id,
            'team_name':        self.team.name if self.team else None,
            'assigned_to_id':   self.assigned_to_id,
            'assigned_to_name': (self.assigned_to.full_name or self.assigned_to.username) if self.assigned_to else None,
        }
