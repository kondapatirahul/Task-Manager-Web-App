from flask import Blueprint, request, jsonify, g
from app import db
from app.models import Task
from app.routes.auth import login_required

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')

@tasks_bp.route('', methods=['GET'])
@login_required
def get_tasks():
    uid = g.current_user.id
    tasks = Task.query.filter_by(user_id=uid).all()
    return jsonify([{
        'id': t.id, 'title': t.title, 'description': t.description,
        'status': t.status, 'priority': t.priority,
        'due_date': t.due_date.isoformat() if t.due_date else None,
        'category_id': t.category_id
    } for t in tasks])

@tasks_bp.route('', methods=['POST'])
@login_required
def create_task():
    uid = g.current_user.id
    data = request.get_json()
    task = Task(title=data['title'], description=data.get('description'),
                status=data.get('status', 'pending'), priority=data.get('priority', 'medium'),
                category_id=data.get('category_id'), user_id=uid)
    db.session.add(task)
    db.session.commit()
    return jsonify({'id': task.id, 'title': task.title}), 201

@tasks_bp.route('/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    uid = g.current_user.id
    task = Task.query.filter_by(id=task_id, user_id=uid).first_or_404()
    data = request.get_json()
    for field in ('title', 'description', 'status', 'priority', 'category_id'):
        if field in data:
            setattr(task, field, data[field])
    db.session.commit()
    return jsonify({'message': 'Updated'})

@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    uid = g.current_user.id
    task = Task.query.filter_by(id=task_id, user_id=uid).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
