from datetime import date, timedelta

def test_stats_metrics_and_overdue_calculation(auth_client_a):
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()

    # 1. Overdue pending task
    auth_client_a.post('/api/tasks', json={
        'title': 'Overdue task',
        'status': 'pending',
        'due_date': yesterday
    })

    # 2. Overdue but completed task -> should NOT count as overdue
    auth_client_a.post('/api/tasks', json={
        'title': 'Completed past task',
        'status': 'completed',
        'due_date': yesterday
    })

    # 3. Future pending task
    auth_client_a.post('/api/tasks', json={
        'title': 'Future task',
        'status': 'pending',
        'due_date': tomorrow
    })

    # 4. Another completed task
    auth_client_a.post('/api/tasks', json={
        'title': 'Another done',
        'status': 'completed'
    })

    # Fetch stats
    res = auth_client_a.get('/api/stats')
    assert res.status_code == 200
    stats = res.get_json()['data']

    assert stats['total'] == 4
    assert stats['pending'] == 2
    assert stats['completed'] == 2
    assert stats['overdue'] == 1  # only the pending task with yesterday's due date
    assert stats['completion_rate'] == 50

def test_stats_unauthenticated(client):
    res = client.get('/api/stats')
    assert res.status_code == 401
    assert res.get_json()['ok'] is False
