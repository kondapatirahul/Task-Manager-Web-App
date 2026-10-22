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

    tasks      = db.relationship('Task',     backref='user', lazy='dynamic',
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
    def is_management(self):
        """True for super_admin, admin, and team_lead."""
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
        return {
            'id':           self.id,
            'full_name':    self.full_name or self.username,
            'username':     self.username,
            'email':        self.email,
            'role':         self.role,
            'account_active': self.account_active,
            'created_at':   self.created_at.isoformat() if self.created_at else None,
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

    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer,
                            db.ForeignKey('categories.id', ondelete='SET NULL'),
                            nullable=True)

    @property
    def is_overdue(self):
        if self.status != 'completed' and self.due_date:
            return self.due_date < date.today()
        return False

    def to_dict(self):
        return {
            'id':            self.id,
            'title':         self.title,
            'description':   self.description or '',
            'status':        self.status,
            'priority':      self.priority,
            'due_date':      self.due_date.isoformat() if self.due_date else None,
            'created_at':    self.created_at.isoformat() if self.created_at else None,
            'completed_at':  self.completed_at.isoformat() if self.completed_at else None,
            'is_overdue':    self.is_overdue,
            'user_id':       self.user_id,
            'category_id':   self.category_id,
            'category_name': self.category.name if self.category else None,
        }
