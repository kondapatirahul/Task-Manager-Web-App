from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.models import Activity, Notification, Task
from app.routes.tasks import can_user_view_task
from app.routes.utils import active_account_required, api_error, api_success
from app.services.workload import authorized_task_query

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api')


def accessible_task_ids():
    if current_user.role == 'super_admin':
        return None
    return [row[0] for row in authorized_task_query(current_user).with_entities(Task.id).all()]


@notifications_bp.get('/notifications')
@active_account_required
@login_required
def list_notifications():
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    except (TypeError, ValueError):
        return api_error('Invalid pagination values.', 400)
    query = Notification.query.filter_by(recipient_id=current_user.id)
    pagination = query.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return api_success({
        'items': [item.to_dict() for item in pagination.items],
        'page': pagination.page,
        'pages': pagination.pages,
        'has_more': pagination.has_next,
        'unread_count': query.filter_by(is_read=False).count(),
    })


@notifications_bp.get('/notifications/unread-count')
@active_account_required
@login_required
def unread_notification_count():
    return api_success({
        'unread_count': Notification.query.filter_by(
            recipient_id=current_user.id, is_read=False
        ).count()
    })


@notifications_bp.patch('/notifications/<int:notification_id>/read')
@active_account_required
@login_required
def mark_notification_read(notification_id):
    notification = db.session.get(Notification, notification_id)
    if not notification or notification.recipient_id != current_user.id:
        return api_error('Notification not found.', 404)
    notification.is_read = True
    db.session.commit()
    return api_success(notification.to_dict())


@notifications_bp.post('/notifications/read-all')
@active_account_required
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(
        recipient_id=current_user.id, is_read=False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return api_success(message='Notifications marked as read.')


@notifications_bp.get('/activity')
@active_account_required
@login_required
def list_activity():
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    except (TypeError, ValueError):
        return api_error('Invalid pagination values.', 400)

    task_ids = accessible_task_ids()
    query = Activity.query
    if task_ids is not None:
        query = query.filter(Activity.task_id.in_(task_ids))
    if request.args.get('task_id'):
        try:
            query = query.filter(Activity.task_id == int(request.args['task_id']))
        except ValueError:
            return api_error('Invalid task filter.', 400)
    if request.args.get('type'):
        query = query.filter(Activity.activity_type == request.args['type'].strip()[:50])
    if request.args.get('from'):
        query = query.filter(Activity.created_at >= request.args['from'])
    if request.args.get('to'):
        query = query.filter(Activity.created_at <= request.args['to'])

    pagination = query.order_by(Activity.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return api_success({
        'items': [item.to_dict() for item in pagination.items],
        'page': pagination.page,
        'pages': pagination.pages,
        'has_more': pagination.has_next,
    })
