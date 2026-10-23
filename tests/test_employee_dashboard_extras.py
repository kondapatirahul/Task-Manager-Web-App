"""
Unit and integration tests for TaskNest Employee Dashboard Safe Feature Expansion:
- Validates that the 7 employee features are rendered exclusively for Employees.
- Verifies that Admin and Team Lead dashboards remain isolated and unaffected.
- Checks unauthenticated protection and endpoint behavior.
"""
import pytest
from app import create_app, db
from app.models import (
    User, Organization, Department, Team, Task,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE
)


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-emp-dashboard',
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'WTF_CSRF_ENABLED': False,
        'CSRF_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def setup_roles(app):
    """Create test users for Super Admin, Admin, Team Lead, and Employee roles."""
    with app.app_context():
        org = Organization(name='Acme Corp', slug='acme-corp')
        db.session.add(org)
        db.session.flush()

        dept = Department(name='Engineering', organization_id=org.id)
        db.session.add(dept)
        db.session.flush()

        admin = User(
            full_name='HR Admin',
            username='hradmin',
            email='admin@example.com',
            role=ROLE_ADMIN,
            organization_id=org.id,
            account_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        lead = User(
            full_name='Tech Lead',
            username='techlead',
            email='lead@example.com',
            role=ROLE_TEAM_LEAD,
            organization_id=org.id,
            department_id=dept.id,
            account_active=True
        )
        lead.set_password('LeadPass123!')
        db.session.add(lead)
        db.session.flush()

        team = Team(
            name='Core Team',
            department_id=dept.id,
            organization_id=org.id,
            lead_id=lead.id
        )
        db.session.add(team)
        db.session.flush()
        lead.team_id = team.id

        employee = User(
            full_name='Alice Employee',
            username='alice',
            email='alice@example.com',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
            department_id=dept.id,
            team_id=team.id,
            manager_id=lead.id,
            account_active=True
        )
        employee.set_password('EmpPass123!')
        db.session.add(employee)
        db.session.flush()

        # Add a task for the employee
        task = Task(
            title='Review quarterly goals',
            description='Plan targets for next quarter',
            priority='high',
            status='in_progress',
            user_id=employee.id,
            assignee_id=employee.id,
            creator_id=lead.id,
            organization_id=org.id
        )
        db.session.add(task)
        db.session.commit()


def login(client, email, password):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


def test_unauthenticated_dashboard_redirects(client):
    """Unauthenticated users must be redirected to the login page."""
    res = client.get('/dashboard')
    assert res.status_code == 302
    assert '/login' in res.headers['Location']

    res2 = client.get('/employee/dashboard')
    assert res2.status_code == 302
    assert '/login' in res2.headers['Location']


def test_employee_dashboard_renders_all_features(client, setup_roles):
    """Verify that an authenticated employee sees all 7 productivity features and assets."""
    login(client, 'alice@example.com', 'EmpPass123!')

    res = client.get('/dashboard')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # 1. Scoped CSS and JS included for Employee
    assert 'css/employee_dashboard.css' in html
    assert 'js/employee_dashboard.js' in html
    assert 'class="employee-dashboard-wrapper"' in html

    # 2. Feature 6: Quick Actions Bar
    assert 'emp-quick-actions-bar' in html
    assert 'id="emp-action-new-task"' in html
    assert 'id="emp-action-board"' in html
    assert 'id="emp-action-calendar"' in html
    assert 'id="emp-action-notifications-btn"' in html
    assert 'id="emp-action-timesheets"' in html

    # 3. Feature 1 & 3: My Day Planner & Better Task Organization
    assert 'id="emp-my-day-section"' in html
    assert 'My Day Planner' in html
    assert 'id="emp-today-date-badge"' in html
    assert 'id="emp-daily-progress-box"' in html
    assert 'id="emp-progress-fill"' in html
    assert 'emp-filter-tabs' in html
    assert 'id="emp-task-inline-search"' in html
    assert 'id="emp-priority-select-filter"' in html
    assert 'id="emp-my-day-task-list"' in html

    # 4. Feature 2: Personal Productivity Dashboard
    assert 'id="emp-productivity-section"' in html
    assert 'Personal Productivity &amp; Milestones' in html or 'Personal Productivity & Milestones' in html
    assert 'id="emp-donut-stroke"' in html
    assert 'id="emp-completion-rate-text"' in html
    assert 'id="emp-stat-completed-week"' in html
    assert 'id="emp-stat-remaining"' in html
    assert 'id="emp-stat-shift-time"' in html
    assert 'id="emp-milestones-container"' in html
    assert 'id="emp-activity-stream-list"' in html

    # 5. Feature 5: Daily Schedule
    assert 'id="emp-schedule-section"' in html
    assert 'Daily Schedule' in html
    assert 'id="emp-daily-timeline"' in html

    # 6. Feature 4: Employee Collaboration Center
    assert 'id="emp-collab-section"' in html
    assert 'Collaboration Center' in html
    assert 'id="emp-collab-mark-read"' in html
    assert 'id="emp-collab-items-container"' in html

    # 7. Backward compatibility: Standard metrics grid preserved
    assert 'id="dashboard-metrics"' in html
    assert 'id="stat-total"' in html
    assert 'id="stat-pending"' in html
    assert 'id="stat-completed"' in html
    assert 'id="stat-overdue"' in html


def test_admin_dashboard_strictly_isolated(client, setup_roles):
    """Verify Admin Dashboard is completely unchanged and does not contain employee-specific extras."""
    login(client, 'admin@example.com', 'AdminPass123!')

    res = client.get('/dashboard')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Must contain Admin-specific content
    assert 'Admin Dashboard' in html or 'admin-metrics' in html or 'System Overview' in html

    # Must NOT contain Employee Dashboard extras
    assert 'css/employee_dashboard.css' not in html
    assert 'js/employee_dashboard.js' not in html
    assert 'employee-dashboard-wrapper' not in html
    assert 'emp-quick-actions-bar' not in html
    assert 'id="emp-my-day-section"' not in html
    assert 'id="emp-productivity-section"' not in html
    assert 'id="emp-schedule-section"' not in html
    assert 'id="emp-collab-section"' not in html


def test_team_lead_dashboard_strictly_isolated(client, setup_roles):
    """Verify Team Lead Dashboard is completely unchanged and does not contain employee-specific extras."""
    login(client, 'lead@example.com', 'LeadPass123!')

    res = client.get('/dashboard')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Must contain Team Lead specific content
    assert 'Team Lead Dashboard' in html or 'lead-metrics' in html

    # Must NOT contain Employee Dashboard extras
    assert 'css/employee_dashboard.css' not in html
    assert 'js/employee_dashboard.js' not in html
    assert 'employee-dashboard-wrapper' not in html
    assert 'emp-quick-actions-bar' not in html
    assert 'id="emp-my-day-section"' not in html
    assert 'id="emp-productivity-section"' not in html
    assert 'id="emp-schedule-section"' not in html
    assert 'id="emp-collab-section"' not in html


def test_employee_dashboard_apis_working(client, setup_roles):
    """Verify backend endpoints powering the employee dashboard respond with valid payloads."""
    login(client, 'alice@example.com', 'EmpPass123!')

    # 1. Tasks API
    res_tasks = client.get('/api/tasks')
    assert res_tasks.status_code == 200
    data_tasks = res_tasks.get_json()
    assert data_tasks['ok'] is True

    # 2. Stats API
    res_stats = client.get('/api/stats')
    assert res_stats.status_code == 200
    data_stats = res_stats.get_json()
    assert data_stats['ok'] is True
    assert 'total' in data_stats['data']
    assert 'pending' in data_stats['data']

    # 3. Attendance Today API
    res_att = client.get('/api/attendance/today')
    assert res_att.status_code == 200
    data_att = res_att.get_json()
    assert data_att['ok'] is True
    assert 'is_checked_in' in data_att['data']

    # 4. Meetings API
    res_meet = client.get('/api/meetings?upcoming=1')
    assert res_meet.status_code == 200
    data_meet = res_meet.get_json()
    assert data_meet['ok'] is True

    # 5. Notifications API
    res_notif = client.get('/api/notifications')
    assert res_notif.status_code == 200
    data_notif = res_notif.get_json()
    assert data_notif['ok'] is True

    # 6. Mark All Read
    res_read = client.post('/api/notifications/mark-all-read')
    assert res_read.status_code == 200
    data_read = res_read.get_json()
    assert data_read['ok'] is True
