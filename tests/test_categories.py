def test_category_create_and_list(auth_client_a):
    res = auth_client_a.post('/api/categories', json={'name': 'DevOps'})
    assert res.status_code == 201
    assert res.get_json()['data']['name'] == 'DevOps'

    list_res = auth_client_a.get('/api/categories')
    assert list_res.status_code == 200
    names = [c['name'] for c in list_res.get_json()['data']]
    assert 'DevOps' in names

def test_category_duplicate_name(auth_client_a):
    auth_client_a.post('/api/categories', json={'name': 'Finance'})
    dup_res = auth_client_a.post('/api/categories', json={'name': 'Finance'})
    assert dup_res.status_code == 409
    assert dup_res.get_json()['ok'] is False

def test_safe_category_deletion(auth_client_a):
    # 1. Create a category
    cat_res = auth_client_a.post('/api/categories', json={'name': 'Temporary Category'})
    cat_id = cat_res.get_json()['data']['id']

    # 2. Create a task assigned to this category
    task_res = auth_client_a.post('/api/tasks', json={
        'title': 'Task in temp category',
        'category_id': cat_id
    })
    task_id = task_res.get_json()['data']['id']

    # 3. Delete the category
    del_res = auth_client_a.delete(f'/api/categories/{cat_id}')
    assert del_res.status_code == 200

    # 4. Verify task still exists and its category_id is now None
    get_task_res = auth_client_a.get(f'/api/tasks/{task_id}')
    assert get_task_res.status_code == 200
    task_data = get_task_res.get_json()['data']
    assert task_data['title'] == 'Task in temp category'
    assert task_data['category_id'] is None

def test_category_user_isolation(client, user_a, user_b):
    # User A creates a category
    client.post('/api/auth/login', json={'email': 'usera@example.com', 'password': 'password123'})
    res_a = client.post('/api/categories', json={'name': "User A's Secret Category"})
    cat_id = res_a.get_json()['data']['id']
    client.post('/api/auth/logout')

    # User B logs in
    client.post('/api/auth/login', json={'email': 'userb@example.com', 'password': 'password456'})

    # User B cannot see User A's category
    list_res = client.get('/api/categories')
    assert not any(c['id'] == cat_id for c in list_res.get_json()['data'])

    # User B cannot delete User A's category
    del_res = client.delete(f'/api/categories/{cat_id}')
    assert del_res.status_code == 404
