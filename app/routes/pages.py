from flask import Blueprint, render_template

pages_bp = Blueprint('pages', __name__)

@pages_bp.route('/')
def index():
    return render_template('index.html')

@pages_bp.route('/login')
def login():
    return render_template('login.html')

@pages_bp.route('/signup')
def signup():
    return render_template('signup.html')

@pages_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@pages_bp.route('/tasks')
def tasks():
    return render_template('tasks.html')
