from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config['SECRET_KEY'] = 'tasknest-dev-secret-key-change-in-prod'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasknest.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'pages.login'

    @login_manager.user_loader
    def load_user(user_id):
        # Stub loader until M2/M3 models and auth are merged
        return None

    # Register blueprints
    from app.routes.pages import pages_bp
    app.register_blueprint(pages_bp)

    return app
