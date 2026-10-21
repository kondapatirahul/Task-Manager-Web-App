from flask import Blueprint, request, jsonify, g
from app import db
from app.models import Category, Task
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
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required'}), 400

    title = data.get('title')
    description = data.get('description')
    status = data.get('status', 'pending')
    priority = data.get('priority', 'medium')
    category_id = data.get('category_id')

    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        return jsonify({'error': 'Title must be between 1 and 200 characters'}), 400
    if description is not None and not isinstance(description, str):
        return jsonify({'error': 'Description must be a string or null'}), 400
    if status not in ('pending', 'in_progress', 'done'):
        return jsonify({'error': 'Invalid task status'}), 400
    if priority not in ('low', 'medium', 'high'):
        return jsonify({'error': 'Invalid task priority'}), 400
    if category_id is not None and (type(category_id) is not int or category_id <= 0):
        return jsonify({'error': 'Category ID must be a positive integer or null'}), 400
    if category_id is not None and not Category.query.filter_by(
        id=category_id, user_id=uid
    ).first():
        return jsonify({'error': 'Category not found'}), 404

    task = Task(
        title=title,
        description=description,
        status=status,
        priority=priority,
        category_id=category_id,
        user_id=uid,
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({'id': task.id, 'title': task.title}), 201

@tasks_bp.route('/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    uid = g.current_user.id
    task = Task.query.filter_by(id=task_id, user_id=uid).first_or_404()
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required'}), 400

    updates = {}
    if 'title' in data:
        title = data['title']
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            return jsonify({'error': 'Title must be between 1 and 200 characters'}), 400
        updates['title'] = title
    if 'description' in data:
        description = data['description']
        if description is not None and not isinstance(description, str):
            return jsonify({'error': 'Description must be a string or null'}), 400
        updates['description'] = description
    if 'status' in data:
        if data['status'] not in ('pending', 'in_progress', 'done'):
            return jsonify({'error': 'Invalid task status'}), 400
        updates['status'] = data['status']
    if 'priority' in data:
        if data['priority'] not in ('low', 'medium', 'high'):
            return jsonify({'error': 'Invalid task priority'}), 400
        updates['priority'] = data['priority']
    if 'category_id' in data:
        category_id = data['category_id']
        if category_id is not None and (
            type(category_id) is not int or category_id <= 0
        ):
            return jsonify({
                'error': 'Category ID must be a positive integer or null'
            }), 400
        if category_id is not None and not Category.query.filter_by(
            id=category_id, user_id=uid
        ).first():
            return jsonify({'error': 'Category not found'}), 404
        updates['category_id'] = category_id

    for field, value in updates.items():
        setattr(task, field, value)
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
