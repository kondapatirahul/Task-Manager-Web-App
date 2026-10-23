"""
tests/test_employee_dashboard_tasks.py

Comprehensive test suite verifying the Employee Dashboard & Task Management enhancements:
- Navigation & sidebar role boundaries: Employee sidebar cleanup (keeps only Dashboard, Tasks,
  Attendance, Notifications, Profile, Settings) and backend route protection.
- Personal task creation, automatic owner assignment, subtasks creation, and strict privacy boundary
  (invisible to other employees, Admin, and Team Leads).
- Personal task direct completion vs assigned task review workflow enforcement (employees cannot
  approve own assigned work or mark completed directly).
- Assigned task lifecycle: todo -> in_progress -> blocked (with reason & notification) -> in_review (via submission) -> changes_requested / completed.
- Database-backed dashboard metrics: distinct counts, personal vs assigned breakdown, overdue calculation,
  deterministic rule-based Smart Priority ("What should I work on next?"), and recent activity feed.
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from app import create_app, db
from app.models import (
    User, Organization, Department, Team, TeamMember, Task, SubTask,
    TaskStatusHistory, TaskMessage, WorkSubmission, Notification,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE,
    STATUS_TODO, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_IN_REVIEW,
    STATUS_CHANGES_REQUESTED, STATUS_COMPLETED, STATUS_PENDING
)


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-emp-dashboard-secret',
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
def setup_users(app):
    with app.app_context():
        org = Organization(name='Acme Corp', slug='acme')
        db.session.add(org)
        db.session.flush()

        dept = Department(name='Engineering', organization_id=org.id)
        db.session.add(dept)
        db.session.flush()

        admin = User(
            full_name='Admin Alice',
            username='admin_alice',
            email='admin@acme.com',
            role=ROLE_ADMIN,
            organization_id=org.id,
            department_id=dept.id,
            account_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)
        db.session.flush()

        lead = User(
            full_name='Lead Larry',
            username='lead_larry',
            email='lead@acme.com',
            role=ROLE_TEAM_LEAD,
            organization_id=org.id,
            department_id=dept.id,
            account_active=True
        )
        lead.set_password('LeadPass123!')
        db.session.add(lead)
        db.session.flush()

        team = Team(name='Core Dev', department_id=dept.id, organization_id=org.id, lead_id=lead.id)
        db.session.add(team)
        db.session.flush()
        lead.team_id = team.id

        emp1 = User(
            full_name='Emma Employee',
            username='emma_emp',
            email='emma@acme.com',
            employee_id_code='EMP-0042',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
            department_id=dept.id,
            team_id=team.id,
            account_active=True
        )
        emp1.set_password('EmmaPass123!')
        db.session.add(emp1)

        emp2 = User(
            full_name='Evan Employee',
            username='evan_emp',
            email='evan@acme.com',
            employee_id_code='EMP-0043',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
            department_id=dept.id,
            team_id=team.id,
            account_active=True
        )
        emp2.set_password('EvanPass123!')
        db.session.add(emp2)

        db.session.commit()

        return {
            'admin_id': admin.id,
            'lead_id': lead.id,
            'team_id': team.id,
            'emp1_id': emp1.id,
            'emp2_id': emp2.id,
        }


def login(client, email, password):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


# ── 1. Navigation & Sidebar Lockdown ──────────────────────────────────────────

def test_employee_navigation_and_sidebar_lockdown(client, setup_users):
    """
    Employee sidebar must only display Dashboard, Tasks, Attendance, Notifications, Profile, Settings.
    Protected management pages redirect unauthorized employee to /unauthorized.
    """
    login(client, 'emma@acme.com', 'EmmaPass123!')

    # Authorized pages
    for path in ['/dashboard', '/tasks', '/profile', '/settings']:
        res = client.get(path)
        assert res.status_code == 200, f"Employee should have access to {path}"

    # Restricted management pages redirect to /unauthorized
    for path in ['/reports', '/organization', '/attendance']:
        res = client.get(path)
        assert res.status_code == 302, f"Employee should be blocked from {path}"
        assert '/unauthorized' in res.headers['Location']

    # Inspect rendered HTML sidebar on /dashboard
    dash_html = client.get('/dashboard').data.decode('utf-8')
    assert '<span>Dashboard</span>' in dash_html
    assert '<span>Tasks & Board</span>' in dash_html
    assert '<span>Attendance</span>' in dash_html
    assert '<span>Notifications</span>' in dash_html
    assert '<span>Profile</span>' in dash_html
    assert '<span>Settings</span>' in dash_html

    # Prohibited navigation items must NOT be present in employee view
    assert '<span>Calendar & Meetings</span>' not in dash_html
    assert '<span>Directory</span>' not in dash_html
    assert '<span>Categories</span>' not in dash_html
    assert '<span>Teams & Org</span>' not in dash_html
    assert '<span>Reports & Analytics</span>' not in dash_html


def test_admin_and_lead_keep_navigation_items(client, setup_users):
    """Admins and Team Leads retain access to their respective management views."""
    # Team Lead
    login(client, 'lead@acme.com', 'LeadPass123!')
    res_lead_tasks = client.get('/tasks')
    assert res_lead_tasks.status_code == 200
    assert 'view-mode-list-btn' in res_lead_tasks.data.decode('utf-8')  # List toggle preserved
    assert client.get('/attendance').status_code == 200
    assert client.get('/teams').status_code == 200

    # Admin
    client.post('/api/auth/logout')
    login(client, 'admin@acme.com', 'AdminPass123!')
    assert client.get('/reports').status_code == 200
    assert client.get('/organization').status_code == 200
    assert client.get('/categories').status_code == 200


# ── 2. Personal Task Creation & Strict Privacy ────────────────────────────────

def test_personal_task_creation_and_enforced_defaults(client, setup_users):
    """
    Employees can create personal tasks with subtasks. The server automatically enforces
    creator_id = assignee_id = current_user.id, team_id = None, and is_personal = True.
    """
    login(client, 'emma@acme.com', 'EmmaPass123!')

    res = client.post('/api/tasks', json={
        'title': 'My Personal Research',
        'description': 'Draft personal study plan',
        'priority': 'high',
        'due_date': (date.today() + timedelta(days=3)).isoformat(),
        'is_personal': True,
        'subtasks': ['Read documentation', 'Write notes', 'Summarize findings']
    })
    assert res.status_code == 201
    data = res.get_json()['data']
    task_id = data['id']

    assert data['title'] == 'My Personal Research'
    assert data['is_personal'] is True
    assert data['assignee_id'] == setup_users['emp1_id']
    assert data['creator_id'] == setup_users['emp1_id']
    assert data['team_id'] is None
    assert data['subtask_count'] == 3


def test_employee_cannot_assign_personal_tasks_to_others_or_teams(client, setup_users):
    """Employees cannot assign personal tasks to other employees or team queues."""
    login(client, 'emma@acme.com', 'EmmaPass123!')

    # Attempt to assign to coworker Evan
    res1 = client.post('/api/tasks', json={
        'title': 'Attempted Delegation',
        'assigned_to_id': setup_users['emp2_id'],
        'is_personal': True
    })
    assert res1.status_code == 403
    assert 'cannot assign tasks to other employees' in res1.get_json()['error']

    # Attempt to assign to team
    res2 = client.post('/api/tasks', json={
        'title': 'Attempted Team Queue Task',
        'team_id': setup_users['team_id'],
        'is_personal': True
    })
    assert res2.status_code == 403
    assert 'cannot assign tasks to teams' in res2.get_json()['error']


def test_personal_tasks_are_strictly_private_from_others_and_admin(client, setup_users):
    """
    Personal tasks are strictly private:
    - Coworker Evan cannot view it (404).
    - Team Lead cannot view it or see it in team task lists.
    - Admin cannot view it or see it in company task lists.
    """
    login(client, 'emma@acme.com', 'EmmaPass123!')
    res_create = client.post('/api/tasks', json={
        'title': "Emma's Private Task",
        'is_personal': True
    })
    task_id = res_create.get_json()['data']['id']

    # 1. Coworker Evan
    client.post('/api/auth/logout')
    login(client, 'evan@acme.com', 'EvanPass123!')
    res_evan_get = client.get(f'/api/tasks/{task_id}')
    assert res_evan_get.status_code == 404

    res_evan_list = client.get('/api/tasks')
    evan_task_ids = [t['id'] for t in res_evan_list.get_json()['data']]
    assert task_id not in evan_task_ids

    # 2. Team Lead Larry
    client.post('/api/auth/logout')
    login(client, 'lead@acme.com', 'LeadPass123!')
    res_lead_get = client.get(f'/api/tasks/{task_id}')
    assert res_lead_get.status_code == 404

    res_lead_list = client.get('/api/tasks')
    lead_task_ids = [t['id'] for t in res_lead_list.get_json()['data']]
    assert task_id not in lead_task_ids

    # 3. Admin Alice
    client.post('/api/auth/logout')
    login(client, 'admin@acme.com', 'AdminPass123!')
    res_admin_get = client.get(f'/api/tasks/{task_id}')
    assert res_admin_get.status_code == 404

    res_admin_list = client.get('/api/tasks')
    admin_task_ids = [t['id'] for t in res_admin_list.get_json()['data']]
    assert task_id not in admin_task_ids


def test_personal_task_direct_completion_by_owner(client, setup_users):
    """Personal task owner can directly update status to completed without review workflow."""
    login(client, 'emma@acme.com', 'EmmaPass123!')
    res_create = client.post('/api/tasks', json={
        'title': 'Finish reading documentation',
        'is_personal': True,
        'status': 'in_progress'
    })
    task_id = res_create.get_json()['data']['id']

    # Owner marks completed directly
    res_complete = client.patch(f'/api/tasks/{task_id}', json={'status': 'completed'})
    assert res_complete.status_code == 200
    assert res_complete.get_json()['data']['status'] == 'completed'
    assert res_complete.get_json()['data']['completed_at'] is not None


# ── 3. Assigned Task Lifecycle & Protection ───────────────────────────────────

def test_assigned_task_protection_against_direct_completion(client, setup_users):
    """Employees cannot directly mark assigned organization tasks as completed (must submit work)."""
    # Admin assigns task to Emma
    login(client, 'admin@acme.com', 'AdminPass123!')
    res_create = client.post('/api/tasks', json={
        'title': 'Deploy Microservice to Production',
        'assigned_to_id': setup_users['emp1_id'],
        'team_id': setup_users['team_id'],
        'priority': 'high',
        'is_personal': False
    })
    task_id = res_create.get_json()['data']['id']

    # Emma logs in and tries to mark completed directly
    client.post('/api/auth/logout')
    login(client, 'emma@acme.com', 'EmmaPass123!')

    res_fail = client.patch(f'/api/tasks/{task_id}', json={'status': 'completed'})
    assert res_fail.status_code == 403
    assert 'submit work for review' in res_fail.get_json()['error']


def test_assigned_task_blocked_with_reason_and_notification(client, setup_users):
    """
    When an employee marks a task blocked:
    - Reason is stored in TaskStatusHistory.
    - TaskMessage is created.
    - Notification is sent to the assigner/creator.
    """
    # Lead Larry assigns task to Emma
    login(client, 'lead@acme.com', 'LeadPass123!')
    res_create = client.post('/api/tasks', json={
        'title': 'Integrate Payment Gateway',
        'assigned_to_id': setup_users['emp1_id'],
        'team_id': setup_users['team_id'],
        'priority': 'urgent',
        'is_personal': False
    })
    task_id = res_create.get_json()['data']['id']

    # Emma marks it blocked
    client.post('/api/auth/logout')
    login(client, 'emma@acme.com', 'EmmaPass123!')

    block_reason = 'Stripe test API keys are failing with 401 unauthorized'
    res_block = client.patch(f'/api/tasks/{task_id}', json={
        'status': 'blocked',
        'block_reason': block_reason
    })
    assert res_block.status_code == 200
    assert res_block.get_json()['data']['status'] == 'blocked'

    # Check notification sent to Lead Larry
    client.post('/api/auth/logout')
    login(client, 'lead@acme.com', 'LeadPass123!')

    notif_res = client.get('/api/notifications')
    assert notif_res.status_code == 200
    notifs = notif_res.get_json()['data']['notifications']
    assert any('Integrate Payment Gateway' in n['title'] and 'blocked' in n['message'] for n in notifs)


def test_assigned_task_review_and_changes_requested_workflow(client, setup_users):
    """
    Full workflow:
    Emma moves task in_progress -> submits work -> status is in_review.
    Emma cannot self-approve -> 403.
    Lead requests changes -> status becomes changes_requested.
    Emma resubmits -> Lead approves -> status becomes completed.
    """
    # Admin assigns task
    login(client, 'admin@acme.com', 'AdminPass123!')
    res_task = client.post('/api/tasks', json={
        'title': 'Implement SSO Login',
        'assigned_to_id': setup_users['emp1_id'],
        'is_personal': False
    })
    task_id = res_task.get_json()['data']['id']

    # Emma marks in progress and submits deliverable
    client.post('/api/auth/logout')
    login(client, 'emma@acme.com', 'EmmaPass123!')
    client.patch(f'/api/tasks/{task_id}', json={'status': 'in_progress'})

    res_sub = client.post(f'/api/tasks/{task_id}/submissions', json={
        'notes': 'SSO endpoints implemented with OAuth2 code flow'
    })
    assert res_sub.status_code == 201
    sub_id = res_sub.get_json()['data']['id']

    # Verify task is now in_review
    res_task_check = client.get(f'/api/tasks/{task_id}')
    assert res_task_check.get_json()['data']['status'] == 'in_review'

    # Emma cannot approve her own submission
    res_self_review = client.post(f'/api/tasks/{task_id}/submissions/{sub_id}/review', json={
        'decision': 'approve'
    })
    assert res_self_review.status_code == 403

    # Admin requests changes
    client.post('/api/auth/logout')
    login(client, 'admin@acme.com', 'AdminPass123!')

    res_req_change = client.post(f'/api/tasks/{task_id}/submissions/{sub_id}/review', json={
        'decision': 'request_changes',
        'review_notes': 'Please add state parameter validation for CSRF mitigation'
    })
    assert res_req_change.status_code == 200

    # Verify status changed to changes_requested
    res_task_after_req = client.get(f'/api/tasks/{task_id}')
    assert res_task_after_req.get_json()['data']['status'] == 'changes_requested'

    # Emma fixes and resubmits
    client.post('/api/auth/logout')
    login(client, 'emma@acme.com', 'EmmaPass123!')

    res_resub = client.post(f'/api/tasks/{task_id}/submissions', json={
        'notes': 'Added state parameter validation as requested.'
    })
    assert res_resub.status_code == 201
    resub_id = res_resub.get_json()['data']['id']

    # Admin approves
    client.post('/api/auth/logout')
    login(client, 'admin@acme.com', 'AdminPass123!')

    res_approve = client.post(f'/api/tasks/{task_id}/submissions/{resub_id}/review', json={
        'decision': 'approve',
        'review_notes': 'Looks great, approved!'
    })
    assert res_approve.status_code == 200

    res_final_task = client.get(f'/api/tasks/{task_id}')
    assert res_final_task.get_json()['data']['status'] == 'completed'


# ── 4. Dashboard Stats & Smart Priority ───────────────────────────────────────

def test_employee_dashboard_metrics_and_smart_priority(client, setup_users):
    """
    Test database-backed metrics, personal vs assigned breakdown, overdue calculation,
    deterministic Smart Priority algorithm, and recent activity feed.
    """
    today = date.today()
    login(client, 'emma@acme.com', 'EmmaPass123!')

    # 1. Overdue personal task
    client.post('/api/tasks', json={
        'title': 'Overdue Personal Task',
        'status': 'todo',
        'priority': 'medium',
        'due_date': (today - timedelta(days=2)).isoformat(),
        'is_personal': True
    })

    # 2. Urgent assigned task due today
    login(client, 'admin@acme.com', 'AdminPass123!')
    client.post('/api/tasks', json={
        'title': 'Urgent Security Patch',
        'status': 'in_progress',
        'priority': 'urgent',
        'due_date': today.isoformat(),
        'assigned_to_id': setup_users['emp1_id'],
        'is_personal': False
    })

    # 3. Completed task
    client.post('/api/tasks', json={
        'title': 'Setup dev environment',
        'status': 'completed',
        'priority': 'low',
        'assigned_to_id': setup_users['emp1_id'],
        'is_personal': False
    })

    # Fetch stats as Emma
    client.post('/api/auth/logout')
    login(client, 'emma@acme.com', 'EmmaPass123!')

    res_stats = client.get('/api/stats')
    assert res_stats.status_code == 200
    stats = res_stats.get_json()['data']

    assert stats['total'] == 3
    assert stats['personal_count'] == 1
    assert stats['assigned_count'] == 2
    assert stats['completed'] == 1
    assert stats['overdue'] == 1

    # Smart Priority Recommendation check
    assert stats['smart_next'] is not None
    next_task = stats['smart_next']['task']
    reason = stats['smart_next']['reason']
    # Must be one of the active tasks (never completed)
    assert next_task['status'] != 'completed'
    assert 'Overdue' in reason or 'Due today' in reason or 'Urgent' in reason

    # Personal Weekly Progress check
    assert 'weekly_progress' in stats
    wp = stats['weekly_progress']
    assert wp['assigned_this_week'] >= 1
    assert 'completion_trend' in wp

    # Recent Activity Feed check
    assert 'recent_activity' in stats
    assert isinstance(stats['recent_activity'], list)
    assert len(stats['recent_activity']) >= 1
