"""
tests/test_admin_tl_attendance.py

Comprehensive test suite verifying Admin and Team Lead exclusive Attendance & Timesheets workflows:
- Strict role-based access: Employees are locked down from management page, records, metrics, reviews, exports.
- Admin view: Organization-wide metrics (all 6 cards), filterable records, CSV export, full review authority.
- Team Lead view: Strictly scoped to authorized team members + self. Unrelated teams and employees are strictly excluded.
- Live shift tracking, timestamp-backed duration calculation, zero-duration/short session accuracy, and missing checkout detection.
- Correction request workflow with enforced self-review protection (no user can approve their own request).
- Unbroken employee personal check-in/out on employee dashboard.
"""
import io
import csv
import pytest
from datetime import datetime, date, timedelta, timezone
from app import create_app, db
from app.models import (
    User, Organization, Department, Team, TeamMember, Attendance, AttendanceCorrection,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE
)


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-attendance-secret',
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
def attendance_setup(app):
    """
    Setup multi-team environment:
    - Organization: Acme Corp
    - Department: Tech
    - Team 1: 'Frontend' led by Lead 1 (lead1@acme.com) with Member Alice (alice@acme.com)
    - Team 2: 'Backend' led by Lead 2 (lead2@acme.com) with Member Bob (bob@acme.com)
    - Admin: Carol Admin (admin@acme.com)
    """
    with app.app_context():
        org = Organization(name='Acme Corp', slug='acme-corp')
        db.session.add(org)
        db.session.flush()

        dept = Department(name='Tech', organization_id=org.id)
        db.session.add(dept)
        db.session.flush()

        # Admin
        admin = User(
            full_name='Carol Admin',
            username='admin_carol',
            email='admin@acme.com',
            employee_id_code='EMP-0001',
            role=ROLE_ADMIN,
            organization_id=org.id,
            account_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)
        db.session.flush()

        # Team 1 Lead
        lead1 = User(
            full_name='Lead One',
            username='lead1',
            email='lead1@acme.com',
            employee_id_code='EMP-0010',
            role=ROLE_TEAM_LEAD,
            organization_id=org.id,
            department_id=dept.id,
            account_active=True
        )
        lead1.set_password('LeadPass123!')
        db.session.add(lead1)
        db.session.flush()

        team1 = Team(name='Frontend Team', department_id=dept.id, organization_id=org.id, lead_id=lead1.id)
        db.session.add(team1)
        db.session.flush()
        lead1.team_id = team1.id

        # Employee Alice (in Team 1)
        alice = User(
            full_name='Alice Smith',
            username='alice',
            email='alice@acme.com',
            employee_id_code='EMP-0101',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
            department_id=dept.id,
            team_id=team1.id,
            manager_id=lead1.id,
            account_active=True
        )
        alice.set_password('AlicePass123!')
        db.session.add(alice)
        db.session.flush()

        # Team 2 Lead
        lead2 = User(
            full_name='Lead Two',
            username='lead2',
            email='lead2@acme.com',
            employee_id_code='EMP-0020',
            role=ROLE_TEAM_LEAD,
            organization_id=org.id,
            department_id=dept.id,
            account_active=True
        )
        lead2.set_password('LeadPass123!')
        db.session.add(lead2)
        db.session.flush()

        team2 = Team(name='Backend Team', department_id=dept.id, organization_id=org.id, lead_id=lead2.id)
        db.session.add(team2)
        db.session.flush()
        lead2.team_id = team2.id

        # Employee Bob (in Team 2)
        bob = User(
            full_name='Bob Jones',
            username='bob',
            email='bob@acme.com',
            employee_id_code='EMP-0202',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
            department_id=dept.id,
            team_id=team2.id,
            manager_id=lead2.id,
            account_active=True
        )
        bob.set_password('BobPass123!')
        db.session.add(bob)
        db.session.commit()

        return {
            'org_id': org.id,
            'team1_id': team1.id,
            'team2_id': team2.id,
            'admin_id': admin.id,
            'lead1_id': lead1.id,
            'lead2_id': lead2.id,
            'alice_id': alice.id,
            'bob_id': bob.id,
        }


