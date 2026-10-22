"""
Server-rendered page routes.

All authenticated pages check both login state (via @login_required)
and account-active state (via the before_request hook below).
"""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

web_bp = Blueprint('web', __name__)


# ── Active-account guard ───────────────────────────────────────────────────────

@web_bp.before_request
def check_account_active():
    """
    Before every page request on this blueprint: if the user is logged in
    but their account has been deactivated, force-log them out and redirect
    to the login page.

    Uses a raw SQL scalar query to bypass SQLAlchemy's identity-map cache
    so that admin-side deactivation takes effect on the very next request.
    """
    if current_user.is_authenticated:
        from app import db
        # Raw scalar bypasses the ORM identity-map so we always read from DB
        result = db.session.execute(
            text('SELECT account_active FROM users WHERE id = :uid'),
            {'uid': current_user.id}
        ).fetchone()
        is_active = result[0] if result else False
        if not is_active:
            from flask_login import logout_user
            logout_user()
            return redirect(url_for('web.login_page'))



# ── Public routes (no authentication required) ─────────────────────────────────

@web_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard'))
    return render_template('index.html')


@web_bp.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard'))
    return render_template('login.html')


@web_bp.route('/signup')
def signup_page():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard'))
    return render_template('signup.html')


# ── Private routes (login + active account required) ──────────────────────────

@web_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')


@web_bp.route('/tasks')
@login_required
def tasks():
    return render_template('tasks.html', active_page='tasks')


@web_bp.route('/categories')
@login_required
def categories():
    return render_template('categories.html', active_page='categories')


@web_bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', active_page='profile')


@web_bp.route('/settings')
@login_required
def settings():
    """Account settings: display-name editing and password change."""
    return render_template('settings.html', active_page='settings')


@web_bp.route('/employees')
@login_required
def employees():
    """Employee directory with search, filters, and team/department assignments."""
    return render_template('employees.html', active_page='employees')


@web_bp.route('/teams')
@login_required
def teams():
    """Department and team administration with member rosters and team tasks."""
    return render_template('teams.html', active_page='teams')
