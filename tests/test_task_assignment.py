from datetime import date, timedelta
import pytest
from app import db
from app.models import (
    User,
    Team,
    team_members,
    Category,
    Task,
    TaskStatusHistory,
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_TEAM_LEAD,
    ROLE_EMPLOYEE,
    STATUS_TODO,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_IN_REVIEW,
    STATUS_COMPLETED,
    STATUS_CHANGES_REQUESTED,
)


@pytest.fixture
def org_and_team_fixture(app):
    """
    Creates:
    - super_admin
    - team_lead_1 (leads Team Alpha)
    - team_lead_2 (leads Team Beta)
    - employee_1 (member of Team Alpha)
    - employee_2 (member of Team Beta)
    """
    with app.app_context():
        admin = User(username='admin', full_name='Admin User', email='admin@test.com', role=ROLE_ADMIN)
        admin.set_password('AdminPass123!')

        lead1 = User(username='lead1', full_name='Lead One', email='lead1@test.com', role=ROLE_TEAM_LEAD)
        lead1.set_password('Lead1Pass123!')

        lead2 = User(username='lead2', full_name='Lead Two', email='lead2@test.com', role=ROLE_TEAM_LEAD)
        lead2.set_password('Lead2Pass123!')

        emp1 = User(username='emp1', full_name='Employee One', email='emp1@test.com', role=ROLE_EMPLOYEE)
        emp1.set_password('Emp1Pass123!')

        emp2 = User(username='emp2', full_name='Employee Two', email='emp2@test.com', role=ROLE_EMPLOYEE)
        emp2.set_password('Emp2Pass123!')

        db.session.add_all([admin, lead1, lead2, emp1, emp2])
        db.session.commit()

        # Create Team Alpha led by lead1, containing emp1
        team_alpha = Team(name='Team Alpha', lead_id=lead1.id)
        # Create Team Beta led by lead2, containing emp2
        team_beta = Team(name='Team Beta', lead_id=lead2.id)

        db.session.add_all([team_alpha, team_beta])
        db.session.commit()

        # Add memberships
        db.session.execute(team_members.insert().values(team_id=team_alpha.id, user_id=lead1.id, role='lead'))
        db.session.execute(team_members.insert().values(team_id=team_alpha.id, user_id=emp1.id, role='member'))

        db.session.execute(team_members.insert().values(team_id=team_beta.id, user_id=lead2.id, role='lead'))
        db.session.execute(team_members.insert().values(team_id=team_beta.id, user_id=emp2.id, role='member'))

        db.session.commit()

        return {
            'admin_id': admin.id,
            'lead1_id': lead1.id,
            'lead2_id': lead2.id,
            'emp1_id': emp1.id,
            'emp2_id': emp2.id,
            'team_alpha_id': team_alpha.id,
            'team_beta_id': team_beta.id,
        }


def login_as(client, email, password):
    client.post('/api/auth/logout')
    res = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert res.status_code == 200, f"Login failed for {email}: {res.get_json()}"


# ── Test 1: Task Creation and Assignment within Permitted Scope ──────────────────

