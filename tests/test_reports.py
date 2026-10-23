from datetime import date, datetime, timedelta

from app import db
from app.models import Attendance, Task, User


def _add_task(user_id, title, status, priority='medium', due_date=None, completed_at=None, assignee_id=None):
    task = Task(
        title=title,
        user_id=user_id,
        assignee_id=assignee_id,
        status=status,
        priority=priority,
        due_date=due_date,
        completed_at=completed_at,
    )
    db.session.add(task)
    return task


def test_productivity_report_uses_task_records_and_selected_range(auth_client_a, app, user_a, user_b):
    today = date.today()
    with app.app_context():
        _add_task(
            user_a, 'On-time completion', 'completed', 'medium',
            due_date=today, completed_at=datetime.combine(today, datetime.min.time()),
        )
        _add_task(
            user_a, 'Late completion', 'completed', 'high',
            due_date=today - timedelta(days=3),
            completed_at=datetime.combine(today - timedelta(days=2), datetime.min.time()),
        )
        _add_task(
            user_a, 'Older completion', 'completed', 'low',
            completed_at=datetime.combine(today - timedelta(days=8), datetime.min.time()),
        )
        _add_task(
            user_a, 'Overdue incomplete', 'pending', 'urgent',
            due_date=today - timedelta(days=1),
        )
        _add_task(user_a, 'Blocked item', 'blocked', 'low')
        _add_task(user_b, 'Other user task', 'pending', 'high')
        db.session.commit()

    response = auth_client_a.get('/api/reports/productivity?range_days=7')
    assert response.status_code == 200
    result = response.get_json()
    assert result['ok'] is True
    data = result['data']
    assert data['range_days'] == 7
    assert data['start_date'] == (today - timedelta(days=6)).isoformat()
    assert data['end_date'] == today.isoformat()
    assert data['metrics'] == {
        'total_tasks': 5,
        'completed_tasks': 2,
        'overdue_incomplete_tasks': 1,
        'blocked_tasks': 1,
        'on_time_rate': 50.0,
    }
    assert len(data['completion_trends']) == 7
    assert sum(day['completed_count'] for day in data['completion_trends']) == 2
    assert data['completion_trends'][-1]['completed_count'] == 1
    assert data['status_distribution']['completed'] == 3
    assert data['status_distribution']['blocked'] == 1
    assert data['priority_distribution']['urgent'] == 1

    for days in (14, 30, 90):
        range_response = auth_client_a.get(f'/api/reports/productivity?range_days={days}')
        assert range_response.status_code == 200
        range_data = range_response.get_json()['data']
        assert range_data['range_days'] == days
        assert len(range_data['completion_trends']) == days


def test_productivity_report_rejects_invalid_range(auth_client_a):
    response = auth_client_a.get('/api/reports/productivity?range_days=recent')
    assert response.status_code == 400
    assert response.get_json()['ok'] is False


def test_productivity_report_returns_empty_state_without_tasks(auth_client_a):
    response = auth_client_a.get('/api/reports/productivity?range_days=7')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['metrics']['total_tasks'] == 0
    assert data['metrics']['completed_tasks'] == 0
    assert data['metrics']['on_time_rate'] == 0.0
    assert [
        (day['date'], day['completed_count'])
        for day in data['completion_trends']
    ] == [
        ((date.today() - timedelta(days=offset)).isoformat(), 0)
        for offset in range(6, -1, -1)
    ]
    assert data['status_distribution'] == {}
    assert data['priority_distribution'] == {}


def test_management_workload_and_csv_exports_remain_available(client, app, user_a, user_b):
    with app.app_context():
        user = db.session.get(User, user_a)
        user.role = 'admin'
        db.session.add(Attendance(user_id=user_a, status='completed', duration_minutes=60))
        _add_task(user_a, 'Active assignment', 'in_progress', assignee_id=user_b)
        _add_task(
            user_a,
            'Completed assignment',
            'completed',
            completed_at=datetime.combine(date.today(), datetime.min.time()),
        )
        db.session.commit()

    login = client.post('/api/auth/login', json={
        'email': 'usera@example.com',
        'password': 'password123',
    })
    assert login.status_code == 200

    report = client.get('/api/reports/productivity?range_days=7').get_json()['data']
    workload_by_user = {item['user_id']: item for item in report['workload_distribution']}
    assert workload_by_user[user_b]['active_tasks'] == 1
    assert workload_by_user[user_a]['completed_tasks'] == 1

    tasks_csv = client.get('/api/reports/export/tasks')
    assert tasks_csv.status_code == 200
    assert tasks_csv.mimetype == 'text/csv'
    assert b'Active assignment' in tasks_csv.data

    attendance_csv = client.get('/api/reports/export/attendance')
    assert attendance_csv.status_code == 200
    assert attendance_csv.mimetype == 'text/csv'
    assert b'Employee Name' in attendance_csv.data