def login(client, email, password):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


# ── 1. Employee Lockdown Tests ────────────────────────────────────────────────

def test_employee_locked_down_from_attendance_management(client, attendance_setup):
    """
    Employees must be completely prevented from accessing the Attendance Management page,
    management APIs, records, metrics, exports, and correction reviews.
    """
    login(client, 'alice@acme.com', 'AlicePass123!')

    # Web page access: /attendance redirects to /unauthorized (403)
    res_page = client.get('/attendance')
    assert res_page.status_code == 302
    assert '/unauthorized' in res_page.headers['Location']

    unauth = client.get('/unauthorized')
    assert unauth.status_code == 403

    # API endpoints lockdown:
    # 1. Summary metrics
    res_metrics = client.get('/api/attendance/metrics')
    assert res_metrics.status_code == 403
    assert 'Permission denied' in res_metrics.get_json()['error']

    # 2. Paginated records
    res_records = client.get('/api/attendance/records')
    assert res_records.status_code == 403

    # 3. CSV export
    res_export = client.get('/api/attendance/export')
    assert res_export.status_code == 403

    # 4. Organization attendance
    res_org = client.get('/api/attendance/organization')
    assert res_org.status_code == 403

    # 5. Team attendance
    res_team = client.get('/api/attendance/team')
    assert res_team.status_code == 403

    # 6. Correction review
    res_review = client.post('/api/attendance/corrections/1/review', json={'decision': 'approve'})
    assert res_review.status_code == 403


def test_employee_personal_shift_operations_preserved(client, attendance_setup):
    """
    Preserve existing employee personal check-in, check-out, today status,
    and timesheet history without interruption.
    """
    login(client, 'alice@acme.com', 'AlicePass123!')

    # Today status before check-in
    res_today = client.get('/api/attendance/today')
    assert res_today.status_code == 200
    d_today = res_today.get_json()['data']
    assert d_today['is_checked_in'] is False

    # Check-in
    res_ci = client.post('/api/attendance/check-in', json={'notes': 'Morning shift started'})
    assert res_ci.status_code == 201
    assert res_ci.get_json()['data']['status'] == 'active'

    # Cannot check in again while active (prevent duplicate active sessions)
    res_dup = client.post('/api/attendance/check-in', json={})
    assert res_dup.status_code == 409

    # Check-out
    res_co = client.post('/api/attendance/check-out', json={'notes': 'Shift ended'})
    assert res_co.status_code == 200
    assert res_co.get_json()['data']['status'] == 'completed'

    # Personal history
    res_my = client.get('/api/attendance/my')
    assert res_my.status_code == 200
    records = res_my.get_json()['data']['records']
    assert len(records) >= 1
    assert records[0]['status'] == 'completed'


# ── 2. Admin Scope Tests ──────────────────────────────────────────────────────

