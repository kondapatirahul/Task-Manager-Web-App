from datetime import datetime
from flask import Blueprint, jsonify, g
from app.models import Task
from app.routes.auth import login_required


stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('', methods=['GET'])
@login_required
def get_stats():
    uid = g.current_user.id

    tasks = Task.query.filter_by(user_id=uid).all()

    now = datetime.utcnow()

    pending = sum(
        1 for task in tasks
        if task.status == 'pending'
    )

    completed = sum(
        1 for task in tasks
        if task.status == 'done'
    )

    overdue = sum(
        1 for task in tasks
        if task.due_date
        and task.due_date < now
        and task.status != 'done'
    )

    by_priority = {
        'low': sum(
            1 for task in tasks
            if task.priority == 'low'
        ),
        'medium': sum(
            1 for task in tasks
            if task.priority == 'medium'
        ),
        'high': sum(
            1 for task in tasks
            if task.priority == 'high'
        )
    }

    return jsonify({
        'total': len(tasks),
        'pending': pending,
        'completed': completed,
        'overdue': overdue,
        'by_priority': by_priority
    })