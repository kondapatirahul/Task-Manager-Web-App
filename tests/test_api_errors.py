import pytest

from app import create_app, db


@pytest.fixture
def client():
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
    })

    @app.get('/api/test-error')
    def raise_error():
        raise RuntimeError('password=private secret-key=private')

    with app.app_context():
        db.drop_all()
        db.create_all()

    with app.test_client() as test_client:
        test_client.post('/api/auth/register', json={
            'username': 'error-test-user',
            'email': 'errors@example.com',
            'password': 'not-a-secret-to-return',
        })
        test_client.post('/api/auth/login', json={
            'email': 'errors@example.com',
            'password': 'not-a-secret-to-return',
        })
        yield test_client

    with app.app_context():
        db.session.remove()
        db.drop_all()


def assert_json_error(response, status, message=None):
    assert response.status_code == status
    assert response.is_json
    body = response.get_json()
    assert 'error' in body
    if message:
        err = body.get('error', '')
        assert (message.lower() in err.lower()) or (err.lower() in message.lower())


@pytest.mark.parametrize('method,path', [
    ('get', '/api/missing'),
    ('get', '/api/tasks/not-an-id'),
    ('put', '/api/tasks/0'),
    ('get', '/api/categories/not-an-id'),
])
def test_api_not_found_responses_are_json(client, method, path):
    response = getattr(client, method)(path, json={})

    assert_json_error(response, 404, 'Not Found')


def test_unsupported_method_returns_json_405(client):
    response = client.patch('/api/tasks')

    assert_json_error(response, 405, 'Method Not Allowed')
    assert 'Allow' in response.headers


@pytest.mark.parametrize('path', ['/api/tasks', '/api/categories'])
def test_mutations_reject_missing_or_malformed_json(client, path):
    res1 = client.post(path)
    assert res1.status_code in (400, 415)
    assert res1.is_json

    response = client.post(
        path,
        data='{"invalid"',
        content_type='application/json',
    )
    assert response.status_code == 400
    assert response.is_json

    res3 = client.post(path, json=[])
    assert res3.status_code == 400
    assert res3.is_json

@pytest.mark.parametrize('path', ['/api/auth/register', '/api/auth/login'])
def test_auth_mutations_reject_unsupported_content_type(client, path):
    res = client.post(path, data={'unexpected': 'form'})
    assert res.status_code in (400, 415)
    assert res.is_json


def test_task_validation_returns_safe_field_errors(client):
    assert_json_error(
        client.post('/api/tasks', json={}),
        400,
        'Title is required',
    )
    assert_json_error(
        client.post('/api/tasks', json={'title': 'Report', 'status': 'unknown'}),
        400,
        'Invalid status',
    )
    assert_json_error(
        client.post('/api/tasks', json={'title': 'Report', 'category_id': 999}),
        404,
        'Category not found',
    )


def test_category_validation_returns_safe_field_errors(client):
    assert_json_error(
        client.post('/api/categories', json={}),
        400,
        'Category name is required',
    )


def test_missing_or_inaccessible_resources_return_json_404(client):
    response = client.put('/api/tasks/999', json={'title': 'Updated'})
    assert_json_error(response, 404, 'Not Found')

    response = client.delete('/api/categories/999')
    assert_json_error(response, 404, 'Not Found')

def test_invalid_task_update_does_not_partially_change_the_task(client):
    create_response = client.post('/api/tasks', json={'title': 'Original'})
    body = create_response.get_json()
    task_id = body.get('data', {}).get('id') if 'data' in body else body.get('id')

    response = client.put(f'/api/tasks/{task_id}', json={
        'title': 'Changed',
        'status': 'invalid',
    })
    assert_json_error(response, 400, 'Invalid status')

    tasks_response = client.get('/api/tasks')
    tasks_body = tasks_response.get_json()
    tasks_list = tasks_body.get('data', tasks_body)
    assert tasks_list[0]['title'] == 'Original'


def test_unexpected_api_errors_do_not_expose_details(client):
    response = client.get('/api/test-error')
    assert_json_error(response, 500, 'Internal server error')
    assert b'password' not in response.data
    assert b'secret-key' not in response.data
    assert b'Traceback' not in response.data
