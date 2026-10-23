"""
Server-rendered page routes.

All authenticated pages check login state (via @login_required)
and account-active state (via before_request hook).
Provides distinct URLs for public flows, admin modules, lead workflows,
employee tools, and task detail views.
"""
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, abort
from flask_login import current_user, login_required
from sqlalchemy import text
from app import db
from app.models import Task, User

web_bp = Blueprint('web', __name__)


# ── Active-account guard ───────────────────────────────────────────────────────

@web_bp.before_request
def check_account_active():
    """
    Before every page request on this blueprint: if the user is logged in
    but their account has been deactivated, force-log them out and redirect
    to the login page.
    """
    if current_user.is_authenticated:
        result = db.session.execute(
            text('SELECT account_active FROM users WHERE id = :uid'),
            {'uid': current_user.id}
        ).fetchone()
        is_active = result[0] if result else False
        if not is_active:
            from flask_login import logout_user
            logout_user()
            return redirect(url_for('web.login_page'))


def web_roles_required(*roles):
    """Decorator to restrict web pages to specific user roles, redirecting to /unauthorized."""
    allowed = set(roles)
    if 'admin' in allowed or 'admin_hr' in allowed:
        allowed.add('admin')
        allowed.add('admin_hr')

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('web.login_page', next=request.path))
            if current_user.role not in allowed:
                return redirect(url_for('web.unauthorized_page'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ── Public routes ──────────────────────────────────────────────────────────────

@web_bp.route('/')
def index():
    # Authenticated users should not be able to navigate back to the public
    # landing page as if their session were anonymous.
    if current_user.is_authenticated:
        return redirect(_role_home(current_user.role))
    return render_template('index.html')


def _role_home(role):
    if role in ('super_admin', 'admin', 'admin_hr'):
        return url_for('web.admin_dashboard')
    if role == 'team_lead':
        return url_for('web.lead_dashboard')
    return url_for('web.employee_dashboard')


@web_bp.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(_role_home(current_user.role))
    return render_template('login.html', expected_role='')


@web_bp.route('/admin/login')
def admin_login_page():
    if current_user.is_authenticated:
        if current_user.role in ('super_admin', 'admin', 'admin_hr'):
            return redirect(url_for('web.admin_dashboard'))
        return redirect(url_for('web.unauthorized_page'))
    return render_template('login.html', expected_role='admin', login_heading='Administrator Sign In')


@web_bp.route('/lead/login')
def lead_login_page():
    if current_user.is_authenticated:
        if current_user.role == 'team_lead' or current_user.role in ('super_admin', 'admin', 'admin_hr'):
            return redirect(_role_home(current_user.role))
        return redirect(url_for('web.unauthorized_page'))
    return render_template('login.html', expected_role='team_lead', login_heading='Team Lead Sign In')


@web_bp.route('/employee/login')
def employee_login_page():
    if current_user.is_authenticated:
        if current_user.role == 'employee':
            return redirect(url_for('web.employee_dashboard'))
        return redirect(_role_home(current_user.role))
    return render_template('login.html', expected_role='employee', login_heading='Employee Sign In')


@web_bp.route('/signup')
def signup_page():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard'))
    return render_template('signup.html')


@web_bp.route('/forgot-password')
def forgot_password_page():
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard'))
    return render_template('forgot_password.html')


@web_bp.route('/reset-password/<token>')
def reset_password_page(token):
    if current_user.is_authenticated:
        return redirect(url_for('web.dashboard'))
    return render_template('reset_password.html', token=token)


@web_bp.route('/unauthorized')
def unauthorized_page():
    return render_template('unauthorized.html'), 403


# ── Core Dashboard Route (Role Adaptive) ──────────────────────────────────────

@web_bp.route('/dashboard')
def dashboard():
    # Keep the public homepage as the default for anonymous visitors.
    if not current_user.is_authenticated:
        return redirect(url_for('web.index'))
    # A generic dashboard URL must never show a role-neutral page or bypass role routing.
    return redirect(_role_home(current_user.role))


# ── Admin Module Routes (/admin/*) ───────────────────────────────────────────

@web_bp.route('/admin/dashboard')
@web_roles_required('super_admin', 'admin_hr')
def admin_dashboard():
    return render_template('dashboard.html', active_page='admin_dashboard')


@web_bp.route('/admin/employees')
@web_roles_required('super_admin', 'admin_hr')
def admin_employees():
    return render_template('employees.html', active_page='employees')


@web_bp.route('/admin/teams')
@web_roles_required('super_admin', 'admin_hr')
def admin_teams():
    return render_template('organization.html', active_page='organization', active_tab='teams')


@web_bp.route('/admin/roles-permissions')
@web_roles_required('super_admin', 'admin_hr')
def admin_roles_permissions():
    return render_template('organization.html', active_page='organization', active_tab='audit')


@web_bp.route('/admin/attendance')
@web_roles_required('super_admin', 'admin_hr')
def admin_attendance():
    return render_template('attendance.html', active_page='attendance', active_tab='team-attendance')


@web_bp.route('/admin/tasks')
@web_roles_required('super_admin', 'admin_hr')
def admin_tasks():
    return render_template('tasks.html', active_page='tasks')


@web_bp.route('/admin/reports')
@web_roles_required('super_admin', 'admin_hr')
def admin_reports():
    return render_template('reports.html', active_page='reports')


@web_bp.route('/admin/settings')
@web_roles_required('super_admin', 'admin_hr')
def admin_settings():
    return render_template('settings.html', active_page='settings')


# ── Team Lead Module Routes (/lead/*) ─────────────────────────────────────────

@web_bp.route('/lead/dashboard')
@web_roles_required('super_admin', 'admin_hr', 'team_lead')
def lead_dashboard():
    return render_template('dashboard.html', active_page='lead_dashboard')


@web_bp.route('/lead/team')
@web_roles_required('super_admin', 'admin_hr', 'team_lead')
def lead_team():
    return render_template('organization.html', active_page='organization', active_tab='teams')


@web_bp.route('/lead/tasks')
@web_roles_required('super_admin', 'admin_hr', 'team_lead')
def lead_tasks():
    return render_template('tasks.html', active_page='tasks')


@web_bp.route('/lead/tasks/new')
@web_roles_required('super_admin', 'admin_hr', 'team_lead')
def lead_tasks_new():
    return render_template('tasks.html', active_page='tasks', auto_open_add=True)


@web_bp.route('/lead/reviews')
@web_roles_required('super_admin', 'admin_hr', 'team_lead')
def lead_reviews():
    return render_template('tasks.html', active_page='tasks', default_status='in_review')


@web_bp.route('/lead/calendar')
@web_roles_required('super_admin', 'admin_hr', 'team_lead')
def lead_calendar():
    return render_template('calendar.html', active_page='calendar')


@web_bp.route('/lead/meetings')
@web_roles_required('super_admin', 'admin_hr', 'team_lead')
def lead_meetings():
    return render_template('calendar.html', active_page='calendar', auto_open_meeting=True)


# ── Employee Module Routes (/employee/*) ──────────────────────────────────────

@web_bp.route('/employee/dashboard')
@login_required
def employee_dashboard():
    return render_template('dashboard.html', active_page='employee_dashboard')


@web_bp.route('/employee/my-tasks')
@login_required
def employee_my_tasks():
    return render_template('tasks.html', active_page='tasks')


@web_bp.route('/employee/calendar')
@login_required
def employee_calendar():
    return render_template('calendar.html', active_page='calendar')


@web_bp.route('/employee/attendance')
@login_required
def employee_attendance():
    return render_template('attendance.html', active_page='attendance')


@web_bp.route('/employee/meetings')
@login_required
def employee_meetings():
    return render_template('calendar.html', active_page='calendar')


@web_bp.route('/employee/notifications')
@login_required
def employee_notifications():
    return render_template('dashboard.html', active_page='dashboard', open_notifications=True)


# ── Dedicated Task Detail View ────────────────────────────────────────────────

@web_bp.route('/tasks/<int:task_id>')
@login_required
def task_detail_view(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return render_template('404.html'), 404

    # Authorization: Admins/HR, Creator, Assignee, or Lead of the task's team
    user = current_user
    is_authorized = (
        user.is_admin or
        task.user_id == user.id or
        task.assignee_id == user.id or
        task.creator_id == user.id or
        (task.team and task.team.lead_id == user.id)
    )
    if not is_authorized:
        return redirect(url_for('web.unauthorized_page'))

    creator_name = 'Unknown'
    if task.creator_id:
        creator = db.session.get(User, task.creator_id)
        if creator:
            creator_name = creator.full_name or creator.username
    elif task.user:
        creator_name = task.user.full_name or task.user.username

    assignee_name = 'Unassigned'
    if task.assignee:
        assignee_name = task.assignee.full_name or task.assignee.username

    team_name = task.team.name if task.team else 'General / Personal'

    return render_template(
        'task_detail.html',
        task=task,
        creator_name=creator_name,
        assignee_name=assignee_name,
        team_name=team_name,
        active_page='tasks'
    )


# ── Shared Application Pages ──────────────────────────────────────────────────

@web_bp.route('/tasks')
@login_required
def tasks():
    return render_template('tasks.html', active_page='tasks')


@web_bp.route('/categories')
@login_required
def categories():
    return render_template('categories.html', active_page='categories')


@web_bp.route('/attendance')
@login_required
def attendance():
    return render_template('attendance.html', active_page='attendance')


@web_bp.route('/leaves')
@login_required
def leaves():
    return render_template('leaves.html', active_page='leaves')


@web_bp.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html', active_page='calendar')


@web_bp.route('/teams')
@login_required
def teams():
    return render_template('organization.html', active_page='teams')


@web_bp.route('/employees')
@login_required
def employees():
    return render_template('employees.html', active_page='employees')


@web_bp.route('/organization')
@login_required
def organization():
    return render_template('organization.html', active_page='organization')


@web_bp.route('/reports')
@login_required
def reports():
    return render_template('reports.html', active_page='reports')


@web_bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', active_page='profile')


@web_bp.route('/settings')
@login_required
def settings():
    return render_template('settings.html', active_page='settings')
