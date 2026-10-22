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


# ── Organization & Structure ──────────────────────────────────────────────────

class Organization(db.Model):
    __tablename__ = 'organizations'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    slug       = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    departments = db.relationship('Department', backref='organization', lazy='dynamic', cascade='all, delete-orphan')
    teams       = db.relationship('Team', backref='organization', lazy='dynamic', cascade='all, delete-orphan')
    users       = db.relationship('User', backref='organization', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_count': self.users.count() if hasattr(self.users, 'count') else 0,
            'team_count': self.teams.count() if hasattr(self.teams, 'count') else 0,
        }


class Department(db.Model):
    __tablename__ = 'departments'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    created_at      = db.Column(db.DateTime, default=utc_now, nullable=False)

    teams = db.relationship('Team', backref='department', lazy='dynamic')
    users = db.relationship('User', backref='department', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'organization_id': self.organization_id,
            'team_count': self.teams.count() if hasattr(self.teams, 'count') else 0,
            'user_count': self.users.count() if hasattr(self.users, 'count') else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


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
    joined_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship('User', backref='team_memberships')

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'user_id': self.user_id,
            'user_name': self.user.full_name or self.user.username if self.user else None,
            'user_email': self.user.email if self.user else None,
            'user_role': self.user.role if self.user else None,
            'designation': self.user.designation if self.user else None,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
        }


# ── User Model ─────────────────────────────────────────────────────────────────

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
    attendances = db.relationship('Attendance', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    # ── Flask-Login requirement ────────────────────────────────────────────────
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
        expanded = set(roles)
        if 'admin' in expanded or 'admin_hr' in expanded:
            expanded.add('admin')
            expanded.add('admin_hr')
        return self.role in expanded

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


# ── Category Model ─────────────────────────────────────────────────────────────

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


class TaskComment(db.Model):
    __tablename__ = 'task_comments'

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
    start_date   = db.Column(db.Date, nullable=True)
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at   = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Workflow & company fields
    acceptance_criteria  = db.Column(db.Text, nullable=True)
    submission_notes     = db.Column(db.Text, nullable=True)
    review_notes         = db.Column(db.Text, nullable=True)
    is_recurring         = db.Column(db.Boolean, default=False, nullable=False)
    recurrence_interval  = db.Column(db.String(20), nullable=True)

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
        if self.status != STATUS_COMPLETED and self.due_date:
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
