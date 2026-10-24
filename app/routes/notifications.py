"""
In-App Notifications API routes.
"""
from datetime import datetime, date, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import Notification, Task, Attendance
from app.routes.utils import api_success, api_error, active_account_required, send_notification

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


def generate_automated_reminders(user_id):
    """Generate deadline, overdue, and attendance reminders with strict idempotency."""
    today = date.today()
    today_str = today.isoformat()

    # 1. Task Due Today & Overdue reminders
    user_tasks = Task.query.filter(
        (Task.assignee_id == user_id) | (Task.user_id == user_id),
        Task.due_date.isnot(None),
        Task.status != 'completed'
    ).all()

    for t in user_tasks:
        if t.due_date == today:
            send_notification(
                user_id,
                f'Task Due Today: {t.title}',
                f'"{t.title}" is due today. Priority: {t.priority.upper()}.',
                f'/tasks/{t.id}',
                'deadline',
                idempotency_key=f'due-today-{t.id}-{today_str}'
            )
        elif t.due_date < today:
            send_notification(
                user_id,
                f'Task Overdue: {t.title}',
                f'"{t.title}" was due on {t.due_date.strftime("%b %d")} and is currently overdue.',
                f'/tasks/{t.id}',
                'overdue',
                idempotency_key=f'overdue-{t.id}-{today_str}'
            )

    # 2. Attendance shift reminder (weekdays)
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() < 5 and now_utc.hour >= 4: # Working hours check
        today_start = datetime.combine(today, datetime.min.time())
        has_session_today = Attendance.query.filter(
            Attendance.user_id == user_id,
            Attendance.check_in >= today_start
        ).first()
        if not has_session_today:
            send_notification(
                user_id,
                'Attendance Reminder',
                "You have not checked in for today's work shift yet. Please check in on your dashboard.",
                '/employee/attendance',
                'attendance',
                idempotency_key=f'att-reminder-{user_id}-{today_str}'
            )


@notifications_bp.route('', methods=['GET'])
@login_required
@active_account_required
def get_notifications():
    # Trigger automated reminders for due tasks, overdue tasks, and attendance
    generate_automated_reminders(current_user.id)

    notifs = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(100).all()

    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()

    return api_success({
        'notifications': [n.to_dict() for n in notifs],
        'unread_count': unread_count,
    })


@notifications_bp.route('/<int:notif_id>/read', methods=['PATCH', 'POST', 'PUT'])
@login_required
@active_account_required
def mark_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return api_success(notif.to_dict(), message='Notification marked as read.')


@notifications_bp.route('/mark-all-read', methods=['POST', 'PATCH'])
@login_required
@active_account_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return api_success(message='All notifications marked as read.')
