"""
Comprehensive test suite for TaskNest Enterprise features:
- Organization, Departments, Teams, Team Membership
- Role permissions (Super Admin, Admin/HR, Team Lead, Employee)
- Task assignment & Kanban lifecycle
- Task discussion threads & messages
- File attachment upload & authorized download
- Work submissions & review workflows (approval / changes requested)
- Attendance check-in/out & timesheets
- Meetings scheduling & calendar feed
- In-app notifications
- Productivity analytics & CSV exports
"""
import io
import pytest
from datetime import datetime, date, timedelta, timezone
from app import create_app, db
from app.models import (
    User, Organization, Department, Team, TeamMember, Task,
    TaskMessage, TaskAttachment, WorkSubmission, Attendance,
    Meeting, MeetingAttendee, Notification,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE
)


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-enterprise-secret',
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
def enterprise_setup(app):
    """Seed test organization, users with various roles, departments, and teams."""
    with app.app_context():
        org = Organization(name='Acme Enterprise', slug='acme-enterprise')
        db.session.add(org)
        db.session.flush()

        dept = Department(name='Engineering', organization_id=org.id)
        db.session.add(dept)
        db.session.flush()

        # 1. Super Admin
        super_admin = User(
            full_name='Super Admin',
            username='superadmin',
            email='superadmin@acme.com',
            role=ROLE_SUPER_ADMIN,
            organization_id=org.id,
            designation='Executive Director',
            account_active=True
        )
        super_admin.set_password('AdminPass123!')
        db.session.add(super_admin)

        # 2. Admin / HR
        admin = User(
            full_name='HR Admin',
            username='hradmin',
            email='hradmin@acme.com',
            role=ROLE_ADMIN,
            organization_id=org.id,
            designation='HR Manager',
            account_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        # 3. Team Lead
        lead = User(
            full_name='Tech Lead',
            username='techlead',
            email='techlead@acme.com',
            role=ROLE_TEAM_LEAD,
            organization_id=org.id,
            department_id=dept.id,
            designation='Senior Lead',
            account_active=True
        )
        lead.set_password('LeadPass123!')
        db.session.add(lead)
        db.session.flush()

        # Team
        team = Team(
            name='Core Backend',
            department_id=dept.id,
            organization_id=org.id,
            lead_id=lead.id
        )
        db.session.add(team)
        db.session.flush()

        lead.team_id = team.id

        # 4. Employee A
        emp_a = User(
            full_name='Alice Employee',
            username='alice',
            email='alice@acme.com',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
            department_id=dept.id,
            team_id=team.id,
            manager_id=lead.id,
            designation='Software Engineer',
            account_active=True
        )
        emp_a.set_password('AlicePass123!')
        db.session.add(emp_a)

        # 5. Employee B
        emp_b = User(
            full_name='Bob Employee',
            username='bob',
            email='bob@acme.com',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
            department_id=dept.id,
            designation='QA Engineer',
            account_active=True
        )
        emp_b.set_password('BobPass123!')
        db.session.add(emp_b)

        db.session.commit()

        # Memberships
        db.session.add(TeamMember(team_id=team.id, user_id=lead.id))
        db.session.add(TeamMember(team_id=team.id, user_id=emp_a.id))
        db.session.commit()

        return {
            'org_id': org.id,
            'dept_id': dept.id,
            'team_id': team.id,
            'super_admin_id': super_admin.id,
            'admin_id': admin.id,
            'lead_id': lead.id,
            'emp_a_id': emp_a.id,
            'emp_b_id': emp_b.id,
        }


def login(client, email, password):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


# ── Organization, Departments & Teams Tests ───────────────────────────────────

def test_organization_retrieval(client, enterprise_setup):
    login(client, 'alice@acme.com', 'AlicePass123!')
    res = client.get('/api/organization')
    assert res.status_code == 200
    data = res.get_json()['data']
    assert data['name'] == 'Acme Enterprise'


def test_admin_can_create_department_and_team(client, enterprise_setup):
    login(client, 'hradmin@acme.com', 'AdminPass123!')

    # Create Department
    res_d = client.post('/api/organization/departments', json={'name': 'Marketing'})
    assert res_d.status_code == 201
    dept_id = res_d.get_json()['data']['id']

    # Create Team
    res_t = client.post('/api/organization/teams', json={
        'name': 'Growth Marketing',
        'department_id': dept_id,
        'lead_id': enterprise_setup['lead_id']
    })
    assert res_t.status_code == 201
    assert res_t.get_json()['data']['name'] == 'Growth Marketing'


def test_regular_employee_cannot_create_department(client, enterprise_setup):
    login(client, 'alice@acme.com', 'AlicePass123!')
    res = client.post('/api/organization/departments', json={'name': 'Illegal Dept'})
    assert res.status_code == 403


# ── Employee Directory & Management Tests ─────────────────────────────────────

def test_employee_directory_list_and_search(client, enterprise_setup):
    login(client, 'alice@acme.com', 'AlicePass123!')
    res = client.get('/api/employees?q=Alice')
    assert res.status_code == 200
    emps = res.get_json()['data']
    assert len(emps) == 1
    assert emps[0]['username'] == 'alice'


def test_admin_can_provision_new_employee(client, enterprise_setup):
    login(client, 'hradmin@acme.com', 'AdminPass123!')
    res = client.post('/api/employees', json={
        'full_name': 'Charlie Developer',
        'username': 'charlie',
        'email': 'charlie@acme.com',
        'password': 'TempPassword123!',
        'role': 'employee',
        'designation': 'Frontend Engineer',
        'team_id': enterprise_setup['team_id']
    })
    assert res.status_code == 201
    data = res.get_json()['data']
    assert data['email'] == 'charlie@acme.com'
    assert data['role'] == 'employee'


def test_admin_can_deactivate_employee_account(client, enterprise_setup):
    login(client, 'hradmin@acme.com', 'AdminPass123!')
    emp_b_id = enterprise_setup['emp_b_id']
    res = client.patch(f'/api/employees/{emp_b_id}/status', json={'active': False})
    assert res.status_code == 200
    assert res.get_json()['data']['account_active'] is False

    # Deactivated account cannot log in
    client.post('/api/auth/logout')
    login_res = login(client, 'bob@acme.com', 'BobPass123!')
    assert login_res.status_code == 403


# ── Task Assignment & Collaboration Tests ──────────────────────────────────────

def test_lead_can_assign_task_to_employee(client, enterprise_setup):
    login(client, 'techlead@acme.com', 'LeadPass123!')
    res = client.post('/api/tasks', json={
        'title': 'Build REST API endpoint',
        'description': 'Implement user profile endpoints with validation.',
        'priority': 'high',
        'status': 'todo',
        'assignee_id': enterprise_setup['emp_a_id'],
        'team_id': enterprise_setup['team_id'],
        'acceptance_criteria': 'All unit tests pass 100%'
    })
    assert res.status_code == 201
    task_id = res.get_json()['data']['id']
    assert res.get_json()['data']['assignee_id'] == enterprise_setup['emp_a_id']

    # Alice can see the assigned task
    client.post('/api/auth/logout')
    login(client, 'alice@acme.com', 'AlicePass123!')
    get_res = client.get(f'/api/tasks/{task_id}')
    assert get_res.status_code == 200
    assert get_res.get_json()['data']['title'] == 'Build REST API endpoint'


def test_task_discussions_and_messages(client, enterprise_setup):
    # Tech lead creates task
    login(client, 'techlead@acme.com', 'LeadPass123!')
    res = client.post('/api/tasks', json={
        'title': 'Discussion Test Task',
        'assignee_id': enterprise_setup['emp_a_id']
    })
    task_id = res.get_json()['data']['id']

    # Alice posts message
    client.post('/api/auth/logout')
    login(client, 'alice@acme.com', 'AlicePass123!')
    msg_res = client.post(f'/api/tasks/{task_id}/messages', json={
        'content': 'Should we use JSON or form data for the upload?'
    })
    assert msg_res.status_code == 201
    assert 'JSON or form data' in msg_res.get_json()['data']['content']

    # Verify message thread
    list_res = client.get(f'/api/tasks/{task_id}/messages')
    assert list_res.status_code == 200
    assert len(list_res.get_json()['data']) == 1


def test_work_submission_and_lead_review(client, enterprise_setup):
    # Tech lead creates task
    login(client, 'techlead@acme.com', 'LeadPass123!')
    res = client.post('/api/tasks', json={
        'title': 'Review Flow Task',
        'assignee_id': enterprise_setup['emp_a_id']
    })
    task_id = res.get_json()['data']['id']

    # Alice submits deliverable
    client.post('/api/auth/logout')
    login(client, 'alice@acme.com', 'AlicePass123!')
    sub_res = client.post(f'/api/tasks/{task_id}/submissions', json={
        'notes': 'Completed feature branch, tests passing.'
    })
    assert sub_res.status_code == 201
    sub_id = sub_res.get_json()['data']['id']

    # Task status transitioned to in_review
    task_check = client.get(f'/api/tasks/{task_id}')
    assert task_check.get_json()['data']['status'] == 'in_review'

    # Tech lead approves deliverable
    client.post('/api/auth/logout')
    login(client, 'techlead@acme.com', 'LeadPass123!')
    rev_res = client.post(f'/api/tasks/{task_id}/submissions/{sub_id}/review', json={
        'decision': 'approve',
        'review_notes': 'Great job, code looks solid.'
    })
    assert rev_res.status_code == 200
    assert rev_res.get_json()['data']['status'] == 'approved'

    # Task status now completed
    completed_task = client.get(f'/api/tasks/{task_id}')
    assert completed_task.get_json()['data']['status'] == 'completed'
    assert completed_task.get_json()['data']['progress'] == 100


# ── File Attachments & Secure Download Tests ───────────────────────────────────

def test_file_upload_and_authorized_download(client, enterprise_setup):
    login(client, 'techlead@acme.com', 'LeadPass123!')
    res = client.post('/api/tasks', json={
        'title': 'Attachment Test Task',
        'assignee_id': enterprise_setup['emp_a_id']
    })
    task_id = res.get_json()['data']['id']

    # Upload valid text file
    file_content = b"Task specification and technical design notes."
    upload_res = client.post(
        f'/api/tasks/{task_id}/attachments',
        data={'file': (io.BytesIO(file_content), 'specs.txt')},
        content_type='multipart/form-data'
    )
    assert upload_res.status_code == 201
    file_id = upload_res.get_json()['data']['id']

    # Alice (assignee) can download the file
    client.post('/api/auth/logout')
    login(client, 'alice@acme.com', 'AlicePass123!')
    dl_res = client.get(f'/api/files/{file_id}/download')
    assert dl_res.status_code == 200
    assert dl_res.data == file_content

    # Bob (unrelated employee) is denied access
    client.post('/api/auth/logout')
    login(client, 'bob@acme.com', 'BobPass123!')
    unauth_dl = client.get(f'/api/files/{file_id}/download')
    assert unauth_dl.status_code == 403


# ── Attendance & Timesheets Tests ──────────────────────────────────────────────

def test_attendance_checkin_checkout_flow(client, enterprise_setup):
    login(client, 'alice@acme.com', 'AlicePass123!')

    # 1. Check in
    ci_res = client.post('/api/attendance/check-in', json={'notes': 'Morning shift started.'})
    assert ci_res.status_code == 201
    assert ci_res.get_json()['data']['status'] == 'active'

    # 2. Prevent duplicate check-in
    dup_res = client.post('/api/attendance/check-in', json={})
    assert dup_res.status_code == 409

    # 3. Check today status
    today_res = client.get('/api/attendance/today')
    assert today_res.status_code == 200
    assert today_res.get_json()['data']['is_checked_in'] is True

    # 4. Check out
    co_res = client.post('/api/attendance/check-out', json={'notes': 'Done for the day.'})
    assert co_res.status_code == 200
    assert co_res.get_json()['data']['status'] == 'completed'

    # 5. Prevent checkout when not checked in
    co_err = client.post('/api/attendance/check-out')
    assert co_err.status_code == 400


# ── Calendar & Meetings Tests ──────────────────────────────────────────────────

def test_meetings_schedule_and_calendar_feed(client, enterprise_setup):
    login(client, 'techlead@acme.com', 'LeadPass123!')
    now = datetime.now(timezone.utc)
    start_time = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    # Schedule meeting
    res = client.post('/api/meetings', json={
        'title': 'Sprint Planning',
        'agenda': 'Review backlog and plan Q4 goals.',
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
        'location_or_link': 'https://meet.google.com/xyz',
        'team_id': enterprise_setup['team_id'],
        'invitee_ids': [enterprise_setup['emp_a_id']]
    })
    assert res.status_code == 201
    meeting_id = res.get_json()['data']['id']

    # Alice checks calendar feed
    client.post('/api/auth/logout')
    login(client, 'alice@acme.com', 'AlicePass123!')
    cal_res = client.get('/api/calendar/events')
    assert cal_res.status_code == 200
    events = cal_res.get_json()['data']
    assert any(e['title'] == 'Meeting: Sprint Planning' for e in events)

    # Alice RSVPs
    rsvp_res = client.post(f'/api/meetings/{meeting_id}/rsvp', json={'status': 'accepted'})
    assert rsvp_res.status_code == 200
    assert rsvp_res.get_json()['data']['status'] == 'accepted'


# ── In-App Notifications Tests ─────────────────────────────────────────────────

def test_notification_delivery_and_read(client, enterprise_setup):
    # Tech lead assigns task to Alice -> Alice receives notification
    login(client, 'techlead@acme.com', 'LeadPass123!')
    client.post('/api/tasks', json={
        'title': 'Task with Notification',
        'assignee_id': enterprise_setup['emp_a_id']
    })

    # Alice views notifications
    client.post('/api/auth/logout')
    login(client, 'alice@acme.com', 'AlicePass123!')
    notif_res = client.get('/api/notifications')
    assert notif_res.status_code == 200
    notifs = notif_res.get_json()['data']['notifications']
    assert len(notifs) >= 1
    assert 'Task with Notification' in notifs[0]['title']

    # Mark as read
    notif_id = notifs[0]['id']
    read_res = client.patch(f'/api/notifications/{notif_id}/read')
    assert read_res.status_code == 200
    assert read_res.get_json()['data']['is_read'] is True


# ── Reports & CSV Export Tests ─────────────────────────────────────────────────

def test_productivity_reports_and_csv_exports(client, enterprise_setup):
    login(client, 'techlead@acme.com', 'LeadPass123!')

    # Productivity report
    prod_res = client.get('/api/reports/productivity')
    assert prod_res.status_code == 200
    data = prod_res.get_json()['data']
    assert 'total_tasks' in data
    assert 'completion_trends' in data

    # CSV Task Export
    csv_res = client.get('/api/reports/export/tasks')
    assert csv_res.status_code == 200
    assert csv_res.headers['Content-Type'].startswith('text/csv')
    assert b'Title' in csv_res.data


# ── Website Multi-Page & Role Route Tests ──────────────────────────────────────

def test_public_homepage_and_login_layout(client, enterprise_setup):
    res = client.get('/')
    assert res.status_code == 200
    assert b'Work together.' in res.data
    assert b'Deliver better.' in res.data
    assert b'Assign and track work' in res.data
    assert b'Welcome back' in res.data
    assert b'Sign In' in res.data

    # Working login authentication against database
    login_res = client.post('/api/auth/login', json={
        'email': 'superadmin@acme.com',
        'password': 'AdminPass123!'
    })
    assert login_res.status_code == 200
    assert login_res.get_json()['data']['role'] == 'super_admin'


def test_password_recovery_and_reset_workflow(client, enterprise_setup):
    # 1. Request forgot password
    forgot_res = client.post('/api/auth/forgot-password', json={
        'email': 'alice@acme.com'
    })
    assert forgot_res.status_code == 200
    token = forgot_res.get_json()['data']['token']
    assert token is not None

    # 2. Reset page with token loads
    reset_page_res = client.get(f'/reset-password/{token}')
    assert reset_page_res.status_code == 200
    assert b'Set New Password' in reset_page_res.data

    # 3. Post new password
    reset_res = client.post('/api/auth/reset-password', json={
        'token': token,
        'password': 'BrandNewAlicePass456!',
        'confirm_password': 'BrandNewAlicePass456!'
    })
    assert reset_res.status_code == 200

    # 4. Login with old password fails
    fail_res = client.post('/api/auth/login', json={
        'email': 'alice@acme.com',
        'password': 'AlicePass123!'
    })
    assert fail_res.status_code == 401

    # 5. Login with new password succeeds
    success_res = client.post('/api/auth/login', json={
        'email': 'alice@acme.com',
        'password': 'BrandNewAlicePass456!'
    })
    assert success_res.status_code == 200


def test_role_based_page_access_and_unauthorized_protection(client, enterprise_setup):
    # Login as Employee Alice
    login(client, 'alice@acme.com', 'AlicePass123!')

    # Employee accesses Employee pages -> 200
    emp_dash = client.get('/employee/dashboard')
    assert emp_dash.status_code == 200

    emp_tasks = client.get('/employee/my-tasks')
    assert emp_tasks.status_code == 200

    emp_att = client.get('/employee/attendance')
    assert emp_att.status_code == 200

    emp_cal = client.get('/employee/calendar')
    assert emp_cal.status_code == 200

    # Employee tries to access Admin pages -> Redirects to /unauthorized
    admin_access = client.get('/admin/employees')
    assert admin_access.status_code == 302
    assert '/unauthorized' in admin_access.headers['Location']

    # Employee tries to access Lead pages -> Redirects to /unauthorized
    lead_access = client.get('/lead/dashboard')
    assert lead_access.status_code == 302
    assert '/unauthorized' in lead_access.headers['Location']

    # Visiting /unauthorized returns 403 Forbidden
    unauth_page = client.get('/unauthorized')
    assert unauth_page.status_code == 403
    assert b'Access Restricted' in unauth_page.data

    # Login as Admin -> Admin pages return 200
    client.post('/api/auth/logout')
    login(client, 'hradmin@acme.com', 'AdminPass123!')

    admin_dash = client.get('/admin/dashboard')
    assert admin_dash.status_code == 200

    admin_emp = client.get('/admin/employees')
    assert admin_emp.status_code == 200

    admin_rep = client.get('/admin/reports')
    assert admin_rep.status_code == 200


def test_task_detail_page_view(client, enterprise_setup):
    login(client, 'techlead@acme.com', 'LeadPass123!')

    # Create task
    create_res = client.post('/api/tasks', json={
        'title': 'Standalone Task Detail Test',
        'description': 'Comprehensive detail page test description',
        'priority': 'high',
        'assignee_id': enterprise_setup['emp_a_id']
    })
    task_id = create_res.get_json()['data']['id']

    # Lead can view dedicated task detail page
    detail_res = client.get(f'/tasks/{task_id}')
    assert detail_res.status_code == 200
    assert b'Standalone Task Detail Test' in detail_res.data
    assert b'Subtasks' in detail_res.data
    assert b'Discussion' in detail_res.data

    # Assignee Alice can view
    client.post('/api/auth/logout')
    login(client, 'alice@acme.com', 'AlicePass123!')
    alice_view = client.get(f'/tasks/{task_id}')
    assert alice_view.status_code == 200

    # Unrelated user Bob (different org/team unassigned) is unauthorized
    client.post('/api/auth/logout')
    login(client, 'bob@acme.com', 'BobPass123!')
    bob_view = client.get(f'/tasks/{task_id}')
    assert bob_view.status_code == 302
    assert '/unauthorized' in bob_view.headers['Location']

