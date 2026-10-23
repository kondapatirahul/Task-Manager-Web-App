import os
import secrets
from flask import Flask, session, request, redirect, url_for, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()

def create_app(test_config=None):
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder='../templates',
        static_folder='../static'
    )

    # Ensure instance directory exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    default_db_path = os.path.join(app.instance_path, 'tasks.db')
    default_upload_path = os.getenv('TASKNEST_UPLOAD_FOLDER', os.path.join(app.instance_path, 'uploads'))
    try:
        os.makedirs(default_upload_path, exist_ok=True)
    except OSError:
        pass

    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'tasknest-dev-secret-key-change-in-prod'),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', f'sqlite:///{default_db_path}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        CSRF_ENABLED=True,
        UPLOAD_FOLDER=default_upload_path,
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
        MAX_ATTACHMENT_SIZE=5 * 1024 * 1024,
        MAX_ATTACHMENTS_PER_MESSAGE=5,
    )

    if test_config:
        app.config.update(test_config)

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        if request.path.startswith('/api/'):
            msg = e.name if e.code in (404, 405) else (e.description or e.name)
            response = app.response_class(
                response=app.json.dumps({'ok': False, 'error': msg}),
                status=e.code,
                mimetype='application/json'
            )
            for key, val in e.get_headers():
                if key.lower() not in ('content-type', 'content-length'):
                    response.headers[key] = val
            return response
        return e

    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        if request.path.startswith('/api/'):
            app.logger.error(f"Unhandled API error: {e}", exc_info=True)
            return {'ok': False, 'error': 'Internal server error'}, 500
        raise e

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'web.login_page'
    login_manager.login_message = 'Please log in to access this page.'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith('/api/'):
            return {'ok': False, 'error': 'Authentication required'}, 401
        return redirect(url_for('web.login_page', next=request.path))

    # CSRF Handling & Session Setup
    def get_csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        return session['csrf_token']

    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=get_csrf_token)

    @app.after_request
    def set_csrf_cookie(response):
        if 'csrf_token' in session:
            # Set cookie for JavaScript access
            response.set_cookie(
                'csrf_token',
                session['csrf_token'],
                samesite='Lax',
                secure=app.config.get('SESSION_COOKIE_SECURE', False),
                httponly=False
            )
        return response

    @app.before_request
    def check_csrf():
        # Skip CSRF check in testing mode or for safe methods
        if app.config.get('TESTING', False) or not app.config.get('CSRF_ENABLED', True):
            return
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return

        # Exempt initial auth signup/login endpoints if session doesn't exist yet
        # But if CSRF token was supplied, validate it.
        csrf_token = (
            request.headers.get('X-CSRFToken') or
            request.headers.get('X-CSRF-Token') or
            (request.form.get('csrf_token') if request.form else None)
        )

        expected_token = session.get('csrf_token')
<<<<<<< Updated upstream
        auth_bootstrap_paths = {'/api/auth/login', '/api/auth/signup', '/api/auth/register'}
        if (
            request.path in auth_bootstrap_paths
            and not current_user.is_authenticated
            and not expected_token
        ):
            return
        if not expected_token or not csrf_token:
            message = 'CSRF token required'
            if request.path.startswith('/api/'):
                return {'ok': False, 'error': message}, 403
            return message, 403
        if not secrets.compare_digest(csrf_token, expected_token):
            if request.path.startswith('/api/'):
                return {'ok': False, 'error': 'Invalid CSRF token'}, 403
            return 'Invalid CSRF token', 403
=======
        if expected_token and csrf_token:
            if not secrets.compare_digest(csrf_token, expected_token):
                if request.path.startswith('/api/'):
                    return {'ok': False, 'error': 'Invalid CSRF token'}, 403
                return 'Invalid CSRF token', 403
