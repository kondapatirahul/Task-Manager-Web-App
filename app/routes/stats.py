from flask import Blueprint, jsonify, g
from app.models import Task
from app.routes.auth import login_required

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')

@stats_bp.route('', methods=['GET'])
@login_required
def get_stats():
    uid = g.current_user.id
    tasks = Task.query.filter_by(user_id=uid).all()
    return jsonify({
        'total': len(tasks),
        'pending': sum(1 for t in tasks if t.status == 'pending'),
        'in_progress': sum(1 for t in tasks if t.status == 'in_progress'),
        'done': sum(1 for t in tasks if t.status == 'done'),
        'high_priority': sum(1 for t in tasks if t.priority == 'high'),
    })
