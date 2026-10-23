from datetime import date, datetime, timedelta, timezone

from app import db
from app.models import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_TEAM_LEAD, Task, User


def _make_user(app, email, role=ROLE_EMPLOYEE):
    with app.app_context():
        user = User(
            username=email.split('@')[0],
            full_name=email.split('@')[0].title(),
            email=email,
            role=role,
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, email):
    response = client.post('/api/auth/login', json={
        'email': email,
        'password': 'password123',
    })
    assert response.status_code == 200


def test_employee_dashboard_counts_sections_and_daily_progress(app, client):
    employee_id = _make_user(app, 'my-day@example.com')
    today = date.today()

    with app.app_context():
        db.session.add_all([
            Task(title='Past due', user_id=employee_id, due_date=today - timedelta(days=1)),
            Task(title='Due today', user_id=employee_id, due_date=today),
            Task(title='High priority', user_id=employee_id, priority='high'),
            Task(title='Being worked', user_id=employee_id, status='in_progress'),
            Task(
                title='Completed today',
                user_id=employee_id,
                status='completed',
                due_date=today,
                completed_at=datetime.now(timezone.utc),
            ),
            Task(title='No due date', user_id=employee_id),
        ])
        db.session.commit()

    _login(client, 'my-day@example.com')
    response = client.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'My Open Tasks' in html
    assert '>5<' in html
    assert 'Due Today' in html
    assert 'Overdue Tasks' in html
    assert 'Completed This Week' in html
    assert 'Past due' in html
    assert 'Due today' in html
    assert 'High priority' in html
    assert 'Being worked' in html
    assert 'No due date' not in html
    assert '1<span>/2</span>' in html


def test_employee_dashboard_isolation_and_hidden_sidebar_items(app, client):
    employee_id = _make_user(app, 'first@example.com')
    other_id = _make_user(app, 'second@example.com')

    with app.app_context():
        db.session.add_all([
            Task(title='Visible task', user_id=employee_id, due_date=date.today()),
            Task(title='Private task', user_id=other_id, due_date=date.today()),
        ])
        db.session.commit()

    _login(client, 'first@example.com')
    html = client.get('/dashboard').get_data(as_text=True)
    assert 'Visible task' in html
    assert 'Private task' not in html
    assert '<span>Categories</span>' not in html
    assert '<span>Employees</span>' not in html


def test_employee_dashboard_empty_state(app, client):
    _make_user(app, 'empty@example.com')
    _login(client, 'empty@example.com')

    html = client.get('/dashboard').get_data(as_text=True)
    assert 'My Day' in html
    assert html.count('Nothing here right now.') == 4
    assert '0<span>/0</span>' in html


def test_dashboard_requires_authentication(client):
    response = client.get('/dashboard')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_admin_dashboard_keeps_existing_dashboard(app, client):
    _make_user(app, 'admin-dashboard@example.com', ROLE_ADMIN)
    _login(client, 'admin-dashboard@example.com')

    html = client.get('/dashboard').get_data(as_text=True)
    assert 'My Day' not in html
    assert 'Recent Tasks' in html
    assert '<span>Categories</span>' in html
    assert '<span>Employees</span>' in html


def test_team_lead_dashboard_keeps_existing_dashboard(app, client):
    _make_user(app, 'lead-dashboard@example.com', ROLE_TEAM_LEAD)
    _login(client, 'lead-dashboard@example.com')

    html = client.get('/dashboard').get_data(as_text=True)
    assert 'My Day' not in html
    assert 'Recent Tasks' in html
    assert '<span>Categories</span>' in html
    assert '<span>Employees</span>' in html
