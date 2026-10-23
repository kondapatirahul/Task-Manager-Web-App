"""
Integration and security tests for Leave / Time-Off Management System (HR & Operations).
"""
import pytest
from datetime import date, timedelta
from app import db
from app.models import (
    User, Team, LeaveRequest, LeaveBalance, Notification, AuditLog,
    LEAVE_STATUS_PENDING, LEAVE_STATUS_APPROVED, LEAVE_STATUS_REJECTED, LEAVE_STATUS_CANCELLED,
    LEAVE_TYPE_VACATION, LEAVE_TYPE_SICK, LEAVE_TYPE_CASUAL,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_EMPLOYEE
)


def _setup_employee(app, email='emp@test.com', username='emp_user', role=ROLE_EMPLOYEE, team_id=None):
    with app.app_context():
        u = User(
            email=email,
            username=username,
            full_name=username.title(),
            role=role,
            team_id=team_id,
            account_active=True
        )
        u.set_password('pass1234')
        db.session.add(u)
        db.session.commit()
        return u.id


def test_leave_balance_initialization_and_retrieval(client, app):
    emp_id = _setup_employee(app, email='bal_emp@test.com', username='bal_emp')
    client.post('/api/auth/login', json={'email': 'bal_emp@test.com', 'password': 'pass1234'})

    res = client.get('/api/leaves/balance')
    assert res.status_code == 200
    data = res.get_json()['data']
    assert data['annual_total'] == 20.0
    assert data['annual_available'] == 20.0
    assert data['sick_total'] == 10.0
    assert data['sick_available'] == 10.0
    assert data['casual_total'] == 10.0
    assert data['casual_available'] == 10.0


def test_apply_leave_validation(client, app):
    emp_id = _setup_employee(app, email='apply_emp@test.com', username='apply_emp')
    client.post('/api/auth/login', json={'email': 'apply_emp@test.com', 'password': 'pass1234'})

    today = date.today()

    # Invalid leave type
    r = client.post('/api/leaves', json={
        'leave_type': 'holiday',
        'start_date': today.isoformat(),
        'end_date': (today + timedelta(days=2)).isoformat(),
        'reason': 'Trip'
    })
    assert r.status_code == 400
    assert 'Invalid leave type' in r.get_json()['error']

    # End date before start date
    r = client.post('/api/leaves', json={
        'leave_type': 'vacation',
        'start_date': (today + timedelta(days=5)).isoformat(),
        'end_date': (today + timedelta(days=2)).isoformat(),
        'reason': 'Trip'
    })
    assert r.status_code == 400
    assert 'precede' in r.get_json()['error']

    # Missing reason
    r = client.post('/api/leaves', json={
        'leave_type': 'vacation',
        'start_date': today.isoformat(),
        'end_date': (today + timedelta(days=1)).isoformat(),
        'reason': ''
    })
    assert r.status_code == 400
    assert 'reason' in r.get_json()['error']

    # Successful submission
    r = client.post('/api/leaves', json={
        'leave_type': 'vacation',
        'start_date': (today + timedelta(days=10)).isoformat(),
        'end_date': (today + timedelta(days=12)).isoformat(),
        'reason': 'Summer vacation'
    })
    assert r.status_code == 201
    res_data = r.get_json()['data']
    assert res_data['status'] == LEAVE_STATUS_PENDING
    assert res_data['days_count'] == 3.0


def test_prevent_overlapping_leave_applications(client, app):
    emp_id = _setup_employee(app, email='overlap_emp@test.com', username='overlap_emp')
    client.post('/api/auth/login', json={'email': 'overlap_emp@test.com', 'password': 'pass1234'})

    today = date.today()
    # First application: day 10 to 15
    r1 = client.post('/api/leaves', json={
        'leave_type': 'vacation',
        'start_date': (today + timedelta(days=10)).isoformat(),
        'end_date': (today + timedelta(days=15)).isoformat(),
        'reason': 'First leave'
    })
    assert r1.status_code == 201

    # Overlapping application: day 12 to 18
    r2 = client.post('/api/leaves', json={
        'leave_type': 'sick',
        'start_date': (today + timedelta(days=12)).isoformat(),
        'end_date': (today + timedelta(days=18)).isoformat(),
        'reason': 'Second leave'
    })
    assert r2.status_code == 409
    assert 'already have' in r2.get_json()['error']


def test_insufficient_leave_balance(client, app):
    emp_id = _setup_employee(app, email='limit_emp@test.com', username='limit_emp')
    client.post('/api/auth/login', json={'email': 'limit_emp@test.com', 'password': 'pass1234'})

    today = date.today()
    # Attempt 25 days of vacation when limit is 20
    r = client.post('/api/leaves', json={
        'leave_type': 'vacation',
        'start_date': today.isoformat(),
        'end_date': (today + timedelta(days=24)).isoformat(),
        'reason': 'Long sabbatical'
    })
    assert r.status_code == 400
    assert 'Insufficient annual leave balance' in r.get_json()['error']


