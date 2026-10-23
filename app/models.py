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

ALL_ROLES        = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE)
MANAGEMENT_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD}
ADMIN_ROLES      = {ROLE_SUPER_ADMIN, ROLE_ADMIN}

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

    # Soft-disable: deactivated accounts cannot log in, data is preserved
    account_active = db.Column(db.Boolean, nullable=False, default=True)

    # Enterprise Extensions
    organization_id  = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    department_id    = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    team_id          = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    manager_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    designation      = db.Column(db.String(100), nullable=False, default='Employee')
    employee_id_code = db.Column(db.String(30), nullable=True)
    phone            = db.Column(db.String(30), nullable=True)

    # Relationships
    manager = db.relationship('User', remote_side=[id], backref='direct_reports')

    # Tasks: explicitly bind user_id to prevent ambiguity with creator_id/assignee_id
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
        return self.role in ADMIN_ROLES or self.role == 'admin_hr'

    @property
    def is_team_lead(self):
        return self.role == ROLE_TEAM_LEAD

    @property
    def is_management(self):
        """True for super_admin, admin, admin_hr, and team_lead."""
        return self.role in MANAGEMENT_ROLES or self.role == 'admin_hr'

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
        dept_name = self.department.name if self.department else None
        manager_name = self.manager.full_name or self.manager.username if self.manager else None
        return {
            'id':               self.id,
            'full_name':        self.full_name or self.username,
            'username':         self.username,
            'email':            self.email,
            'role':             self.role,
            'account_active':   self.account_active,
            'organization_id':  self.organization_id,
            'department_id':    self.department_id,
            'department_name':  dept_name,
            'team_id':          self.team_id,
            'manager_id':       self.manager_id,
            'manager_name':     manager_name,
            'designation':      self.designation or 'Employee',
            'employee_id_code': self.employee_id_code or f'EMP-{self.id:04d}',
            'phone':            self.phone or '',
            'created_at':       self.created_at.isoformat() if self.created_at else None,
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


# ── Task & Lifecycle Models ────────────────────────────────────────────────────

# Extended Enterprise Statuses
STATUS_TODO              = 'todo'
STATUS_IN_PROGRESS       = 'in_progress'
STATUS_BLOCKED           = 'blocked'
STATUS_IN_REVIEW         = 'in_review'
STATUS_CHANGES_REQUESTED = 'changes_requested'
STATUS_COMPLETED         = 'completed'
STATUS_PENDING           = 'pending'  # legacy alias mapped to todo

ENTERPRISE_STATUSES = {
    STATUS_TODO, STATUS_IN_PROGRESS, STATUS_BLOCKED,
    STATUS_IN_REVIEW, STATUS_CHANGES_REQUESTED, STATUS_COMPLETED,
    STATUS_PENDING
}

class Task(db.Model):
    __tablename__ = 'tasks'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text, nullable=True)
    status       = db.Column(db.String(25), default='pending', nullable=False)
    priority     = db.Column(db.String(10), default='medium', nullable=False)   # 'low', 'medium', 'high', 'urgent'
    due_date     = db.Column(db.Date, nullable=True)
    start_date   = db.Column(db.Date, nullable=True)
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at   = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Legacy & Enterprise Assignment
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # Owner/Assignee legacy compatibility
    creator_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    team_id     = db.Column(db.Integer, db.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)

    # Enterprise Fields
    acceptance_criteria  = db.Column(db.Text, nullable=True)
    progress             = db.Column(db.Integer, default=0, nullable=False) # 0 to 100
    is_recurring         = db.Column(db.Boolean, default=False, nullable=False)
    recurrence_interval  = db.Column(db.String(20), nullable=True) # 'daily', 'weekly', 'monthly'
    next_recurrence_date = db.Column(db.Date, nullable=True)

    # Relationships
    creator  = db.relationship('User', foreign_keys=[creator_id], backref='created_tasks')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_tasks')
    subtasks = db.relationship('SubTask', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('TaskMessage', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    attachments = db.relationship('TaskAttachment', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    submissions = db.relationship('WorkSubmission', backref='task', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def is_overdue(self):
        if self.status != STATUS_COMPLETED and self.due_date:
            return self.due_date < date.today()
        return False

    def to_dict(self):
        # Effective assignee is assignee or user
        eff_assignee = self.assignee or self.user
        eff_assignee_name = (eff_assignee.full_name or eff_assignee.username) if eff_assignee else None
        creator_name = (self.creator.full_name or self.creator.username) if self.creator else None

        return {
            'id':                   self.id,
            'title':                self.title,
            'description':          self.description or '',
            'status':               self.status,
            'priority':             self.priority,
            'due_date':             self.due_date.isoformat() if self.due_date else None,
            'start_date':           self.start_date.isoformat() if self.start_date else None,
            'created_at':           self.created_at.isoformat() if self.created_at else None,
            'updated_at':           self.updated_at.isoformat() if self.updated_at else None,
            'completed_at':         self.completed_at.isoformat() if self.completed_at else None,
            'is_overdue':           self.is_overdue,
            'user_id':              self.user_id,
            'creator_id':           self.creator_id or self.user_id,
            'creator_name':         creator_name,
            'assignee_id':          self.assignee_id or self.user_id,
            'assignee_name':        eff_assignee_name,
            'category_id':          self.category_id,
            'category_name':        self.category.name if self.category else None,
            'team_id':              self.team_id,
            'team_name':            self.team.name if self.team else None,
            'organization_id':      self.organization_id,
            'acceptance_criteria':  self.acceptance_criteria or '',
            'progress':             self.progress,
            'is_recurring':         bool(self.is_recurring),
            'recurrence_interval':  self.recurrence_interval,
            'next_recurrence_date': self.next_recurrence_date.isoformat() if self.next_recurrence_date else None,
            'subtask_count':        self.subtasks.count() if hasattr(self.subtasks, 'count') else 0,
            'message_count':        self.messages.count() if hasattr(self.messages, 'count') else 0,
            'attachment_count':     self.attachments.count() if hasattr(self.attachments, 'count') else 0,
            'submission_count':     self.submissions.count() if hasattr(self.submissions, 'count') else 0,
        }


class SubTask(db.Model):
    __tablename__ = 'subtasks'

    id           = db.Column(db.Integer, primary_key=True)
    task_id      = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    title        = db.Column(db.String(200), nullable=False)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'title': self.title,
            'is_completed': self.is_completed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ── Discussions, Attachments & Work Submissions ───────────────────────────────

class TaskMessage(db.Model):
    __tablename__ = 'task_messages'

    id         = db.Column(db.Integer, primary_key=True)
    task_id    = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship('User', backref='task_messages')

    def to_dict(self):
        author_name = (self.author.full_name or self.author.username) if self.author else 'Unknown'
        return {
            'id': self.id,
            'task_id': self.task_id,
            'user_id': self.user_id,
            'author_name': author_name,
            'author_role': self.author.role if self.author else None,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskAttachment(db.Model):
    __tablename__ = 'task_attachments'

    id            = db.Column(db.Integer, primary_key=True)
    task_id       = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    message_id    = db.Column(db.Integer, db.ForeignKey('task_messages.id', ondelete='SET NULL'), nullable=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('work_submissions.id', ondelete='SET NULL'), nullable=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename      = db.Column(db.String(255), nullable=False)
    file_path     = db.Column(db.String(500), nullable=False)
    file_size     = db.Column(db.Integer, nullable=False)
    content_type  = db.Column(db.String(100), nullable=True)
    created_at    = db.Column(db.DateTime, default=utc_now, nullable=False)

    uploader = db.relationship('User', backref='task_attachments')

    def to_dict(self):
        uploader_name = (self.uploader.full_name or self.uploader.username) if self.uploader else None
        return {
            'id': self.id,
            'task_id': self.task_id,
            'message_id': self.message_id,
            'submission_id': self.submission_id,
            'user_id': self.user_id,
            'uploader_name': uploader_name,
            'filename': self.filename,
            'file_size': self.file_size,
            'content_type': self.content_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class WorkSubmission(db.Model):
    __tablename__ = 'work_submissions'

    id           = db.Column(db.Integer, primary_key=True)
    task_id      = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notes        = db.Column(db.Text, nullable=True)
    status       = db.Column(db.String(30), default='submitted', nullable=False) # 'submitted', 'approved', 'changes_requested'
    review_notes = db.Column(db.Text, nullable=True)
    reviewed_by  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at  = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False)

    submitter = db.relationship('User', foreign_keys=[user_id], backref='work_submissions')
    reviewer  = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_submissions')
    attachments = db.relationship('TaskAttachment', backref='submission', lazy='dynamic')

    def to_dict(self):
        submitter_name = (self.submitter.full_name or self.submitter.username) if self.submitter else None
        reviewer_name = (self.reviewer.full_name or self.reviewer.username) if self.reviewer else None
        return {
            'id': self.id,
            'task_id': self.task_id,
            'user_id': self.user_id,
            'submitter_name': submitter_name,
            'notes': self.notes or '',
            'status': self.status,
            'review_notes': self.review_notes or '',
            'reviewed_by': self.reviewed_by,
            'reviewer_name': reviewer_name,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'attachments': [a.to_dict() for a in self.attachments] if self.attachments else [],
        }


# ── Attendance & Timesheets ───────────────────────────────────────────────────

class Attendance(db.Model):
    __tablename__ = 'attendances'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id  = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    check_in         = db.Column(db.DateTime, default=utc_now, nullable=False)
    check_out        = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, default=0, nullable=False)
    notes            = db.Column(db.Text, nullable=True)
    status           = db.Column(db.String(20), default='active', nullable=False) # 'active', 'completed', 'corrected'
    created_at       = db.Column(db.DateTime, default=utc_now, nullable=False)

    corrections = db.relationship('AttendanceCorrection', backref='attendance', lazy='dynamic', cascade='all, delete-orphan')

    def calculate_duration(self):
        if self.check_in and self.check_out:
            ci = self.check_in.replace(tzinfo=None) if self.check_in.tzinfo else self.check_in
            co = self.check_out.replace(tzinfo=None) if self.check_out.tzinfo else self.check_out
            delta = co - ci
            self.duration_minutes = max(0, int(delta.total_seconds() / 60))
        return self.duration_minutes

    def to_dict(self):
        user_name = (self.user.full_name or self.user.username) if self.user else None
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': user_name,
            'organization_id': self.organization_id,
            'check_in': self.check_in.isoformat() if self.check_in else None,
            'check_out': self.check_out.isoformat() if self.check_out else None,
            'duration_minutes': self.duration_minutes,
            'duration_hours': round(self.duration_minutes / 60.0, 2),
            'notes': self.notes or '',
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AttendanceCorrection(db.Model):
    __tablename__ = 'attendance_corrections'

    id                  = db.Column(db.Integer, primary_key=True)
    attendance_id       = db.Column(db.Integer, db.ForeignKey('attendances.id', ondelete='CASCADE'), nullable=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_check_in  = db.Column(db.DateTime, nullable=False)
    requested_check_out = db.Column(db.DateTime, nullable=False)
    reason              = db.Column(db.Text, nullable=False)
    status              = db.Column(db.String(20), default='pending', nullable=False) # 'pending', 'approved', 'rejected'
    reviewed_by         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at         = db.Column(db.DateTime, nullable=True)
    created_at          = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship('User', foreign_keys=[user_id], backref='attendance_corrections')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_corrections')

    def to_dict(self):
        user_name = (self.user.full_name or self.user.username) if self.user else None
        reviewer_name = (self.reviewer.full_name or self.reviewer.username) if self.reviewer else None
        return {
            'id': self.id,
            'attendance_id': self.attendance_id,
            'user_id': self.user_id,
            'user_name': user_name,
            'requested_check_in': self.requested_check_in.isoformat() if self.requested_check_in else None,
            'requested_check_out': self.requested_check_out.isoformat() if self.requested_check_out else None,
            'reason': self.reason,
            'status': self.status,
            'reviewed_by': self.reviewed_by,
            'reviewer_name': reviewer_name,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ── Calendar & Meetings ────────────────────────────────────────────────────────

class Meeting(db.Model):
    __tablename__ = 'meetings'

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(200), nullable=False)
    agenda           = db.Column(db.Text, nullable=True)
    organizer_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    team_id          = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    organization_id  = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    start_time       = db.Column(db.DateTime, nullable=False)
    end_time         = db.Column(db.DateTime, nullable=False)
    location_or_link = db.Column(db.String(255), nullable=True)
    status           = db.Column(db.String(20), default='scheduled', nullable=False) # 'scheduled', 'cancelled'
    created_at       = db.Column(db.DateTime, default=utc_now, nullable=False)

    organizer = db.relationship('User', backref='organized_meetings')
    team      = db.relationship('Team', backref='meetings')
    attendees = db.relationship('MeetingAttendee', backref='meeting', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        organizer_name = (self.organizer.full_name or self.organizer.username) if self.organizer else None
        return {
            'id': self.id,
            'title': self.title,
            'agenda': self.agenda or '',
            'organizer_id': self.organizer_id,
            'organizer_name': organizer_name,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'organization_id': self.organization_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'location_or_link': self.location_or_link or '',
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'attendee_count': self.attendees.count() if hasattr(self.attendees, 'count') else 0,
        }


class MeetingAttendee(db.Model):
    __tablename__ = 'meeting_attendees'

    id         = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status     = db.Column(db.String(20), default='invited', nullable=False) # 'invited', 'accepted', 'declined', 'tentative'

    user = db.relationship('User', backref='meeting_invitations')

    def to_dict(self):
        user_name = (self.user.full_name or self.user.username) if self.user else None
        return {
            'id': self.id,
            'meeting_id': self.meeting_id,
            'user_id': self.user_id,
            'user_name': user_name,
            'user_email': self.user.email if self.user else None,
            'status': self.status,
        }


# ── Notifications ──────────────────────────────────────────────────────────────

class Notification(db.Model):
    __tablename__ = 'notifications'

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title           = db.Column(db.String(150), nullable=False)
    message         = db.Column(db.String(500), nullable=False)
    link            = db.Column(db.String(255), nullable=True)
    type            = db.Column(db.String(50), default='system', nullable=False) # 'task_assigned', 'task_message', 'submission_review', 'meeting_invite', 'system'
    is_read         = db.Column(db.Boolean, default=False, nullable=False)
    idempotency_key = db.Column(db.String(100), unique=True, nullable=True)
    created_at      = db.Column(db.DateTime, default=utc_now, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'link': self.link or '#',
            'type': self.type,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ── Audit Log ──────────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id              = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action          = db.Column(db.String(100), nullable=False) # e.g. 'user_created', 'task_assigned', 'submission_approved'
    entity_type     = db.Column(db.String(50), nullable=False)  # e.g. 'Task', 'User', 'Attendance'
    entity_id       = db.Column(db.Integer, nullable=True)
    details         = db.Column(db.Text, nullable=True)
    ip_address      = db.Column(db.String(45), nullable=True)
    created_at      = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship('User', backref='audit_events')

    def to_dict(self):
        user_name = (self.user.full_name or self.user.username) if self.user else 'System'
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'user_id': self.user_id,
            'user_name': user_name,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'details': self.details or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ── Password Reset Token ───────────────────────────────────────────────────────

class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token      = db.Column(db.String(128), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used    = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship('User', backref=db.backref('reset_tokens', cascade='all, delete-orphan'))

    def is_valid(self):
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return not self.is_used and exp > now