def test_admin_attendance_overview_and_metrics(client, attendance_setup):
    """
    Admin has full organization-wide view:
    - Can access /attendance web page
    - Retrieves 6 real database-backed summary metrics
    - Retrieves filterable attendance records across all teams
    - Exports organization CSV
    """
    setup = attendance_setup
    today = date.today()

    # Seed attendances for Alice (Team 1) and Bob (Team 2)
    with client.application.app_context():
        # Alice completed shift today (2 hours)
        att_alice = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=9),
            check_out=datetime.combine(today, datetime.min.time()) + timedelta(hours=11),
            duration_minutes=120,
            status='completed',
            notes='Alice morning tasks'
        )
        # Bob active shift today (started at 10 AM)
        att_bob = Attendance(
            user_id=setup['bob_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=10),
            status='active',
            notes='Bob working on backend'
        )
        # Missing checkout from 2 days ago for Alice
        att_missing = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today - timedelta(days=2), datetime.min.time()) + timedelta(hours=9),
            status='active',
            notes='Alice forgotten checkout'
        )
        db.session.add_all([att_alice, att_bob, att_missing])
        db.session.commit()

        # Add a pending correction request
        corr = AttendanceCorrection(
            attendance_id=att_missing.id,
            user_id=setup['alice_id'],
            requested_check_in=att_missing.check_in,
            requested_check_out=att_missing.check_in + timedelta(hours=8),
            reason='Forgot checkout due to network outage',
            status='pending'
        )
        db.session.add(corr)
        db.session.commit()

    login(client, 'admin@acme.com', 'AdminPass123!')

    # 1. Admin accesses /attendance
    res_page = client.get('/attendance')
    assert res_page.status_code == 200
    assert b'Attendance & Timesheets' in res_page.data
    assert b'Organization Timesheet' in res_page.data

    # 2. Admin retrieves 6 metrics
    res_metrics = client.get('/api/attendance/metrics')
    assert res_metrics.status_code == 200
    metrics = res_metrics.get_json()['data']

    # Both Bob and the missing checkout session are currently active (status == 'active')
    assert metrics['currently_checked_in'] >= 2
    # Distinct users checked in today (Alice and Bob)
    assert metrics['checked_in_today'] >= 2
    # Total hours today > 0
    assert metrics['total_working_hours_today'] > 0
    # Missing checkout session from 2 days ago
    assert metrics['missing_checkouts'] >= 1
    # Pending correction request
    assert metrics['pending_corrections'] >= 1

    # 3. Admin records endpoint
    res_records = client.get('/api/attendance/records')
    assert res_records.status_code == 200
    records_data = res_records.get_json()['data']
    items = records_data['items']
    assert len(items) >= 3

    # Check employee identities
    emp_names = [i['employee_name'] for i in items]
    emp_codes = [i['employee_id_code'] for i in items]
    assert 'Alice Smith' in emp_names
    assert 'Bob Jones' in emp_names
    assert 'EMP-0101' in emp_codes
    assert 'EMP-0202' in emp_codes

    # 4. Filter by text search q (Bob)
    res_filter_q = client.get('/api/attendance/records?q=Bob')
    assert res_filter_q.status_code == 200
    q_items = res_filter_q.get_json()['data']['items']
    assert all('Bob' in i['employee_name'] for i in q_items)

    # 5. Filter by missing checkouts
    res_filter_missing = client.get('/api/attendance/records?missing_checkout=true')
    assert res_filter_missing.status_code == 200
    missing_items = res_filter_missing.get_json()['data']['items']
    assert len(missing_items) >= 1
    assert all(i['is_missing_checkout'] is True for i in missing_items)

    # 6. Admin CSV export
    res_export = client.get('/api/attendance/export')
    assert res_export.status_code == 200
    assert res_export.mimetype == 'text/csv'
    csv_text = res_export.data.decode('utf-8')
    assert 'Record ID,Employee Name,Employee ID,Role,Team' in csv_text
    assert 'Alice Smith' in csv_text
    assert 'Bob Jones' in csv_text


# ── 3. Team Lead Scoped Access Tests ──────────────────────────────────────────