def test_employee_can_cancel_own_pending_leave(client, app):
    emp_id = _setup_employee(app, email='cancel_emp@test.com', username='cancel_emp')
    client.post('/api/auth/login', json={'email': 'cancel_emp@test.com', 'password': 'pass1234'})

    today = date.today()
    r = client.post('/api/leaves', json={
        'leave_type': 'casual',
        'start_date': (today + timedelta(days=3)).isoformat(),
        'end_date': (today + timedelta(days=4)).isoformat(),
        'reason': 'Personal work'
    })
    leave_id = r.get_json()['data']['id']

    # Cancel pending request
    cancel_res = client.put(f'/api/leaves/{leave_id}/cancel')
    assert cancel_res.status_code == 200
    assert cancel_res.get_json()['data']['status'] == LEAVE_STATUS_CANCELLED

    # Cannot cancel again
    cancel_again = client.put(f'/api/leaves/{leave_id}/cancel')
    assert cancel_again.status_code == 400


def test_employee_cannot_cancel_others_leave(client, app):
    emp_a = _setup_employee(app, email='user_a@test.com', username='user_a')
    emp_b = _setup_employee(app, email='user_b@test.com', username='user_b')

    # User A creates leave
    client.post('/api/auth/login', json={'email': 'user_a@test.com', 'password': 'pass1234'})
    today = date.today()
    r = client.post('/api/leaves', json={
        'leave_type': 'vacation',
        'start_date': (today + timedelta(days=5)).isoformat(),
        'end_date': (today + timedelta(days=6)).isoformat(),
        'reason': 'Trip'
    })
    leave_id = r.get_json()['data']['id']
    client.post('/api/auth/logout')

    # User B logs in and attempts to cancel User A's leave
    client.post('/api/auth/login', json={'email': 'user_b@test.com', 'password': 'pass1234'})
    r_cancel = client.put(f'/api/leaves/{leave_id}/cancel')
    assert r_cancel.status_code == 403


def test_management_authorization_and_review_workflow(client, app):
    with app.app_context():
        # Create team
        t = Team(name='Engineering Team')
        db.session.add(t)
        db.session.commit()
        team_id = t.id

    lead_id = _setup_employee(app, email='lead@test.com', username='lead_eng', role=ROLE_TEAM_LEAD, team_id=team_id)
    emp_id = _setup_employee(app, email='worker@test.com', username='worker_eng', role=ROLE_EMPLOYEE, team_id=team_id)

    # Worker submits leave
    client.post('/api/auth/login', json={'email': 'worker@test.com', 'password': 'pass1234'})
    today = date.today()
    r_apply = client.post('/api/leaves', json={
        'leave_type': 'vacation',
        'start_date': (today + timedelta(days=7)).isoformat(),
        'end_date': (today + timedelta(days=8)).isoformat(),
        'reason': 'Concert'
    })
    leave_id = r_apply.get_json()['data']['id']

    # Worker cannot view pending management queue
    r_pending_emp = client.get('/api/leaves/pending')
    assert r_pending_emp.status_code == 403

    # Worker cannot review
    r_review_emp = client.put(f'/api/leaves/{leave_id}/review', json={'decision': 'approved'})
    assert r_review_emp.status_code == 403

    client.post('/api/auth/logout')

    # Team Lead logs in
    client.post('/api/auth/login', json={'email': 'lead@test.com', 'password': 'pass1234'})
    r_pending = client.get('/api/leaves/pending')
    assert r_pending.status_code == 200
    pending_items = r_pending.get_json()['data']
    assert any(item['id'] == leave_id for item in pending_items)

    # Team Lead approves leave
    r_approve = client.put(f'/api/leaves/{leave_id}/review', json={
        'decision': 'approved',
        'review_notes': 'Have fun at the concert!'
    })
    assert r_approve.status_code == 200
    assert r_approve.get_json()['data']['status'] == LEAVE_STATUS_APPROVED
    assert r_approve.get_json()['data']['review_notes'] == 'Have fun at the concert!'

    # Verify balance was deducted from employee
    with app.app_context():
        bal = LeaveBalance.query.filter_by(user_id=emp_id, year=today.year).first()
        assert bal is not None
        assert bal.annual_used == 2.0
        assert bal.to_dict()['annual_available'] == 18.0

        # Verify notification was sent to employee
        notif = Notification.query.filter_by(user_id=emp_id).first()
        assert notif is not None
        assert 'approved' in notif.title.lower()

        # Verify audit log was recorded
        audit = AuditLog.query.filter_by(entity_type='LeaveRequest', entity_id=leave_id).all()
        assert len(audit) >= 2  # leave_applied and leave_approved


def test_leave_calendar_and_export(client, app):
    admin_id = _setup_employee(app, email='admin_leave@test.com', username='admin_leave', role=ROLE_ADMIN)
    emp_id = _setup_employee(app, email='away_worker@test.com', username='away_worker', role=ROLE_EMPLOYEE)

    today = date.today()
    with app.app_context():
        req = LeaveRequest(
            user_id=emp_id,
            leave_type=LEAVE_TYPE_SICK,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            days_count=2.0,
            reason='Flu recovery',
            status=LEAVE_STATUS_APPROVED
        )
        db.session.add(req)
        db.session.commit()

    client.post('/api/auth/login', json={'email': 'admin_leave@test.com', 'password': 'pass1234'})

    # Calendar endpoint
    r_cal = client.get('/api/leaves/calendar')
    assert r_cal.status_code == 200
    cal_data = r_cal.get_json()['data']
    assert len(cal_data) >= 1
    assert any(c['leave_type'] == 'sick' for c in cal_data)

    # CSV Export
    r_csv = client.get('/api/leaves/export')
    assert r_csv.status_code == 200
    assert r_csv.mimetype == 'text/csv'
    assert b'Flu recovery' in r_csv.data
    assert b'Away_Worker' in r_csv.data