def test_team_lead_can_create_and_assign_task_to_team_member(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')

    res = client.post('/api/tasks', json={
        'title': 'Implement API endpoint',
        'description': 'Build the backend endpoint with validation',
        'priority': 'high',
        'status': 'todo',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
        'acceptance_criteria': 'All unit tests pass and response matches contract',
        'start_date': date.today().isoformat(),
        'due_date': (date.today() + timedelta(days=5)).isoformat(),
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data['ok'] is True
    task_data = data['data']
    assert task_data['title'] == 'Implement API endpoint'
    assert task_data['team_id'] == fixture['team_alpha_id']
    assert task_data['assigned_to_id'] == fixture['emp1_id']
    assert task_data['assigned_to_name'] == 'Employee One'
    assert task_data['acceptance_criteria'] == 'All unit tests pass and response matches contract'
    assert task_data['status'] == 'todo'


# ── Test 2: Team Boundaries (Lead cannot assign outside their team) ─────────────

def test_team_lead_cannot_assign_task_to_employee_outside_team(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')

    # Lead 1 tries to assign to Employee 2 (who is in Team Beta, not Team Alpha)
    res = client.post('/api/tasks', json={
        'title': 'Cross-team task',
        'team_id': fixture['team_beta_id'],
        'assigned_to_id': fixture['emp2_id'],
    })
    assert res.status_code == 403
    assert res.get_json()['ok'] is False
    assert 'authorized scope' in res.get_json()['error']


# ── Test 3: Employee Security & Ownership (Cannot assign to others) ─────────────

def test_employee_cannot_assign_task_to_another_employee(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')

    # Employee 1 tries to assign a task to Employee 2
    res = client.post('/api/tasks', json={
        'title': 'Unauthorized assignment by employee',
        'assigned_to_id': fixture['emp2_id'],
    })
    assert res.status_code == 403
    assert res.get_json()['ok'] is False
    assert 'Employees cannot assign tasks to other employees' in res.get_json()['error']


def test_employee_cannot_assign_task_to_team(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')

    res = client.post('/api/tasks', json={
        'title': 'Unauthorized team assignment',
        'team_id': fixture['team_alpha_id'],
    })
    assert res.status_code == 403
    assert res.get_json()['ok'] is False
    assert 'Employees cannot assign tasks to teams' in res.get_json()['error']


# ── Test 4: Employee Views Assigned Tasks ───────────────────────────────────────

def test_employee_can_view_assigned_tasks(client, org_and_team_fixture):
    fixture = org_and_team_fixture

    # Lead 1 creates and assigns task to Employee 1
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res_create = client.post('/api/tasks', json={
        'title': 'Alpha Assigned Task',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
        'priority': 'medium',
    })
    task_id = res_create.get_json()['data']['id']

    # Log in as Employee 1
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')

    # Employee 1 lists tasks
    res_list = client.get('/api/tasks')
    assert res_list.status_code == 200
    tasks = res_list.get_json()['data']
    assert any(t['id'] == task_id for t in tasks)

    # Employee 1 gets single task
    res_single = client.get(f'/api/tasks/{task_id}')
    assert res_single.status_code == 200
    assert res_single.get_json()['data']['title'] == 'Alpha Assigned Task'


# ── Test 5: Employee Updates Permitted Fields and Status Transitions ─────────────

def test_employee_can_transition_status_to_in_progress_and_blocked(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res = client.post('/api/tasks', json={
        'title': 'Development Task',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
        'status': 'todo',
    })
    task_id = res.get_json()['data']['id']

    # Employee 1 logs in and moves task to in_progress
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    res_prog = client.put(f'/api/tasks/{task_id}', json={'status': 'in_progress'})
    assert res_prog.status_code == 200
    assert res_prog.get_json()['data']['status'] == 'in_progress'

    # Employee 1 encounters a blocker and moves task to blocked
    res_block = client.put(f'/api/tasks/{task_id}', json={'status': 'blocked'})
    assert res_block.status_code == 200
    assert res_block.get_json()['data']['status'] == 'blocked'

    # Employee 1 unblocks and moves back to in_progress
    res_unblock = client.put(f'/api/tasks/{task_id}', json={'status': 'in_progress'})
    assert res_unblock.status_code == 200
    assert res_unblock.get_json()['data']['status'] == 'in_progress'


def test_employee_cannot_mark_assigned_task_completed_directly(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res = client.post('/api/tasks', json={
        'title': 'Company task for review',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
        'status': 'in_progress',
    })
    task_id = res.get_json()['data']['id']

    # Employee 1 tries to mark completed directly via PUT
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    res_put = client.put(f'/api/tasks/{task_id}', json={'status': 'completed'})
    assert res_put.status_code == 403
    assert 'submit work for review' in res_put.get_json()['error']

    # Employee 1 tries to mark completed directly via PATCH /complete
    res_patch = client.patch(f'/api/tasks/{task_id}/complete')
    assert res_patch.status_code == 403
    assert 'submit work for review' in res_patch.get_json()['error']


def test_employee_cannot_modify_protected_fields_on_assigned_task(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res = client.post('/api/tasks', json={
        'title': 'Original Protected Title',
        'priority': 'high',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
    })
    task_id = res.get_json()['data']['id']

    # Employee 1 tries to change title and priority
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    res_edit = client.put(f'/api/tasks/{task_id}', json={
        'title': 'Employee Altered Title',
        'priority': 'low',
    })
    assert res_edit.status_code == 403
    assert 'Employees cannot modify protected task details' in res_edit.get_json()['error']


# ── Test 6: Submission and Review Workflow ──────────────────────────────────────

def test_submission_and_lead_approval_workflow(client, org_and_team_fixture):
    fixture = org_and_team_fixture

    # 1. Team Lead creates task
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res_create = client.post('/api/tasks', json={
        'title': 'Feature Implementation',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
        'status': 'in_progress',
    })
    task_id = res_create.get_json()['data']['id']

    # 2. Employee submits work for review
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    res_submit = client.post(f'/api/tasks/{task_id}/submit', json={
        'notes': 'Implemented feature branch feature/xyz. All 15 tests pass.'
    })
    assert res_submit.status_code == 200
    task_sub = res_submit.get_json()['data']
    assert task_sub['status'] == 'in_review'
    assert 'Implemented feature branch' in task_sub['submission_notes']

    # 3. Employee cannot approve own task
    res_self_review = client.post(f'/api/tasks/{task_id}/review', json={
        'action': 'approve',
        'notes': 'Self approval should fail',
    })
    assert res_self_review.status_code == 403

    # 4. Team Lead approves the task
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res_review = client.post(f'/api/tasks/{task_id}/review', json={
        'action': 'approve',
        'notes': 'Great job! Clean tests and matches specification.',
    })
    assert res_review.status_code == 200
    task_approved = res_review.get_json()['data']
    assert task_approved['status'] == 'completed'
    assert task_approved['completed_at'] is not None
    assert 'Great job!' in task_approved['review_notes']


def test_submission_and_lead_request_changes_workflow(client, org_and_team_fixture):
    fixture = org_and_team_fixture

    # 1. Team Lead creates task
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res_create = client.post('/api/tasks', json={
        'title': 'Documentation Task',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
        'status': 'in_progress',
    })
    task_id = res_create.get_json()['data']['id']

    # 2. Employee submits work for review
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    client.post(f'/api/tasks/{task_id}/submit', json={'notes': 'First draft done'})

    # 3. Team Lead requests changes
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res_review = client.post(f'/api/tasks/{task_id}/review', json={
        'action': 'request_changes',
        'notes': 'Please add API request/response examples to section 3.',
    })
    assert res_review.status_code == 200
    task_changes = res_review.get_json()['data']
    assert task_changes['status'] == 'changes_requested'
    assert task_changes['completed_at'] is None
    assert 'API request/response examples' in task_changes['review_notes']

    # 4. Employee sees changes requested and re-submits
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    res_resubmit = client.post(f'/api/tasks/{task_id}/submit', json={
        'notes': 'Added requested request/response examples.'
    })
    assert res_resubmit.status_code == 200
    assert res_resubmit.get_json()['data']['status'] == 'in_review'


# ── Test 7: Task Status History and Audit Trail ─────────────────────────────────

def test_task_status_history_audit_trail(client, org_and_team_fixture):
    fixture = org_and_team_fixture

    # Lead creates task -> history created
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    res_create = client.post('/api/tasks', json={
        'title': 'Audit Trail Task',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
        'status': 'todo',
    })
    task_id = res_create.get_json()['data']['id']

    # Employee moves to in_progress
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    client.put(f'/api/tasks/{task_id}', json={'status': 'in_progress'})

    # Employee submits
    client.post(f'/api/tasks/{task_id}/submit', json={'notes': 'Done'})

    # Lead approves
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')
    client.post(f'/api/tasks/{task_id}/review', json={'action': 'approve', 'notes': 'LGTM'})

    # Fetch task detail and verify history
    res_detail = client.get(f'/api/tasks/{task_id}')
    assert res_detail.status_code == 200
    history = res_detail.get_json()['data']['status_history']
    assert len(history) >= 4

    statuses = [h['new_status'] for h in history]
    assert 'completed' in statuses
    assert 'in_review' in statuses
    assert 'in_progress' in statuses
    assert 'todo' in statuses


# ── Test 8: Task Search and Filtering (Scope, Team, Statuses) ───────────────────

def test_task_search_and_filters_company_workflow(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'lead1@test.com', 'Lead1Pass123!')

    # Create task 1: In Progress
    client.post('/api/tasks', json={
        'title': 'Frontend Dashboard Widget',
        'description': 'Chart display of company tasks',
        'status': 'in_progress',
        'priority': 'high',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
    })

    # Create task 2: Blocked
    client.post('/api/tasks', json={
        'title': 'Database Migration Script',
        'description': 'Add missing columns',
        'status': 'blocked',
        'priority': 'medium',
        'team_id': fixture['team_alpha_id'],
        'assigned_to_id': fixture['emp1_id'],
    })

    # Filter by status: in_progress
    res_status = client.get('/api/tasks?status=in_progress')
    assert res_status.status_code == 200
    tasks_prog = res_status.get_json()['data']
    assert all(t['status'] == 'in_progress' for t in tasks_prog)

    # Filter by status: blocked
    res_blocked = client.get('/api/tasks?status=blocked')
    assert res_blocked.status_code == 200
    tasks_blocked = res_blocked.get_json()['data']
    assert any(t['status'] == 'blocked' for t in tasks_blocked)

    # Filter by scope: assigned_to_me
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')
    res_scope = client.get('/api/tasks?scope=assigned_to_me')
    assert res_scope.status_code == 200
    assert len(res_scope.get_json()['data']) >= 2

    # Search query
    res_q = client.get('/api/tasks?q=Widget')
    assert res_q.status_code == 200
    tasks_q = res_q.get_json()['data']
    assert len(tasks_q) == 1
    assert 'Widget' in tasks_q[0]['title']


# ── Test 9: Web Task Detail Page Route ──────────────────────────────────────────

def test_task_detail_page_loads(client, org_and_team_fixture):
    fixture = org_and_team_fixture
    login_as(client, 'emp1@test.com', 'Emp1Pass123!')

    res_create = client.post('/api/tasks', json={'title': 'Personal Task For Detail Page'})
    task_id = res_create.get_json()['data']['id']

    res_page = client.get(f'/tasks/{task_id}')
    assert res_page.status_code == 200
    assert b'data-task-id' in res_page.data
