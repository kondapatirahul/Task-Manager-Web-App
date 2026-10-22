from datetime import date, timedelta
from app.models import Task, Category
from app import db

def test_task_create_success(auth_client_a):
    res = auth_client_a.post('/api/tasks', json={
        'title': 'Deploy TaskNest app',
        'description': 'Ensure tests pass and database initializes.',
        'priority': 'high',
        'status': 'pending',
        'due_date': '2026-11-01'
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data['ok'] is True
    assert data['data']['title'] == 'Deploy TaskNest app'
    assert data['data']['priority'] == 'high'
    assert data['data']['status'] == 'pending'
    assert data['data']['due_date'] == '2026-11-01'

def test_task_create_validation(auth_client_a):
    # Missing title
    res = auth_client_a.post('/api/tasks', json={'title': ''})
    assert res.status_code == 400
    assert res.get_json()['ok'] is False

    # Invalid priority
    res = auth_client_a.post('/api/tasks', json={
        'title': 'Test Task',
        'priority': 'critical'  # not allowed
    })
    assert res.status_code == 400
    assert res.get_json()['ok'] is False

    # Invalid status
    res = auth_client_a.post('/api/tasks', json={
        'title': 'Test Task',
        'status': 'invalid_status'  # not allowed
    })
    assert res.status_code == 400

def test_task_update(auth_client_a):
    create_res = auth_client_a.post('/api/tasks', json={'title': 'Original Title', 'priority': 'low'})
    task_id = create_res.get_json()['data']['id']

    update_res = auth_client_a.put(f'/api/tasks/{task_id}', json={
        'title': 'Updated Title',
        'priority': 'high',
        'description': 'Now high priority'
    })
    assert update_res.status_code == 200
    assert update_res.get_json()['data']['title'] == 'Updated Title'
    assert update_res.get_json()['data']['priority'] == 'high'

def test_task_delete(auth_client_a):
    create_res = auth_client_a.post('/api/tasks', json={'title': 'To be deleted'})
    task_id = create_res.get_json()['data']['id']

    del_res = auth_client_a.delete(f'/api/tasks/{task_id}')
    assert del_res.status_code == 200

    # Ensure deleted
    get_res = auth_client_a.get(f'/api/tasks/{task_id}')
    assert get_res.status_code == 404

def test_task_complete_and_reopen(auth_client_a):
    create_res = auth_client_a.post('/api/tasks', json={'title': 'Toggle status test'})
    task_id = create_res.get_json()['data']['id']

    # Toggle to complete
    res = auth_client_a.patch(f'/api/tasks/{task_id}/complete')
    assert res.status_code == 200
    data = res.get_json()
    assert data['data']['status'] == 'completed'
    assert data['data']['completed_at'] is not None

    # Toggle to reopen (pending)
    res_reopen = auth_client_a.patch(f'/api/tasks/{task_id}/complete')
    assert res_reopen.status_code == 200
    data_reopen = res_reopen.get_json()
    assert data_reopen['data']['status'] == 'pending'
    assert data_reopen['data']['completed_at'] is None

def test_task_search_and_filters(auth_client_a):
    auth_client_a.post('/api/tasks', json={'title': 'Write documentation', 'priority': 'high', 'status': 'pending'})
    auth_client_a.post('/api/tasks', json={'title': 'Refactor database', 'priority': 'medium', 'status': 'completed'})
    auth_client_a.post('/api/tasks', json={'title': 'Design logo', 'priority': 'low', 'status': 'pending'})

    # Search by title
    res_q = auth_client_a.get('/api/tasks?q=documentation')
    assert res_q.status_code == 200
    tasks = res_q.get_json()['data']
    assert len(tasks) == 1
    assert tasks[0]['title'] == 'Write documentation'

    # Filter by priority
    res_p = auth_client_a.get('/api/tasks?priority=high')
    tasks_p = res_p.get_json()['data']
    assert all(t['priority'] == 'high' for t in tasks_p)

    # Filter by status
    res_s = auth_client_a.get('/api/tasks?status=completed')
    tasks_s = res_s.get_json()['data']
    assert len(tasks_s) == 1
    assert tasks_s[0]['title'] == 'Refactor database'

def test_user_task_isolation(client, user_a, user_b):
    # Log in as User A and create a task
    client.post('/api/auth/login', json={'email': 'usera@example.com', 'password': 'password123'})
    res_a = client.post('/api/tasks', json={'title': "User A Private Task"})
    task_id = res_a.get_json()['data']['id']
    client.post('/api/auth/logout')

    # Log in as User B
    client.post('/api/auth/login', json={'email': 'userb@example.com', 'password': 'password456'})

    # User B tries to view User A's task -> 404
    get_res = client.get(f'/api/tasks/{task_id}')
    assert get_res.status_code == 404

    # User B tries to edit User A's task -> 404
    put_res = client.put(f'/api/tasks/{task_id}', json={'title': 'Hacked Title'})
    assert put_res.status_code == 404

    # User B tries to toggle complete User A's task -> 404
    patch_res = client.patch(f'/api/tasks/{task_id}/complete')
    assert patch_res.status_code == 404

    # User B tries to delete User A's task -> 404
    del_res = client.delete(f'/api/tasks/{task_id}')
    assert del_res.status_code == 404

    # User B's task list should NOT contain User A's task
    list_res = client.get('/api/tasks')
    assert not any(t['id'] == task_id for t in list_res.get_json()['data'])
