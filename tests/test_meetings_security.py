from datetime import datetime, timedelta
from app import db
from app.models import User, Meeting, MeetingAttendee


def _user(username, role='employee', organization_id=None):
    user = User(username=username, full_name=username.title(), email=f'{username}@example.com',
                role=role, organization_id=organization_id)
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/api/auth/login', json={'email': f'{username}@example.com', 'password': 'password123'})


def test_employee_cannot_schedule_meeting(app, client):
    with app.app_context():
        _user('meetingemployee')
    _login(client, 'meetingemployee')
    start = (datetime.now() + timedelta(days=1)).replace(microsecond=0)
    response = client.post('/api/meetings', json={
        'title': 'Private meeting', 'start_time': start.isoformat(),
        'end_time': (start + timedelta(hours=1)).isoformat()
    })
    assert response.status_code == 403


def test_uninvited_user_cannot_rsvp(app, client):
    with app.app_context():
        organizer = _user('meetingorganizer', role='team_lead')
        attendee = _user('meetingattendee')
        start = datetime.now() + timedelta(days=1)
        meeting = Meeting(title='Team meeting', organizer_id=organizer.id,
                          start_time=start, end_time=start + timedelta(hours=1), status='scheduled')
        db.session.add(meeting)
        db.session.commit()
    _login(client, 'meetingattendee')
    response = client.post(f'/api/meetings/{meeting.id}/rsvp', json={'status': 'accepted'})
    assert response.status_code == 403
