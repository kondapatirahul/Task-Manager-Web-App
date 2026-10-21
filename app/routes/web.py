from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required

web_bp = Blueprint('web', __name__)

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

@web_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@web_bp.route('/tasks')
@login_required
def tasks():
    return render_template('tasks.html', active_page='tasks')

@web_bp.route('/categories')
@login_required
def categories():
    return render_template('categories.html', active_page='categories')

@web_bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', active_page='profile')
