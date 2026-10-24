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
ROLE_HR          = 'hr'

ALL_ROLES        = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE)
ADMIN_ROLES      = {ROLE_SUPER_ADMIN, ROLE_ADMIN}
ADMIN_HR_ROLES   = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, 'admin_hr'}
MANAGEMENT_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, 'admin_hr', ROLE_TEAM_LEAD}

# ── Organization & Structure ──────────────────────────────────────────────────

class Organization(db.Model):
    __tablename__ = 'organizations'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    slug       = db.Column(db.String(100), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    departments = db.relationship('Department', backref='organization', lazy='dynamic', cascade='all, delete-orphan')
    teams       = db.relationship('Team', backref='organization', lazy='dynamic', cascade='all, delete-orphan')
    users       = db.relationship('User', backref='organization', lazy='dynamic')

    def __init__(self, **kwargs):
        if 'slug' not in kwargs and 'name' in kwargs and kwargs['name']:
            import re
            kwargs['slug'] = re.sub(r'[^a-zA-Z0-9_-]', '-', kwargs['name'].lower())
        super().__init__(**kwargs)

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

    @property
    def job_title(self):
        return self.designation

    @job_title.setter
    def job_title(self, val):
        self.designation = val

    @property
    def name(self):
        return self.full_name or self.username

    @name.setter
    def name(self, val):
        self.full_name = val

    # Relationships
    manager = db.relationship('User', remote_side=[id], backref='direct_reports')
    team    = db.relationship('Team', foreign_keys=[team_id], backref='assigned_users')

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
        return self.role in ADMIN_ROLES or self.role in ('admin_hr', 'hr')

    @property
    def is_team_lead(self):
        return self.role == ROLE_TEAM_LEAD

    @property
    def is_management(self):
        """True for super_admin, admin, hr, admin_hr, and team_lead."""
        return self.role in MANAGEMENT_ROLES or self.role in ('admin_hr', 'hr')

    def has_role(self, *roles):
        """Return True if this user's role is among the given roles."""
        expanded = set(roles)
        if 'admin' in expanded or 'admin_hr' in expanded or 'hr' in expanded:
            expanded.add('admin')
            expanded.add('admin_hr')
            expanded.add('hr')
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
    is_personal          = db.Column(db.Boolean, default=False, nullable=True)
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
    def assigned_to_id(self):
        return self.assignee_id or self.user_id

    @assigned_to_id.setter
    def assigned_to_id(self, val):
        self.assignee_id = val

    @property
    def assigned_to(self):
        return self.assignee or self.user

    @assigned_to.setter
    def assigned_to(self, val):
        self.assignee = val

    @property
    def comments(self):
        return self.messages

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status.replace('_', ' ').title())

    @property
    def submission_notes(self):
        sub = self.submissions.order_by(WorkSubmission.created_at.desc()).first() if hasattr(self, 'submissions') else None
        return sub.notes if sub else ''

    @submission_notes.setter
    def submission_notes(self, val):
        pass

    @property
    def review_notes(self):
        sub = self.submissions.order_by(WorkSubmission.created_at.desc()).first() if hasattr(self, 'submissions') else None
        return sub.review_notes if sub else ''

    @review_notes.setter
    def review_notes(self, val):
        pass

    @property
    def is_overdue(self):
        if self.status != STATUS_COMPLETED and self.due_date:
            return self.due_date < date.today()
        return False

    @property
    def reference_attachments(self):
        if not hasattr(self, 'attachments'):
            return []
        refs = [a for a in self.attachments if getattr(a, 'attachment_type', None) == 'reference']
        return [r.to_dict() for r in refs]

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
            'status_label':         self.status_label,
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
            'creator_role':         self.creator.role if self.creator else None,
            'assignee_id':          self.assignee_id or self.user_id,
            'assigned_to_id':       self.assignee_id or self.user_id,
            'assignee_name':        eff_assignee_name,
            'assigned_to_name':     eff_assignee_name,
            'assigned_to_email':    eff_assignee.email if eff_assignee else None,
            'assigned_to_role':     eff_assignee.role if eff_assignee else None,
            'category_id':          self.category_id,
            'category_name':        self.category.name if self.category else None,
            'team_id':              self.team_id,
            'team_name':            self.team.name if self.team else None,
            'organization_id':      self.organization_id,
            'acceptance_criteria':  self.acceptance_criteria or '',
            'submission_notes':     self.submission_notes,
            'review_notes':         self.review_notes,
            'progress':             self.progress,
            'is_recurring':         bool(self.is_recurring),
            'recurrence_interval':  self.recurrence_interval,
            'next_recurrence_date': self.next_recurrence_date.isoformat() if self.next_recurrence_date else None,
            'subtask_count':        self.subtasks.count() if hasattr(self.subtasks, 'count') else 0,
            'subtasks_completed_count': sum(1 for st in self.subtasks if st.is_completed) if hasattr(self, 'subtasks') else 0,
            'message_count':        self.messages.count() if hasattr(self.messages, 'count') else 0,
            'attachment_count':     self.attachments.count() if hasattr(self.attachments, 'count') else 0,
            'submission_count':     self.submissions.count() if hasattr(self.submissions, 'count') else 0,
            'status_history':       [h.to_dict() for h in self.status_history.all()] if hasattr(self, 'status_history') else [],
            'is_personal':          bool(self.is_personal),
            'reference_attachments': self.reference_attachments,
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
    attachments = db.relationship('TaskAttachment', backref='message', lazy='dynamic')

    @property
    def mentions(self):
        import re
        if not self.content:
            return []
        usernames = set(re.findall(r'@([a-zA-Z0-9_\-\.]+)', self.content))
        if not usernames:
            return []
        users = User.query.filter(User.username.in_(usernames)).all()
        return [{'id': u.id, 'username': u.username, 'full_name': u.full_name or u.username} for u in users]

    def to_dict(self):
        author_name = (self.author.full_name or self.author.username) if self.author else 'Unknown'
        return {
            'id': self.id,
            'task_id': self.task_id,
            'user_id': self.user_id,
            'author_name': author_name,
            'author_role': self.author.role if self.author else None,
            'content': self.content,
            'mentions': self.mentions,
            'attachments': [a.to_dict() for a in self.attachments.all()] if self.attachments else [],
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
    attachment_type = db.Column(db.String(50), default='general', nullable=True)
    created_at    = db.Column(db.DateTime, default=utc_now, nullable=False)

    uploader = db.relationship('User', backref='task_attachments')

    @property
    def file_extension(self):
        if '.' in self.filename:
            return self.filename.rsplit('.', 1)[1].lower()
        return ''

    @property
    def file_type(self):
        ext_types = {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'txt': 'text/plain',
        }
        return self.content_type or ext_types.get(self.file_extension, 'application/octet-stream')

    @property
    def is_image(self):
        return self.file_extension in {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    @property
    def is_previewable(self):
        return self.file_extension in {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'txt'}

    @property
    def download_url(self):
        return f'/api/tasks/{self.task_id}/attachments/{self.id}/download'

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
            'original_filename': self.filename,
            'file_size': self.file_size,
            'content_type': self.file_type,
            'file_type': self.file_type,
            'file_extension': self.file_extension,
            'is_image': self.is_image,
            'is_previewable': self.is_previewable,
            'download_url': self.download_url,
            'attachment_type': self.attachment_type or 'general',
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
        }


# Compatibility aliases
TaskComment = TaskMessage
TaskSubmission = WorkSubmission


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
        emp_code = (self.user.employee_id_code or f'EMP-{self.user.id:04d}') if self.user else ''
        role = self.user.role if self.user else None
        team_name = self.user.team.name if (self.user and getattr(self.user, 'team', None)) else None
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': user_name,
            'employee_id_code': emp_code,
            'role': role,
            'team_name': team_name,
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
        emp_code = (self.user.employee_id_code or f'EMP-{self.user.id:04d}') if self.user else ''
        role_name = self.user.role if self.user else ''
        team_name = self.user.team.name if (self.user and getattr(self.user, 'team', None)) else 'No Team'
        return {
            'id': self.id,
            'attendance_id': self.attendance_id,
            'user_id': self.user_id,
            'user_name': user_name,
            'employee_id_code': emp_code,
            'role': role_name,
            'team_name': team_name,
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



# ── Leave Requests ─────────────────────────────────────────────────────────────

class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type       = db.Column(db.String(50), nullable=False) # 'Casual', 'Sick', 'Annual', 'Maternity/Paternity', 'Unpaid', 'Other'
    start_date       = db.Column(db.Date, nullable=False)
    end_date         = db.Column(db.Date, nullable=False)
    reason           = db.Column(db.Text, nullable=False)
    status           = db.Column(db.String(20), default='pending', nullable=False) # 'pending', 'approved', 'rejected'
    reviewer_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewer_comment = db.Column(db.Text, nullable=True)
    decision_at      = db.Column(db.DateTime, nullable=True)
    created_at       = db.Column(db.DateTime, default=utc_now, nullable=False)

    user     = db.relationship('User', foreign_keys=[user_id], backref='leave_requests')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='reviewed_leaves')

    def to_dict(self):
        user_name = (self.user.full_name or self.user.username) if self.user else None
        reviewer_name = (self.reviewer.full_name or self.reviewer.username) if self.reviewer else None
        emp_code = (self.user.employee_id_code or f'EMP-{self.user.id:04d}') if self.user else ''
        team_name = self.user.team.name if (self.user and getattr(self.user, 'team', None)) else 'No Team'
        role_name = self.user.role if self.user else ''
        days = (self.end_date - self.start_date).days + 1 if (self.start_date and self.end_date) else 0

        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': user_name,
            'employee_name': user_name,
            'employee_id_code': emp_code,
            'employee_role': role_name,
            'team_name': team_name,
            'leave_type': self.leave_type,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'days_count': days,
            'reason': self.reason,
            'status': self.status,
            'reviewer_id': self.reviewer_id,
            'reviewer_name': reviewer_name,
            'reviewer_comment': self.reviewer_comment or '',
            'decision_at': self.decision_at.isoformat() if self.decision_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
