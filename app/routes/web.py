"""
Server-rendered page routes.

All authenticated pages check both login state (via @login_required)
and account-active state (via the before_request hook below).
"""
from datetime import date, timedelta
from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, text

from app.models import Task
from app.services.workload import team_workload, workload_state_counts, workload_summary
from app.services.analytics import employee_analytics, parse_period

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
    if current_user.role != 'employee':
        team_dashboard = current_user.role == 'team_lead'
        dashboard_team_workload = team_workload(current_user) if team_dashboard else []
        return render_template(
            'dashboard.html',
            active_page='dashboard',
            team_workload=dashboard_team_workload if team_dashboard else None,
            team_workload_counts=workload_state_counts(dashboard_team_workload),
            team_workload_dashboard=team_dashboard,
        )

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    tasks = Task.query.filter(
        or_(
            Task.user_id == current_user.id,
            Task.assigned_to_id == current_user.id,
        )
    ).all()

    open_tasks = [task for task in tasks if task.status != 'completed']
    due_today = [task for task in open_tasks if task.due_date == today]
    overdue = [
        task for task in open_tasks
        if task.due_date is not None and task.due_date < today
    ]
    completed_this_week = [
        task for task in tasks
        if task.status == 'completed'
        and task.completed_at is not None
        and week_start <= task.completed_at.date() <= today
    ]

    displayed_ids = {task.id for task in overdue + due_today}
    high_priority = [
        task for task in open_tasks
        if task.id not in displayed_ids and task.priority == 'high'
    ]
    displayed_ids.update(task.id for task in high_priority)
    in_progress = [
        task for task in open_tasks
        if task.id not in displayed_ids and task.status == 'in_progress'
    ]

    completed_due_today = [
        task for task in tasks
        if task.due_date == today
        and task.status == 'completed'
        and task.completed_at is not None
        and task.completed_at.date() == today
    ]
    upcoming_deadlines = sorted(
        [
            task for task in open_tasks
            if task.due_date is not None
            and task.due_date <= today + timedelta(days=7)
        ],
        key=lambda task: (task.due_date, task.id),
    )

    def task_sort_key(task):
        return (task.due_date is None, task.due_date or date.max, -(task.id or 0))

    return render_template(
        'dashboard.html',
        active_page='dashboard',
        employee_dashboard=True,
        dashboard_today=today,
        dashboard_yesterday=today - timedelta(days=1),
        dashboard_tasks={
            'overdue': sorted(overdue, key=task_sort_key),
            'due_today': sorted(due_today, key=task_sort_key),
            'high_priority': sorted(high_priority, key=task_sort_key),
            'in_progress': sorted(in_progress, key=task_sort_key),
        },
        dashboard_counts={
            'open': len(open_tasks),
            'due_today': len(due_today),
            'overdue': len(overdue),
            'completed_this_week': len(completed_this_week),
        },
        daily_progress={
            'completed': len(completed_due_today),
            'due': sum(1 for task in tasks if task.due_date == today),
        },
        workload_summary=workload_summary(current_user, tasks=tasks),
        upcoming_deadlines=upcoming_deadlines,
        dashboard_analytics=employee_analytics(
            current_user, today - timedelta(days=6), today
        ),
    )


@web_bp.route('/tasks')
@login_required
def tasks():
    return render_template('tasks.html', active_page='tasks')


@web_bp.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html', active_page='calendar')


@web_bp.route('/goals')
@login_required
def goals():
    return render_template('goals.html', active_page='goals')


@web_bp.route('/decisions')
@login_required
def decisions():
    return render_template('decisions.html', active_page='decisions')

@web_bp.route('/focus')
@login_required
def focus():
    return render_template('focus.html', active_page='focus')

@web_bp.route('/workflow-templates')
@login_required
def workflow_templates():
    return render_template('workflow_templates.html', active_page='workflow_templates')

@web_bp.route('/automation')
@login_required
def automation():
    return render_template('automation.html', active_page='automation')

@web_bp.route('/tasks/<int:task_id>')
@login_required
def task_detail(task_id):
    return render_template('task_detail.html', active_page='tasks', task_id=task_id)


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


@web_bp.route('/activity')
@login_required
def activity():
    return render_template('activity.html', active_page='activity')
