"""
Shared API response helpers and authorization decorators.
"""
from functools import wraps
from flask import jsonify
from flask_login import current_user


# ── JSON envelope helpers ──────────────────────────────────────────────────────

def api_success(data=None, message=None, status_code=200):
    payload = {'ok': True}
    if data is not None:
        payload['data'] = data
    if message:
        payload['message'] = message
    return jsonify(payload), status_code


def api_error(message, status_code=400):
    return jsonify({'ok': False, 'error': message}), status_code


# ── Authorization decorators ───────────────────────────────────────────────────

def roles_required(*roles):
    """
    Restrict an endpoint to users with one of the specified roles.

    Usage::

        @app.route('/admin/panel')
        @login_required
        @roles_required('super_admin', 'admin')
        def admin_panel():
            ...

    Returns 403 JSON for authenticated users without the required role.
    Returns 401 JSON for unauthenticated requests.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return api_error('Authentication required.', 401)
            if current_user.role not in roles:
                return api_error(
                    'You do not have permission to perform this action.', 403
                )
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def active_account_required(fn):
    """
    Block deactivated accounts from calling the endpoint.

    Apply **after** @login_required so current_user is populated.
    Uses a raw SQL scalar to bypass SQLAlchemy's identity-map cache so that
    admin-side account deactivation is detected immediately.
    Returns 403 if the account has been deactivated by an admin.
    """
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return api_error('Authentication required.', 401)
        # Raw scalar bypasses the ORM identity-map / cached proxy
        from app import db
        from sqlalchemy import text
        result = db.session.execute(
            text('SELECT account_active FROM users WHERE id = :uid'),
            {'uid': current_user.id}
        ).fetchone()
        is_active = result[0] if result else False
        if not is_active:
            return api_error(
                'Your account has been deactivated. '
                'Please contact your administrator.', 403
            )
        return fn(*args, **kwargs)
    return wrapped
