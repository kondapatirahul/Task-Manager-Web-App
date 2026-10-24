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
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', f'sqlite:///{default_db_path}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        CSRF_ENABLED=True,
        UPLOAD_FOLDER=upload_dir,
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB max upload
    )

    if test_config:
        app.config.update(test_config)
    if os.getenv('FLASK_ENV') == 'production' and not os.getenv('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY must be configured in production.')
    app.config.setdefault('PROPAGATE_EXCEPTIONS', False)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'web.login_page'
    login_manager.login_message = 'Please log in to access this page.'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        if user and not user.account_active:
            return None
        return user

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
        if not request.path.startswith('/static/'):
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
        if not expected_token or not csrf_token or not secrets.compare_digest(csrf_token, expected_token):
            if request.path.startswith('/api/'):
                return {'ok': False, 'error': 'Invalid CSRF token (missing or incorrect).'}, 403
            return 'Invalid CSRF token (missing or incorrect).', 403

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

    # Register blueprints
    from app.routes.web import web_bp
    from app.routes.auth import auth_bp
    from app.routes.tasks import tasks_bp
    from app.routes.categories import categories_bp
    from app.routes.stats import stats_bp
    from app.routes.organization import org_bp
    from app.routes.employees import employees_bp
    from app.routes.attendance import attendance_bp
    from app.routes.meetings import meetings_bp
    from app.routes.notifications import notifications_bp
    from app.routes.discussions import discussions_bp
    from app.routes.reports import reports_bp
    from app.routes.teams import teams_bp
    from app.routes.departments import departments_bp
    from app.routes.organizations import organizations_bp
    from app.routes.leaves import leaves_bp
    from app.routes.audit_logs import audit_logs_bp
    from app.routes.portfolio import portfolio_bp
    from app.routes.saved_views import views_bp
    from app.routes.custom_fields import custom_fields_bp
    from app.routes.workflows import workflows_bp
    from app.routes.webhooks import webhooks_bp
    from app.routes.delivery import delivery_bp
    from app.routes.finance import finance_bp
    from app.routes.risks import risks_bp
    from app.routes.objectives import objectives_bp
    from app.routes.assets import assets_bp
    from app.routes.service_desk import service_desk_bp
    from app.routes.time_tracking import time_tracking_bp
    from app.routes.vendors import vendors_bp
    from app.routes.compliance import compliance_bp
    from app.routes.operations import operations_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(org_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(discussions_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(organizations_bp)
    app.register_blueprint(leaves_bp)
    app.register_blueprint(audit_logs_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(custom_fields_bp)
    app.register_blueprint(workflows_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(delivery_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(risks_bp)
    app.register_blueprint(objectives_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(service_desk_bp)
    app.register_blueprint(time_tracking_bp)
    app.register_blueprint(vendors_bp)
    app.register_blueprint(compliance_bp)
    app.register_blueprint(operations_bp)

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

            # 2. Migrate `team_members` table. Older local databases predate
            # the membership role column; add it in place without dropping data.
            if 'team_members' in table_names:
                member_cols = {c['name'] for c in inspector.get_columns('team_members')}
                if 'role' not in member_cols:
                    db.session.execute(text(
                        "ALTER TABLE team_members ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'"
                    ))
                    db.session.commit()

            # 3. Migrate `tasks` table
            if 'tasks' in table_names:
                task_cols = {c['name'] for c in inspector.get_columns('tasks')}
                task_migrations = [
                    ('creator_id', "ALTER TABLE tasks ADD COLUMN creator_id INTEGER"),
                    ('assignee_id', "ALTER TABLE tasks ADD COLUMN assignee_id INTEGER"),
                    ('team_id', "ALTER TABLE tasks ADD COLUMN team_id INTEGER"),
                    ('organization_id', "ALTER TABLE tasks ADD COLUMN organization_id INTEGER"),
                    ('start_date', "ALTER TABLE tasks ADD COLUMN start_date DATE"),
                    ('acceptance_criteria', "ALTER TABLE tasks ADD COLUMN acceptance_criteria TEXT"),
                    ('progress', "ALTER TABLE tasks ADD COLUMN progress INTEGER DEFAULT 0 NOT NULL"),
                    ('is_recurring', "ALTER TABLE tasks ADD COLUMN is_recurring BOOLEAN DEFAULT 0 NOT NULL"),
                    ('recurrence_interval', "ALTER TABLE tasks ADD COLUMN recurrence_interval VARCHAR(20)"),
                    ('next_recurrence_date', "ALTER TABLE tasks ADD COLUMN next_recurrence_date DATE"),
                    ('updated_at', "ALTER TABLE tasks ADD COLUMN updated_at DATETIME"),
                    ('is_personal', "ALTER TABLE tasks ADD COLUMN is_personal BOOLEAN DEFAULT 0"),
                    ('actual_budget', "ALTER TABLE tasks ADD COLUMN actual_budget NUMERIC(14, 2) NOT NULL DEFAULT 0.00"),
                    ('spent_budget', "ALTER TABLE tasks ADD COLUMN spent_budget NUMERIC(14, 2) NOT NULL DEFAULT 0.00"),
                ]
                for col_name, sql in task_migrations:
                    if col_name not in task_cols:
                        db.session.execute(text(sql))
                db.session.commit()

            # 4. Ensure Default Organization exists and backfill
            from app.models import Organization
            default_org = Organization.query.first()
            if not default_org:
                default_org = Organization(name='TaskNest Enterprise', slug='tasknest-enterprise')
                db.session.add(default_org)
                db.session.commit()

            # Backfill any null organization_id or assignee_id
            db.session.execute(text(f"UPDATE users SET organization_id = {default_org.id} WHERE organization_id IS NULL"))
            db.session.execute(text(f"UPDATE tasks SET organization_id = {default_org.id} WHERE organization_id IS NULL"))
            db.session.execute(text("UPDATE tasks SET assignee_id = user_id WHERE assignee_id IS NULL"))
            db.session.execute(text("UPDATE tasks SET creator_id = user_id WHERE creator_id IS NULL"))
            db.session.commit()

        except Exception:
            db.session.rollback()

    return app
