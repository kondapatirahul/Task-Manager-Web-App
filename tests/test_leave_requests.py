from datetime import date, timedelta
from app import db
from app.models import User, Team, LeaveRequest


def _make_user(username, role='employee', org=None, team=None, manager=None):
    user = User(username=username, full_name=username.title(), email=f'{username}@example.com', role=role,
                organization_id=org, team_id=team, manager_id=manager)
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/api/auth/login', json={'email': f'{username}@example.com', 'password': 'password123'})


def test_employee_can_submit_leave_and_view_balance(app, client):
    with app.app_context():
        employee = _make_user('leaveemployee')
        employee_id = employee.id
    _login(client, 'leaveemployee')
    start = (date.today() + timedelta(days=3)).isoformat()
    end = (date.today() + timedelta(days=4)).isoformat()
    response = client.post('/api/leaves', json={'leave_type':'casual','start_date':start,'end_date':end,'reason':'Family event'})
    assert response.status_code == 201
    assert response.get_json()['data']['status'] == 'pending'
    history = client.get('/api/leaves').get_json()['data']
    assert len(history['requests']) == 1
    assert history['balances'][0]['allowance'] == 12


def test_leave_rejects_overlapping_requests(app, client):
    with app.app_context():
        _make_user('overlapemployee')
    _login(client, 'overlapemployee')
    start = (date.today() + timedelta(days=5)).isoformat()
    end = (date.today() + timedelta(days=6)).isoformat()
    first = client.post('/api/leaves', json={'leave_type':'sick','start_date':start,'end_date':end,'reason':'Medical'})
    second = client.post('/api/leaves', json={'leave_type':'personal','start_date':start,'end_date':end,'reason':'Personal'})
    assert first.status_code == 201
    assert second.status_code == 409


def test_reject_requires_comment_and_reviewer_scope(app, client):
    with app.app_context():
        org = None
        lead = _make_user('leadscope', role='team_lead', org=org)
        employee = _make_user('employeescope', manager=lead.id)
        outsider = _make_user('outsidescope', role='team_lead')
        req = LeaveRequest(user_id=employee.id, leave_type='casual', start_date=date.today()+timedelta(days=8),
                           end_date=date.today()+timedelta(days=8), days=1, reason='Test')
        db.session.add(req); db.session.commit(); req_id=req.id
    _login(client, 'outsidescope')
    denied = client.post(f'/api/leaves/{req_id}/decision', json={'status':'approved'})
    assert denied.status_code == 403
    client.post('/api/auth/logout')
    _login(client, 'leadscope')
    no_comment = client.post(f'/api/leaves/{req_id}/decision', json={'status':'rejected','comment':' '})
    assert no_comment.status_code == 400
    accepted = client.post(f'/api/leaves/{req_id}/decision', json={'status':'rejected','comment':'Coverage unavailable'})
    assert accepted.status_code == 200
    assert accepted.get_json()['data']['status'] == 'rejected'
