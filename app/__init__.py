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

    # Ensure instance directory exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    default_db_path = os.path.join(app.instance_path, 'tasks.db')
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'tasknest-dev-secret-key-change-in-prod'),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', f'sqlite:///{default_db_path}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        CSRF_ENABLED=True,
    )

    if test_config:
        app.config.update(test_config)

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
        if expected_token and csrf_token:
            if not secrets.compare_digest(csrf_token, expected_token):
                if request.path.startswith('/api/'):
                    return {'ok': False, 'error': 'Invalid CSRF token'}, 403
                return 'Invalid CSRF token', 403

    # Register blueprints
    from app.routes.web import web_bp
    from app.routes.auth import auth_bp
    from app.routes.tasks import tasks_bp
    from app.routes.categories import categories_bp
    from app.routes.stats import stats_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(stats_bp)

    # CLI command to initialize database
    @app.cli.command('init-db')
    def init_db_command():
        """Initialize SQLite database tables."""
        with app.app_context():
            db.create_all()
        print("Database initialized successfully.")

    # Create tables automatically on start if they don't exist
    with app.app_context():
        db.create_all()
        # Automatically migrate existing SQLite database tables if missing new columns
        from sqlalchemy import inspect as sa_inspect, text
        try:
            inspector = sa_inspect(db.engine)
            if 'users' in inspector.get_table_names():
                existing_cols = {c['name'] for c in inspector.get_columns('users')}
                if 'role' not in existing_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'employee' NOT NULL"))
                if 'account_active' not in existing_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN account_active BOOLEAN DEFAULT 1 NOT NULL"))
                db.session.commit()
        except Exception:
            db.session.rollback()

    return app
