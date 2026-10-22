from datetime import date, timedelta
from flask import Blueprint
from flask_login import current_user, login_required
from sqlalchemy import or_
from app.models import Task, Category, Team
from app.routes.utils import api_success
from app.routes.tasks import get_user_led_team_ids

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('', methods=['GET'])
@login_required
def get_stats():
    today = date.today()

    # Query tasks accessible to the current user
    if current_user.role in ('super_admin', 'admin'):
        tasks = Task.query.all()
    elif current_user.role == 'team_lead':
        led_team_ids = get_user_led_team_ids(current_user)
        conditions = [
            Task.user_id == current_user.id,
            Task.assigned_to_id == current_user.id,
        ]
        if led_team_ids:
            conditions.append(Task.team_id.in_(led_team_ids))
        tasks = Task.query.filter(or_(*conditions)).all()
    else:
        # Employee: personal tasks and company assigned tasks
        tasks = Task.query.filter(
            or_(
                Task.user_id == current_user.id,
                Task.assigned_to_id == current_user.id
            )
        ).all()

    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == 'completed')
    pending = sum(1 for t in tasks if t.status != 'completed')
    overdue = sum(1 for t in tasks if t.status != 'completed' and t.due_date and t.due_date < today)
    due_today = sum(1 for t in tasks if t.status != 'completed' and t.due_date and t.due_date == today)
    high_priority = sum(1 for t in tasks if t.status != 'completed' and t.priority == 'high')

    # Breakdown by specific company statuses
    by_status = {
        'todo': sum(1 for t in tasks if t.status in ('todo', 'pending')),
        'in_progress': sum(1 for t in tasks if t.status == 'in_progress'),
        'blocked': sum(1 for t in tasks if t.status == 'blocked'),
        'in_review': sum(1 for t in tasks if t.status == 'in_review'),
        'changes_requested': sum(1 for t in tasks if t.status == 'changes_requested'),
        'completed': completed,
    }

    completion_rate = round((completed / total * 100)) if total > 0 else 0

    # Categories breakdown
    categories = Category.query.filter_by(user_id=current_user.id).all()
    by_category = [
        {
            'id': c.id,
            'name': c.name,
            'total': sum(1 for t in tasks if t.category_id == c.id),
            'pending': sum(1 for t in tasks if t.category_id == c.id and t.status != 'completed')
        }
        for c in categories
    ]

    # Upcoming tasks (non-completed tasks with due dates in next 7 days or upcoming)
    upcoming_tasks = [
        t.to_dict() for t in sorted(
            [t for t in tasks if t.status != 'completed' and t.due_date],
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
        'by_status': by_status,
        'by_category': by_category,
        'upcoming': upcoming_tasks
    })
