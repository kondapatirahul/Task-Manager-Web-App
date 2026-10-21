from flask import Blueprint, request, jsonify, session
from app import db
from app.models import Task

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')

def current_user_id():
    return session.get('user_id')

@tasks_bp.route('', methods=['GET'])
def get_tasks():
    uid = current_user_id()
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    tasks = Task.query.filter_by(user_id=uid).all()
    return jsonify([{
        'id': t.id, 'title': t.title, 'description': t.description,
        'status': t.status, 'priority': t.priority,
        'due_date': t.due_date.isoformat() if t.due_date else None,
        'category_id': t.category_id
    } for t in tasks])

@tasks_bp.route('', methods=['POST'])
def create_task():
    uid = current_user_id()
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    task = Task(title=data['title'], description=data.get('description'),
                status=data.get('status', 'pending'), priority=data.get('priority', 'medium'),
                category_id=data.get('category_id'), user_id=uid)
    db.session.add(task)
    db.session.commit()
    return jsonify({'id': task.id, 'title': task.title}), 201

@tasks_bp.route('/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    uid = current_user_id()
    task = Task.query.filter_by(id=task_id, user_id=uid).first_or_404()
    data = request.get_json()
    for field in ('title', 'description', 'status', 'priority', 'category_id'):
        if field in data:
            setattr(task, field, data[field])
    db.session.commit()
    return jsonify({'message': 'Updated'})

@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    uid = current_user_id()
    task = Task.query.filter_by(id=task_id, user_id=uid).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Deleted'})