def test_team_lead_scoped_visibility_and_restrictions(client, attendance_setup):
    """
    Team Lead must strictly see only their authorized team members + self:
    - Lead 1 sees Lead 1 and Alice (Frontend Team).
    - Lead 1 CANNOT see Bob (Backend Team) in metrics, records, team timesheets, or CSV export.
    - Lead 1 cannot request records of other teams.
    """
    setup = attendance_setup
    today = date.today()

    with client.application.app_context():
        # Alice (Team 1) attendance
        att_alice = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=9),
            check_out=datetime.combine(today, datetime.min.time()) + timedelta(hours=14),
            duration_minutes=300,
            status='completed',
            notes='Alice frontend design'
        )
        # Bob (Team 2) attendance
        att_bob = Attendance(
            user_id=setup['bob_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=9),
            check_out=datetime.combine(today, datetime.min.time()) + timedelta(hours=15),
            duration_minutes=360,
            status='completed',
            notes='Bob api architecture'
        )
        db.session.add_all([att_alice, att_bob])
        db.session.commit()

    # Login as Lead 1 (Frontend Team)
    login(client, 'lead1@acme.com', 'LeadPass123!')

    # 1. Lead 1 accesses /attendance
    res_page = client.get('/attendance')
    assert res_page.status_code == 200
    # Organization timesheet tab is NOT shown to Team Lead
    assert b'Organization Timesheet' not in res_page.data

    # 2. Lead 1 metrics: Only includes Alice (and Lead 1 if active)
    res_metrics = client.get('/api/attendance/metrics')
    assert res_metrics.status_code == 200
    m_data = res_metrics.get_json()['data']
    # Alice worked 5.0h (300 mins). Bob worked 6.0h (360 mins).
    # TL metrics must ONLY sum Alice (5.0h), not Bob!
    assert m_data['total_working_hours_today'] == 5.0

    # 3. Lead 1 records: Only Alice, Bob MUST NOT appear
    res_records = client.get('/api/attendance/records')
    assert res_records.status_code == 200
    items = res_records.get_json()['data']['items']
    names = [i['employee_name'] for i in items]
    assert 'Alice Smith' in names
    assert 'Bob Jones' not in names

    # 4. Lead 1 attempts to query Bob explicitly -> 403 Forbidden
    res_target_bob = client.get(f"/api/attendance/records?user_id={setup['bob_id']}")
    assert res_target_bob.status_code == 403

    # 5. Lead 1 attempts to query Team 2 explicitly -> 403 Forbidden
    res_target_team2 = client.get(f"/api/attendance/records?team_id={setup['team2_id']}")
    assert res_target_team2.status_code == 403

    # 6. Team timesheet endpoint: Only includes Alice and Lead 1
    res_team = client.get('/api/attendance/team')
    assert res_team.status_code == 200
    team_members = res_team.get_json()['data']
    team_names = [tm['name'] for tm in team_members]
    assert 'Alice Smith' in team_names
    assert 'Bob Jones' not in team_names

    # 7. Lead 1 CSV Export: Only includes Alice, Bob must be excluded
    res_export = client.get('/api/attendance/export')
    assert res_export.status_code == 200
    csv_text = res_export.data.decode('utf-8')
    assert 'Alice Smith' in csv_text
    assert 'Bob Jones' not in csv_text


# ── 4. Correction Workflow & Self-Review Prevention ───────────────────────────

def test_correction_request_and_self_review_prevention(client, attendance_setup):
    """
    Verify correction request submission and review workflows:
    - User cannot approve or review their own correction request (enforced on backend with 403).
    - Team Lead can approve/reject correction requests from their team members.
    - Team Lead CANNOT review correction requests from members of another team.
    """
    setup = attendance_setup
    today = date.today()

    with client.application.app_context():
        # Alice shift
        att_alice = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=9),
            check_out=datetime.combine(today, datetime.min.time()) + timedelta(hours=10),
            duration_minutes=60,
            status='completed',
            notes='Alice initial shift'
        )
        # Lead 1 shift
        att_lead1 = Attendance(
            user_id=setup['lead1_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=8),
            status='active',
            notes='Lead 1 shift'
        )
        # Bob shift (Team 2)
        att_bob = Attendance(
            user_id=setup['bob_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=9),
            status='active',
            notes='Bob shift'
        )
        db.session.add_all([att_alice, att_lead1, att_bob])
        db.session.commit()

        # Alice correction request
        corr_alice = AttendanceCorrection(
            attendance_id=att_alice.id,
            user_id=setup['alice_id'],
            requested_check_in=att_alice.check_in,
            requested_check_out=att_alice.check_in + timedelta(hours=8),
            reason='Correction for actual 8 hour work shift',
            status='pending'
        )
        # Lead 1 correction request
        corr_lead1 = AttendanceCorrection(
            attendance_id=att_lead1.id,
            user_id=setup['lead1_id'],
            requested_check_in=att_lead1.check_in,
            requested_check_out=att_lead1.check_in + timedelta(hours=7),
            reason='Forgot to close session',
            status='pending'
        )
        # Bob correction request (Team 2)
        corr_bob = AttendanceCorrection(
            attendance_id=att_bob.id,
            user_id=setup['bob_id'],
            requested_check_in=att_bob.check_in,
            requested_check_out=att_bob.check_in + timedelta(hours=8),
            reason='Bob correction request',
            status='pending'
        )
        db.session.add_all([corr_alice, corr_lead1, corr_bob])
        db.session.commit()

        att_alice_id = att_alice.id
        c_alice_id = corr_alice.id
        c_lead1_id = corr_lead1.id
        c_bob_id = corr_bob.id

    # Login as Lead 1
    login(client, 'lead1@acme.com', 'LeadPass123!')

    # 1. Lead 1 attempts to review their OWN correction request -> Must return 403!
    res_self = client.post(f'/api/attendance/corrections/{c_lead1_id}/review', json={
        'decision': 'approve'
    })
    assert res_self.status_code == 403
    assert 'You cannot review or approve your own correction request' in res_self.get_json()['error']

    # 2. Lead 1 attempts to review Bob's request (Bob is in Team 2) -> Must return 403!
    res_other = client.post(f'/api/attendance/corrections/{c_bob_id}/review', json={
        'decision': 'approve'
    })
    assert res_other.status_code == 403
    assert 'Permission denied to review correction for an employee outside your authorized team' in res_other.get_json()['error']

    # 3. Lead 1 reviews Alice's request (Alice is in Team 1) -> Approved!
    res_approve = client.post(f'/api/attendance/corrections/{c_alice_id}/review', json={
        'decision': 'approve',
        'review_notes': 'Verified time card'
    })
    assert res_approve.status_code == 200
    assert res_approve.get_json()['data']['status'] == 'approved'

    # Verify database updates on Alice's attendance record
    with client.application.app_context():
        updated_att = db.session.get(Attendance, att_alice_id)
        assert updated_att.status == 'corrected'
        assert updated_att.duration_minutes == 480  # 8 hours = 480 minutes


# ── 5. Duration Accuracy & Timestamp Calculations ─────────────────────────────

def test_duration_calculation_accuracy(client, attendance_setup):
    """
    Verify that session durations are strictly calculated from actual timestamps:
    - Sub-minute session calculates as 0 minutes (no artificial 1-minute floor).
    - Multi-hour session calculates exact minute delta.
    - Missing checkout correctly detects shifts active from prior days.
    """
    setup = attendance_setup
    today = date.today()

    with client.application.app_context():
        # 1. 20-second session (sub-minute)
        short_ci = datetime(2026, 10, 20, 10, 0, 0)
        short_co = datetime(2026, 10, 20, 10, 0, 20)
        att_short = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=short_ci,
            check_out=short_co,
            status='completed'
        )
        att_short.calculate_duration()
        assert att_short.duration_minutes == 0  # 20 seconds = 0 minutes

        # 2. 2 hours 15 minutes session
        norm_ci = datetime(2026, 10, 20, 9, 0, 0)
        norm_co = datetime(2026, 10, 20, 11, 15, 0)
        att_norm = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=norm_ci,
            check_out=norm_co,
            status='completed'
        )
        att_norm.calculate_duration()
        assert att_norm.duration_minutes == 135  # 2h 15m = 135 mins
        assert att_norm.to_dict()['duration_hours'] == 2.25

        # 3. Active session started today (not missing checkout)
        att_today_active = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today, datetime.min.time()) + timedelta(hours=8),
            status='active'
        )
        # 4. Active session started yesterday (missing checkout)
        att_old_active = Attendance(
            user_id=setup['alice_id'],
            organization_id=setup['org_id'],
            check_in=datetime.combine(today - timedelta(days=1), datetime.min.time()) + timedelta(hours=9),
            status='active'
        )
        db.session.add_all([att_short, att_norm, att_today_active, att_old_active])
        db.session.commit()

    login(client, 'admin@acme.com', 'AdminPass123!')

    # Check metrics detects exactly 1 missing checkout
    res_m = client.get('/api/attendance/metrics')
    assert res_m.status_code == 200
    assert res_m.get_json()['data']['missing_checkouts'] == 1

    # Check records flags old active session
    res_r = client.get('/api/attendance/records?missing_checkout=true')
    assert res_r.status_code == 200
    items = res_r.get_json()['data']['items']
    assert len(items) == 1
    assert items[0]['is_missing_checkout'] is True
