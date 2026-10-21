import re
from flask import Blueprint, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models import User, Category
from app.routes.utils import api_success, api_error


auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

@auth_bp.route('/signup', methods=['POST'])
@auth_bp.route('/register', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    full_name = (data.get('full_name') or data.get('username') or '').strip()
    username = (data.get('username') or '').strip()

    if not email or not EMAIL_REGEX.match(email):
        return api_error('A valid email address is required.', 400)

    if not password or len(password) < 6:
        return api_error('Password must be at least 6 characters long.', 400)

    if not username:
        # Fallback username from email prefix
        base_username = email.split('@')[0]
        username = re.sub(r'[^a-zA-Z0-9_]', '_', base_username)

    if User.query.filter_by(email=email).first():
        return api_error('Email is already registered.', 409)

    # Ensure unique username
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        username = f"{username}_{User.query.count() + 1}"

    user = User(
        username=username,
        full_name=full_name or username,
        email=email
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    # Create helpful starter categories for convenience
    starter_categories = ['Work', 'Personal', 'Projects']
    for cat_name in starter_categories:
        db.session.add(Category(name=cat_name, user_id=user.id))
    db.session.commit()

    login_user(user, remember=True)
    return api_success(user.to_dict(), message='User registered successfully', status_code=201)


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    remember = bool(data.get('remember', False))

    if not email or not password:
        return api_error('Email and password are required.', 400)

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return api_error('Invalid email or password.', 401)

    login_user(user, remember=remember)
    return api_success(user.to_dict(), message='Logged in successfully')

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return api_success(message='Logged out successfully')

@auth_bp.route('/me', methods=['GET'])
def get_me():
    if current_user.is_authenticated:
        return api_success(current_user.to_dict())
    return api_error('Not authenticated', 401)
