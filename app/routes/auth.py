"""
Authentication and profile management API endpoints.

Endpoints
---------
POST /api/auth/signup          Register a new account (role = employee)
POST /api/auth/register        Alias for signup
POST /api/auth/login           Authenticate; deactivated accounts are rejected
POST /api/auth/logout          End session
GET  /api/auth/me              Current user profile
GET  /api/auth/profile         Same as /me (named alias)
PUT  /api/auth/profile         Update own display name
POST /api/auth/change-password Securely change own password
"""
import re
from flask import Blueprint, request, session
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models import User, Category, ROLE_EMPLOYEE
from app.routes.utils import api_success, api_error, active_account_required


auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ── Registration ───────────────────────────────────────────────────────────────

@auth_bp.route('/signup', methods=['POST'])
@auth_bp.route('/register', methods=['POST'])
def signup():
    data      = request.get_json(silent=True) or {}
    email     = (data.get('email') or '').strip().lower()
    password  = data.get('password') or ''
    full_name = (data.get('full_name') or data.get('username') or '').strip()
    username  = (data.get('username') or '').strip()

    if not email or not EMAIL_REGEX.match(email):
        return api_error('A valid email address is required.', 400)

    if not password or len(password) < 6:
        return api_error('Password must be at least 6 characters long.', 400)

    if not username:
        base_username = email.split('@')[0]
        username = re.sub(r'[^a-zA-Z0-9_]', '_', base_username)

    if User.query.filter_by(email=email).first():
        return api_error('Email is already registered.', 409)

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        username = f'{username}_{User.query.count() + 1}'

    user = User(
        username=username,
        full_name=full_name or username,
        email=email,
        role=ROLE_EMPLOYEE,    # all self-registrations start as employees
        account_active=True,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    # Starter categories for convenience
    for cat_name in ('Work', 'Personal', 'Projects'):
        db.session.add(Category(name=cat_name, user_id=user.id))
    db.session.commit()

    login_user(user, remember=True)
    return api_success(user.to_dict(), message='User registered successfully', status_code=201)


# ── Login / Logout ─────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['POST'])
def login():
    data     = request.get_json(silent=True) or {}
    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    remember = bool(data.get('remember', False))
    requested_role = (data.get('required_role') or '').strip().lower()

    if requested_role not in ('', 'admin', 'team_lead', 'employee'):
        return api_error('Invalid sign-in type.', 400)

    if not email or not password:
        return api_error('Email and password are required.', 400)

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return api_error('Invalid email or password.', 401)

    # A role-specific sign-in page may only authenticate matching account types.
    # Check this before login_user so a wrong-role attempt cannot create a session.
    if requested_role == 'admin' and user.role not in ('super_admin', 'admin', 'admin_hr'):
        return api_error('This account does not have administrator access. Use the correct sign-in page.', 403)
    if requested_role == 'team_lead' and user.role not in ('team_lead', 'super_admin', 'admin', 'admin_hr'):
        return api_error('This account does not have Team Lead access. Use Employee Login instead.', 403)
    if requested_role == 'employee' and user.role != 'employee':
        return api_error('This is not an employee account. Please use the correct sign-in page.', 403)

    # Reject deactivated accounts before creating a session
    if not user.account_active:
        return api_error(
            'Your account has been deactivated. '
            'Please contact your administrator.', 403
        )

    login_user(user, remember=remember)
    return api_success(user.to_dict(), message='Logged in successfully')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return api_success(message='Logged out successfully')


# ── Current user info ──────────────────────────────────────────────────────────

@auth_bp.route('/me', methods=['GET'])
def get_me():
    if current_user.is_authenticated:
        return api_success(current_user.to_dict())
    return api_error('Not authenticated', 401)


# ── Profile management ─────────────────────────────────────────────────────────

@auth_bp.route('/profile', methods=['GET', 'PUT'])
@login_required
@active_account_required
def profile():
    """
    GET  — Return the authenticated user's profile.
    PUT  — Update permitted profile fields (display name only).
            Users cannot change their own role via this endpoint.
    """
    if request.method == 'GET':
        return api_success(current_user.to_dict())

    # PUT — update profile
    data      = request.get_json(silent=True) or {}
    full_name = (data.get('full_name') or '').strip()

    if not full_name:
        return api_error('Display name is required.', 400)
    if len(full_name) < 2:
        return api_error('Display name must be at least 2 characters.', 400)
    if len(full_name) > 100:
        return api_error('Display name must be 100 characters or fewer.', 400)

    # Silently ignore any attempt to change role — never honour client-supplied role
    current_user.full_name = full_name
    db.session.commit()
    return api_success(current_user.to_dict(), message='Profile updated successfully.')


# ── Password management ────────────────────────────────────────────────────────

@auth_bp.route('/change-password', methods=['POST'])
@login_required
@active_account_required
def change_password():
    """
    Securely change the authenticated user's password.

    Rules
    -----
    - Current password must verify against the stored hash.
    - New password must be ≥ 8 characters.
    - New password must differ from the current one.
    - Confirmation must match new password.
    - Response never contains any password value.
    - Session is rotated after success to invalidate other open sessions.
    """
    data             = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password     = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not current_password or not new_password or not confirm_password:
        return api_error('All password fields are required.', 400)

    if not current_user.check_password(current_password):
        return api_error('Current password is incorrect.', 401)

    if len(new_password) < 8:
        return api_error('New password must be at least 8 characters.', 400)

    if new_password != confirm_password:
        return api_error('New password and confirmation do not match.', 400)

    if current_user.check_password(new_password):
        return api_error('New password must differ from the current password.', 400)

    current_user.set_password(new_password)
    db.session.commit()

    # Rotate the session so other browser sessions / devices are invalidated
    session.clear()
    login_user(current_user)

    return api_success(
        message='Password changed successfully. Please log in again on other devices.'
    )


# ── Password Recovery ─────────────────────────────────────────────────────────

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Initiates a secure password reset flow."""
    import secrets
    from datetime import datetime, timezone, timedelta
    from app.models import PasswordResetToken

    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()

    if not email or not EMAIL_REGEX.match(email):
        return api_error('A valid email address is required.', 400)

    user = User.query.filter_by(email=email).first()
    if not user or not user.account_active:
        # Prevent user enumeration by returning consistent success message
        return api_success(message='If this email is registered, password reset instructions have been generated.')

    # Invalidate older pending tokens for this user
    PasswordResetToken.query.filter_by(user_id=user.id, is_used=False).update({'is_used': True})

    # Generate cryptographically secure token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at
    )
    db.session.add(reset_token)
    db.session.commit()

    reset_url = f'/reset-password/{token}'
    return api_success(
        {'reset_url': reset_url, 'token': token},
        message='Password reset instructions generated successfully.'
    )


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Resets user password with a validated token."""
    from app.models import PasswordResetToken

    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not token:
        return api_error('Reset token is required.', 400)

    if not new_password or len(new_password) < 8:
        return api_error('New password must be at least 8 characters long.', 400)

    if new_password != confirm_password:
        return api_error('Passwords do not match.', 400)

    reset_token = PasswordResetToken.query.filter_by(token=token).first()
    if not reset_token or not reset_token.is_valid():
        return api_error('Reset token is invalid or has expired. Please request a new one.', 400)

    user = User.query.get(reset_token.user_id)
    if not user or not user.account_active:
        return api_error('User account is invalid or deactivated.', 400)

    user.set_password(new_password)
    reset_token.is_used = True
    db.session.commit()

    return api_success(message='Password has been reset successfully. You may now sign in.')

