from flask import Blueprint, render_template, session, redirect, url_for

pages_bp = Blueprint('pages', __name__)

@pages_bp.route('/')
def index():
    return render_template('index.html')

@pages_bp.route('/login')
def login():
    if session.get('user_id'):
        return redirect('/dashboard')
    return render_template('login.html')

@pages_bp.route('/signup')
def signup():
    if session.get('user_id'):
        return redirect('/dashboard')
    return render_template('signup.html')

@pages_bp.route('/dashboard')
def dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/login')
    from app.models import User
    user = User.query.get(user_id)
    return render_template('dashboard.html', user=user)

@pages_bp.route('/tasks')
def tasks():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/login')
    from app.models import User
    user = User.query.get(user_id)
    return render_template('tasks.html', user=user)
