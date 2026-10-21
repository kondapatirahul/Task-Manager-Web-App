from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.exceptions import HTTPException

db = SQLAlchemy()

def create_app(test_config=None):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or os.urandom(32)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///tasks.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config.update(test_config or {})

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if request.path != '/api' and not request.path.startswith('/api/'):
            return error.get_response()

        response = error.get_response()
        response.set_data(jsonify({'error': error.name}).get_data())
        response.content_type = 'application/json'
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.error(
            'Unhandled exception while processing request',
            exc_info=(type(error), error, error.__traceback__),
        )
        return jsonify({'error': 'Internal server error'}), 500

    db.init_app(app)

    from app.routes.auth import auth_bp
    from app.routes.tasks import tasks_bp
    from app.routes.categories import categories_bp
    from app.routes.stats import stats_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(stats_bp)

    with app.app_context():
        db.create_all()

    return app
