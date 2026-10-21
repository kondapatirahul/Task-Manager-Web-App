from functools import wraps
import re

from flask import Blueprint, g, request, jsonify, session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.models import User


auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def get_current_user():
    user_id = session.get('user_id')

    if not isinstance(user_id, int) or user_id <= 0:
        return None

    user = db.session.get(User, user_id)

    if user is None:
        session.pop('user_id', None)

    return user


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = get_current_user()

        if user is None:
            return jsonify({'error': 'Unauthorized'}), 401

        g.current_user = user
        return view(*args, **kwargs)

    return wrapped_view


@auth_bp.route('/register', methods=['POST'])
def register():
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 415
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required'}), 400

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all(
        isinstance(value, str)
        for value in (username, email, password)
    ):
        return jsonify({
            'error': 'Username, email, and password are required'
        }), 400

    username = username.strip()
    email = email.strip().lower()

    if not username or len(username) > 80:
        return jsonify({
            'error': 'Username must be between 1 and 80 characters'
        }), 400

    if (
        len(email) > 120
        or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email)
    ):
        return jsonify({
            'error': 'A valid email address is required'
        }), 400

    if not password or len(password) > 128:
        return jsonify({
            'error': 'Password must be between 1 and 128 characters'
        }), 400

    if (
        User.query.filter_by(email=email).first()
        or User.query.filter_by(username=username).first()
    ):
        return jsonify({
            'error': 'Username or email already registered'
        }), 409

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password)
    )

    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'error': 'Username or email already registered'
        }), 409

    return jsonify({'message': 'User created'}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 415
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required'}), 400

    email = data.get('email')
    password = data.get('password')

    if (
        not isinstance(email, str)
        or not isinstance(password, str)
        or not email.strip()
        or not password
        or len(password) > 128
    ):
        return jsonify({
            'error': 'Email and password are required'
        }), 400

    user = User.query.filter_by(
        email=email.strip().lower()
    ).first()

    if not user or not check_password_hash(
        user.password_hash, password
    ):
        return jsonify({'error': 'Invalid credentials'}), 401

    session.clear()
    session['user_id'] = user.id

    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user.id,
            'username': user.username
        }
    }), 200


@auth_bp.route('/me', methods=['GET'])
@login_required
def current_user():
    user = g.current_user

    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email
    }), 200


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()

    return jsonify({'message': 'Logged out'}), 200