<<<<<<< Updated upstream

    # Error handlers
    from flask import render_template
    @app.errorhandler(400)
    def handle_400(e):
        if request.path.startswith('/api/'):
            return {'ok': False, 'error': getattr(e, 'description', 'Bad Request')}, 400
        return 'Bad Request', 400

    @app.errorhandler(403)
    def handle_403(e):
        if request.path.startswith('/api/'):
            return {'ok': False, 'error': 'Forbidden'}, 403
        return render_template('unauthorized.html'), 403

    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith('/api/'):
            return {'ok': False, 'error': 'Not Found'}, 404
        return render_template('404.html'), 404

    @app.errorhandler(405)
    def handle_405(e):
        if request.path.startswith('/api/'):
            headers = {}
            if hasattr(e, 'valid_methods') and e.valid_methods:
                headers['Allow'] = ', '.join(e.valid_methods)
            return {'ok': False, 'error': 'Method Not Allowed'}, 405, headers
        return 'Method Not Allowed', 405

    @app.errorhandler(415)
    def handle_415(e):
        if request.path.startswith('/api/'):
            return {'ok': False, 'error': 'Content-Type must be application/json'}, 415
        return 'Unsupported Media Type', 415

    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def handle_500(e):
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        if request.path.startswith('/api/'):
            return {'ok': False, 'error': 'Internal server error'}, 500
        return render_template('500.html'), 500
=======
>>>>>>> Stashed changes
>>>>>>> Stashed changes

    # Register blueprints
    from app.routes.web import web_bp
    from app.routes.auth import auth_bp
    from app.routes.tasks import tasks_bp
    from app.routes.categories import categories_bp
    from app.routes.stats import stats_bp
<<<<<<< Updated upstream
    from app.routes.organizations import organizations_bp
    from app.routes.departments import departments_bp
    from app.routes.teams import teams_bp
    from app.routes.employees import employees_bp
    from app.routes.notifications import notifications_bp
    from app.routes.workload import workload_bp
    from app.routes.calendar import calendar_bp
    from app.routes.analytics import analytics_bp
    from app.routes.decisions import decisions_bp
    from app.routes.focus_sessions import focus_bp
    from app.routes.workflow_templates import templates_bp
    from app.routes.automation import automation_bp
=======
    from app.routes.organization import org_bp
    from app.routes.employees import employees_bp
<<<<<<< Updated upstream
    from app.routes.attendance import attendance_bp
    from app.routes.meetings import meetings_bp
    from app.routes.notifications import notifications_bp
    from app.routes.discussions import discussions_bp
    from app.routes.reports import reports_bp
    from app.routes.teams import teams_bp
    from app.routes.departments import departments_bp
    from app.routes.organizations import organizations_bp
=======
>>>>>>> Stashed changes
>>>>>>> Stashed changes

    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(stats_bp)
