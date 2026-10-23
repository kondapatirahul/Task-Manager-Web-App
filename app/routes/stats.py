from datetime import date, datetime, timedelta, timezone
from flask import Blueprint
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import (
    Task, Category, TaskStatusHistory, WorkSubmission, Attendance,
    STATUS_TODO, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_IN_REVIEW,
    STATUS_CHANGES_REQUESTED, STATUS_COMPLETED, STATUS_PENDING
)
from app.routes.utils import api_success

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('', methods=['GET'])
@login_required
def get_stats():
    today = date.today()

    # Query tasks authorized for current user
    if current_user.has_role('super_admin', 'admin'):
        query = Task.query.filter(
            or_(Task.is_personal.is_(False), Task.is_personal.is_(None), Task.creator_id == current_user.id)
        )
    else:
        query = Task.query.filter(
            or_(
                Task.user_id == current_user.id,
                Task.assignee_id == current_user.id,
                Task.creator_id == current_user.id
            ),
            or_(Task.is_personal.is_(False), Task.is_personal.is_(None), Task.creator_id == current_user.id)
        )

    all_tasks = query.all()
    # Deduplicate in case of multiple matching conditions
    task_map = {t.id: t for t in all_tasks}
    tasks = list(task_map.values())

    total = len(tasks)
    personal_count = sum(1 for t in tasks if getattr(t, 'is_personal', False))
    assigned_count = total - personal_count

    # Status counts
    todo = sum(1 for t in tasks if t.status in (STATUS_TODO, STATUS_PENDING))
    in_progress = sum(1 for t in tasks if t.status == STATUS_IN_PROGRESS)
    in_review = sum(1 for t in tasks if t.status in (STATUS_IN_REVIEW, 'review'))
    blocked = sum(1 for t in tasks if t.status == STATUS_BLOCKED)
    changes_requested = sum(1 for t in tasks if t.status == STATUS_CHANGES_REQUESTED)
    completed = sum(1 for t in tasks if t.status == STATUS_COMPLETED)

    # Overdue and due today
    overdue = sum(1 for t in tasks if t.status != STATUS_COMPLETED and t.due_date and t.due_date < today)
    due_today = sum(1 for t in tasks if t.status != STATUS_COMPLETED and t.due_date and t.due_date == today)
    high_priority = sum(1 for t in tasks if t.status != STATUS_COMPLETED and t.priority in ('high', 'urgent'))

    # Backwards compatibility fields
    pending = todo
    completion_rate = round((completed / total * 100)) if total > 0 else 0

    # Categories breakdown
    categories = Category.query.filter(
        or_(Category.user_id == current_user.id, Category.user_id.is_(None))
    ).all()
    by_category = [
        {
            'id': c.id,
            'name': c.name,
            'total': sum(1 for t in tasks if t.category_id == c.id),
            'pending': sum(1 for t in tasks if t.category_id == c.id and t.status != STATUS_COMPLETED)
        }
        for c in categories
    ]

    # Upcoming tasks (pending / active tasks with due dates in next 7 days, or closest pending)
    upcoming_tasks = [
        t.to_dict() for t in sorted(
            [t for t in tasks if t.status != STATUS_COMPLETED and t.due_date],
            key=lambda x: (x.due_date, 0 if x.priority == 'urgent' else 1)
        )[:5]
    ]

    # Deterministic Smart Priority ("What should I work on next?")
    active_candidates = [t for t in tasks if t.status != STATUS_COMPLETED]
    smart_next = None
    if active_candidates:
        scored = []
        for t in active_candidates:
            score = 0
            reason = "Recommended next step"

            # Due date scoring
            if t.due_date:
                if t.due_date < today:
                    days_overdue = (today - t.due_date).days
                    score += 50 + min(days_overdue * 2, 20)
                    reason = f"Overdue by {days_overdue} day{'s' if days_overdue != 1 else ''}"
                elif t.due_date == today:
                    score += 45
                    reason = "Due today"
                elif t.due_date == today + timedelta(days=1):
                    score += 35
                    reason = "Due tomorrow"
                elif t.due_date <= today + timedelta(days=3):
                    score += 25
                    reason = f"Due soon ({t.due_date.strftime('%b %d')})"
                elif t.due_date <= today + timedelta(days=7):
                    score += 15
                    reason = f"Due this week ({t.due_date.strftime('%b %d')})"

            # Priority scoring
            if t.priority == 'urgent':
                score += 40
                if "Due" not in reason and "Overdue" not in reason:
                    reason = "Urgent priority"
            elif t.priority == 'high':
                score += 30
                if "Due" not in reason and "Overdue" not in reason:
                    reason = "High priority"
            elif t.priority == 'medium':
                score += 20
            else:
                score += 10

            # Status scoring
            if t.status == STATUS_CHANGES_REQUESTED:
                score += 30
                reason = "Changes requested by reviewer"
            elif t.status == STATUS_IN_PROGRESS:
                score += 15
                if "Due" not in reason and "Overdue" not in reason and "Urgent" not in reason:
                    reason = "Currently in progress"
            elif t.status in (STATUS_TODO, STATUS_PENDING):
                score += 10
            elif t.status == STATUS_BLOCKED:
                score -= 15  # Blocked items can't be easily progressed
                if "Overdue" not in reason:
                    reason = "Blocked — requires resolution"
            elif t.status in (STATUS_IN_REVIEW, 'review'):
                score -= 25  # Waiting on reviewer

            scored.append({
                'task': t.to_dict(),
                'score': score,
                'reason': reason
            })

        scored.sort(key=lambda x: x['score'], reverse=True)
        if scored:
            smart_next = scored[0]

    # Personal Weekly Progress
    monday = today - timedelta(days=today.weekday())
    monday_dt = datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc)
    completed_this_week = sum(
        1 for t in tasks
        if t.status == STATUS_COMPLETED and t.completed_at and (
            t.completed_at.date() >= monday if hasattr(t.completed_at, 'date') else True
        )
    )
    assigned_this_week = sum(
        1 for t in tasks
        if t.created_at and (
            t.created_at.date() >= monday if hasattr(t.created_at, 'date') else True
        )
    )
    weekly_progress = {
        'start_of_week': monday.isoformat(),
        'assigned_this_week': assigned_this_week,
        'completed_this_week': completed_this_week,
        'awaiting_review': in_review,
        'overdue': overdue,
        'completion_trend': f"{completed_this_week} completed this week"
    }

    # Recent Activity for the user's tasks
    recent_activity = []
    task_ids = list(task_map.keys())
    if task_ids:
        histories = TaskStatusHistory.query.filter(
            TaskStatusHistory.task_id.in_(task_ids)
        ).order_by(TaskStatusHistory.created_at.desc()).limit(15).all()

        for h in histories:
            t = task_map.get(h.task_id)
            recent_activity.append({
                'id': h.id,
                'task_id': h.task_id,
                'task_title': t.title if t else 'Task',
                'actor_id': h.changed_by_id,
                'actor_name': (h.changed_by.full_name or h.changed_by.username) if h.changed_by else 'System',
                'old_status': h.old_status,
                'new_status': h.new_status,
                'comment': h.comment or 'Status updated',
                'created_at': h.created_at.isoformat() if h.created_at else None,
                'type': 'status_change'
            })

        submissions = WorkSubmission.query.filter(
            WorkSubmission.task_id.in_(task_ids)
        ).order_by(WorkSubmission.created_at.desc()).limit(10).all()

        for s in submissions:
            t = task_map.get(s.task_id)
            recent_activity.append({
                'id': f"sub-{s.id}",
                'task_id': s.task_id,
                'task_title': t.title if t else 'Task',
                'actor_id': s.user_id,
                'actor_name': (s.user.full_name or s.user.username) if s.user else 'Employee',
                'old_status': 'in_progress',
                'new_status': 'in_review',
                'comment': f"Work submitted: {s.comments or 'Deliverables ready'}",
                'created_at': s.created_at.isoformat() if s.created_at else None,
                'type': 'work_submission'
            })

        recent_activity.sort(key=lambda x: x['created_at'] or '', reverse=True)
        recent_activity = recent_activity[:15]

    # Employee Attendance Summary
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    today_records = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        Attendance.check_in >= today_start,
        Attendance.check_in <= today_end
    ).all()
    today_mins = sum(r.duration_minutes or 0 for r in today_records)
    today_hours = round(today_mins / 60.0, 1)

    week_start = datetime.combine(monday, datetime.min.time())
    week_records = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        Attendance.check_in >= week_start
    ).all()
    week_mins = sum(r.duration_minutes or 0 for r in week_records)
    week_hours = round(week_mins / 60.0, 1)

    recent_sessions = [
        r.to_dict() for r in sorted(week_records, key=lambda r: r.check_in or datetime.min, reverse=True)[:5]
    ]

    return api_success({
        'total': total,
        'personal_count': personal_count,
        'assigned_count': assigned_count,
        'todo': todo,
        'in_progress': in_progress,
        'in_review': in_review,
        'blocked': blocked,
        'changes_requested': changes_requested,
        'completed': completed,
        'overdue': overdue,
        'due_today': due_today,
        'high_priority': high_priority,
        'pending': pending,
        'completion_rate': completion_rate,
        'by_category': by_category,
        'upcoming': upcoming_tasks,
        'smart_next': smart_next,
        'weekly_progress': weekly_progress,
        'recent_activity': recent_activity,
        'attendance_summary': {
            'today_hours': today_hours,
            'week_hours': week_hours,
            'recent_sessions': recent_sessions
        }
    })
