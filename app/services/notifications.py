"""Database-backed in-app notifications, activity records, and reminders."""

from datetime import date, timedelta
from sqlalchemy import or_

from app import db
from app.models import Activity, Notification, Task, User

EVENT_COPY = {
    'task_created': ('New task', 'A new task was created for you.'),
    'task_assigned': ('Task assigned', 'A task was assigned to you.'),
    'task_reassigned': ('Task assignment changed', 'A task assignment changed.'),
    'status_changed': ('Task status changed', 'The status of a task you can access changed.'),
    'deadline_updated': ('Deadline updated', 'A task deadline was updated.'),
    'comment_created': ('New task discussion', 'A new discussion message was posted.'),
    'reference_uploaded': ('New task attachment', 'A reference file was added to a task.'),
    'submission_created': ('Work submitted', 'Work was submitted for review.'),
    'review_approved': ('Task approved', 'A task submission was approved.'),
    'review_changes_requested': ('Changes requested', 'Changes were requested on a task.'),
    'deadline_reminder': ('Deadline approaching', 'A task deadline is approaching.'),
    'task_overdue': ('Task overdue', 'A task assigned to you is overdue.'),
    'dependency_added': ('Task dependency added', 'A task dependency was added.'),
    'dependency_removed': ('Task dependency removed', 'A task dependency was removed.'),
    'dependency_cleared': ('Task dependency cleared', 'A task dependency was completed.'),
    'dependency_reopened': ('Task dependency reopened', 'A completed dependency was reopened.'),
    'handover_created': ('Task handover requested', 'A task handover is waiting for your acknowledgement.'),
    'handover_accepted': ('Task handover accepted', 'A task handover was accepted.'),
    'handover_declined': ('Task handover declined', 'A task handover was declined.'),
    'handover_cancelled': ('Task handover cancelled', 'A task handover was cancelled.'),
}


def notify_task_collaboration_event(event_type, task, actor=None, recipients=None,
                                    metadata=None, event_key=None):
    """Create deduplicated notifications and one corresponding activity record."""
    metadata = metadata or {}
    recipient_ids = {rid for rid in (recipients or []) if rid and (not actor or rid != actor.id)}
    title, default_message = EVENT_COPY.get(
        event_type, ('Task activity', 'A task you can access was updated.')
    )
    message = metadata.get('message', default_message)
    key = event_key or metadata.get('event_key')
    if not key and metadata.get('event_id') and task:
        key = f'{event_type}:{task.id}:{metadata["event_id"]}'
    if not key or not Activity.query.filter_by(event_key=key).first():
        db.session.add(Activity(
            actor_id=actor.id if actor else None,
            task_id=task.id if task else None,
            activity_type=event_type,
            description=metadata.get('description', message),
            event_key=key,
        ))

    for recipient_id in recipient_ids:
        notification_key = f'{key}:user:{recipient_id}' if key else None
        if notification_key and Notification.query.filter_by(event_key=notification_key).first():
            continue
        db.session.add(Notification(
            recipient_id=recipient_id,
            actor_id=actor.id if actor else None,
            task_id=task.id if task else None,
            notification_type=event_type,
            title=title,
            message=message,
            event_key=notification_key,
        ))

    db.session.commit()


def generate_deadline_reminders(today=None):
    """Create one reminder per assigned employee for tasks due tomorrow."""
    today = today or date.today()
    reminder_date = today + timedelta(days=1)
    tasks = Task.query.filter(
        Task.status != 'completed',
        Task.due_date == reminder_date,
    ).all()
    created = 0
    for task in tasks:
        recipient_ids = [task.assigned_to_id or task.user_id]
        key = f'deadline-reminder:{task.id}:{reminder_date.isoformat()}'
        before = Notification.query.filter(Notification.event_key.like(f'{key}:user:%')).count()
        notify_task_collaboration_event(
            'deadline_reminder',
            task,
            recipients=recipient_ids,
            metadata={
                'event_key': key,
                'message': f'"{task.title}" is due tomorrow.',
                'description': f'Deadline reminder for "{task.title}".',
            },
            event_key=key,
        )
        created += max(0, len(set(recipient_ids)) - before)
    return created
