from datetime import date, timedelta
from flask import Blueprint
from flask_login import current_user, login_required
from app.models import Task, Category
from app.routes.utils import api_success

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('', methods=['GET'])
@login_required
def get_stats():
    today = date.today()
    tasks = Task.query.filter_by(user_id=current_user.id).all()

    total = len(tasks)
    pending = sum(1 for t in tasks if t.status == 'pending')
    completed = sum(1 for t in tasks if t.status == 'completed')
    overdue = sum(1 for t in tasks if t.status != 'completed' and t.due_date and t.due_date < today)
    due_today = sum(1 for t in tasks if t.status != 'completed' and t.due_date and t.due_date == today)
    high_priority = sum(1 for t in tasks if t.status != 'completed' and t.priority == 'high')

    completion_rate = round((completed / total * 100)) if total > 0 else 0

    # Categories breakdown
    categories = Category.query.filter_by(user_id=current_user.id).all()
    by_category = [
        {
            'id': c.id,
            'name': c.name,
            'total': sum(1 for t in tasks if t.category_id == c.id),
            'pending': sum(1 for t in tasks if t.category_id == c.id and t.status == 'pending')
        }
        for c in categories
    ]

    # Upcoming tasks (pending tasks with due dates in next 7 days, or closest pending)
    next_week = today + timedelta(days=7)
    upcoming_tasks = [
        t.to_dict() for t in sorted(
            [t for t in tasks if t.status == 'pending' and t.due_date],
            key=lambda x: x.due_date
        )[:5]
    ]

    return api_success({
        'total': total,
        'pending': pending,
        'completed': completed,
        'overdue': overdue,
        'due_today': due_today,
        'high_priority': high_priority,
        'completion_rate': completion_rate,
        'by_category': by_category,
        'upcoming': upcoming_tasks
    })
