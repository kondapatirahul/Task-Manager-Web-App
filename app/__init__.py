import os
import secrets
from flask import Flask, session, request, redirect, url_for, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
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

    # Ensure instance and upload directories exist
    upload_dir = os.path.join(app.instance_path, 'uploads')
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        os.makedirs(upload_dir, exist_ok=True)
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
        MAX_ATTACHMENT_SIZE=10 * 1024 * 1024,
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
        # Never let authenticated application pages reappear from browser cache
        # after logout. Public homepage and public authentication pages remain cacheable.
        if request.path not in ('/', '/login', '/admin/login', '/lead/login', '/employee/login', '/signup', '/forgot-password') and not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        if 'csrf_token' in session:
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

        # Exempt file downloads or auth endpoints when session doesn't exist yet
        csrf_token = (
            request.headers.get('X-CSRFToken') or
            request.headers.get('X-CSRF-Token') or
            (request.form.get('csrf_token') if request.form else None)
        )

        expected_token = session.get('csrf_token')
        if expected_token and csrf_token:
            if not secrets.compare_digest(csrf_token, expected_token):
                if request.path.startswith('/api/'):
                    return {'ok': False, 'error': 'Invalid CSRF token'}, 403
                return 'Invalid CSRF token', 403

    # Error handlers
    from flask import render_template
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

    @app.errorhandler(500)
    def handle_500(e):
        if request.path.startswith('/api/'):
            return {'ok': False, 'error': 'Internal server error'}, 500
        return render_template('500.html'), 500

    # Register blueprints
    from app.routes.web import web_bp
    from app.routes.auth import auth_bp
    from app.routes.tasks import tasks_bp
    from app.routes.categories import categories_bp
    from app.routes.stats import stats_bp
    from app.routes.organizations import organizations_bp
    from app.routes.departments import departments_bp
    from app.routes.teams import teams_bp
    from app.routes.employees import employees_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(organizations_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(employees_bp)

    # CLI commands
    @app.cli.command('init-db')
    def init_db_command():
        """Initialize SQLite database tables."""
        with app.app_context():
            db.create_all()
        print("Database initialized successfully.")

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
    with app.app_context():
        db.create_all()
        from sqlalchemy import inspect as sa_inspect, text
        try:
            inspector = sa_inspect(db.engine)
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

            db.session.commit()
        except Exception:
            db.session.rollback()

    return app
