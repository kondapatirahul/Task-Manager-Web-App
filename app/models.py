from app import db
from datetime import datetime


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    tasks = db.relationship('Task', backref='owner', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email
        }


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )

    tasks = db.relationship('Task', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'user_id': self.user_id
        }


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    status = db.Column(
        db.String(20),
        default='pending'
    )  # pending, in_progress, done

    priority = db.Column(
        db.String(10),
        default='medium'
    )  # low, medium, high

    due_date = db.Column(db.DateTime)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey('category.id')
    )

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'priority': self.priority,
            'due_date': (
                self.due_date.isoformat()
                if self.due_date
                else None
            ),
            'created_at': (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
            'user_id': self.user_id,
            'category_id': self.category_id
        }