"""
In-App Notifications API routes.
"""
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.models import Notification
from app.routes.utils import api_success, api_error, active_account_required

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


@notifications_bp.route('', methods=['GET'])
@login_required
@active_account_required
def get_notifications():
    notifs = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()

    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()

    return api_success({
        'notifications': [n.to_dict() for n in notifs],
        'unread_count': unread_count,
    })


@notifications_bp.route('/<int:notif_id>/read', methods=['PATCH'])
@login_required
@active_account_required
def mark_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return api_success(notif.to_dict(), message='Notification marked as read.')


@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
@active_account_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return api_success(message='All notifications marked as read.')