<<<<<<< Updated upstream
    app.register_blueprint(organizations_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(workload_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(decisions_bp)
    app.register_blueprint(focus_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(automation_bp)
=======
    app.register_blueprint(org_bp)
    app.register_blueprint(employees_bp)
<<<<<<< Updated upstream
    app.register_blueprint(attendance_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(discussions_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(organizations_bp)
=======
>>>>>>> Stashed changes
>>>>>>> Stashed changes

    # CLI command to initialize database
    @app.cli.command('init-db')
    def init_db_command():
        """Initialize SQLite database tables."""
        with app.app_context():
            db.create_all()
        print("Database initialized successfully.")

<<<<<<< Updated upstream
    @app.cli.command('send-deadline-reminders')
    def send_deadline_reminders_command():
        """Create deduplicated in-app reminders for tasks due tomorrow."""
        from app.services.notifications import generate_deadline_reminders
        print(f"Created {generate_deadline_reminders()} deadline reminder(s).")

    @app.cli.command('run-automation')
    def run_automation_command():
        """Run overdue notifications and due recurring rules once."""
        from app.services.automation import run_automation
        print(run_automation())

    # Create tables automatically on start if they don't exist
=======
<<<<<<< Updated upstream
    @app.cli.command('process-recurring')
    def process_recurring_command():
        """CLI trigger to process recurring tasks on a schedule."""
        from datetime import date, timedelta
        from app.models import Task
        with app.app_context():
            today = date.today()
            recurring = Task.query.filter(Task.is_recurring == True, Task.status == 'completed').all()
            cnt = 0
            for t in recurring:
                interval = t.recurrence_interval or 'weekly'
                next_due = (
                    t.due_date + timedelta(days=1 if interval == 'daily' else 30 if interval == 'monthly' else 7)
                ) if t.due_date else None
                nxt = Task(
                    title=t.title,
                    description=t.description,
                    priority=t.priority,
                    status='todo',
                    due_date=next_due,
                    start_date=today,
                    category_id=t.category_id,
                    user_id=t.user_id,
                    assignee_id=t.assignee_id,
                    creator_id=t.creator_id,
                    team_id=t.team_id,
                    organization_id=t.organization_id,
                    is_recurring=True,
                    recurrence_interval=t.recurrence_interval
                )
                t.is_recurring = False
                db.session.add(nxt)
                cnt += 1
            db.session.commit()
            print(f"Spawned {cnt} recurring tasks.")

    # Create tables automatically on start and perform safe SQLite migrations
=======
    # Create tables automatically on start if they don't exist
>>>>>>> Stashed changes
>>>>>>> Stashed changes
    with app.app_context():
        db.create_all()
        # Automatically migrate existing SQLite database tables if missing new columns
        from sqlalchemy import inspect as sa_inspect, text
        try:
            inspector = sa_inspect(db.engine)
<<<<<<< Updated upstream
            if 'users' in inspector.get_table_names():
                existing_user_cols = {c['name'] for c in inspector.get_columns('users')}
                if 'role' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'employee' NOT NULL"))
                if 'account_active' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN account_active BOOLEAN DEFAULT 1 NOT NULL"))
                if 'organization_id' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN organization_id INTEGER"))
                if 'department_id' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN department_id INTEGER"))
                if 'job_title' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN job_title VARCHAR(100)"))
                if 'phone' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(30)"))
                if 'weekly_capacity_hours' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN weekly_capacity_hours FLOAT DEFAULT 40.0 NOT NULL"))
                if 'reports_to_id' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN reports_to_id INTEGER"))

=======
<<<<<<< Updated upstream
            table_names = set(inspector.get_table_names())

            # 1. Migrate `users` table
            if 'users' in table_names:
                user_cols = {c['name'] for c in inspector.get_columns('users')}
                user_migrations = [
                    ('role', "ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'employee' NOT NULL"),
                    ('account_active', "ALTER TABLE users ADD COLUMN account_active BOOLEAN DEFAULT 1 NOT NULL"),
                    ('organization_id', "ALTER TABLE users ADD COLUMN organization_id INTEGER"),
                    ('department_id', "ALTER TABLE users ADD COLUMN department_id INTEGER"),
                    ('team_id', "ALTER TABLE users ADD COLUMN team_id INTEGER"),
                    ('manager_id', "ALTER TABLE users ADD COLUMN manager_id INTEGER"),
                    ('designation', "ALTER TABLE users ADD COLUMN designation VARCHAR(100) DEFAULT 'Employee' NOT NULL"),
                    ('employee_id_code', "ALTER TABLE users ADD COLUMN employee_id_code VARCHAR(30)"),
                    ('phone', "ALTER TABLE users ADD COLUMN phone VARCHAR(30)"),
                ]
                for col_name, sql in user_migrations:
                    if col_name not in user_cols:
                        db.session.execute(text(sql))
                db.session.commit()
=======
            if 'users' in inspector.get_table_names():
                existing_user_cols = {c['name'] for c in inspector.get_columns('users')}
                if 'role' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'employee' NOT NULL"))
                if 'account_active' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN account_active BOOLEAN DEFAULT 1 NOT NULL"))
                if 'organization_id' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN organization_id INTEGER"))
                if 'department_id' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN department_id INTEGER"))
                if 'job_title' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN job_title VARCHAR(100)"))
                if 'phone' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(30)"))
                if 'reports_to_id' not in existing_user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN reports_to_id INTEGER"))

>>>>>>> Stashed changes
            if 'tasks' in inspector.get_table_names():
                existing_task_cols = {c['name'] for c in inspector.get_columns('tasks')}
                if 'team_id' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN team_id INTEGER"))
                if 'assigned_to_id' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN assigned_to_id INTEGER"))
                if 'start_date' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN start_date DATE"))
                if 'acceptance_criteria' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN acceptance_criteria TEXT"))
                if 'submission_notes' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN submission_notes TEXT"))
                if 'review_notes' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN review_notes TEXT"))
                if 'is_recurring' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN is_recurring BOOLEAN DEFAULT 0 NOT NULL"))
                if 'recurrence_interval' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN recurrence_interval VARCHAR(20)"))
                if 'updated_at' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN updated_at DATETIME"))
<<<<<<< Updated upstream
                if 'estimated_effort_hours' not in existing_task_cols:
                    db.session.execute(text("ALTER TABLE tasks ADD COLUMN estimated_effort_hours FLOAT"))
=======
>>>>>>> Stashed changes
>>>>>>> Stashed changes

            db.session.commit()
        except Exception:
            db.session.rollback()

    return app
