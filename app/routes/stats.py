from flask import Blueprint, jsonify, session
from app.models import Task

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')

@stats_bp.route('', methods=['GET'])
def get_stats():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    tasks = Task.query.filter_by(user_id=uid).all()
    return jsonify({
        'total': len(tasks),
        'pending': sum(1 for t in tasks if t.status == 'pending'),
        'in_progress': sum(1 for t in tasks if t.status == 'in_progress'),
        'done': sum(1 for t in tasks if t.status == 'done'),
        'high_priority': sum(1 for t in tasks if t.priority == 'high'),
    })
