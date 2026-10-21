from app import create_app, db

def test_csrf_protection_blocks_forged_requests():
    app = create_app({
        'TESTING': False,
        'CSRF_ENABLED': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'csrf-test-secret'
    })

    with app.app_context():
        db.create_all()

    client = app.test_client()

    # Initial GET to establish session and get CSRF token
    get_res = client.get('/login')
    assert get_res.status_code == 200

    # Extract session cookie
    with client.session_transaction() as sess:
        valid_token = sess.get('csrf_token')

    assert valid_token is not None

    # POST request with invalid CSRF token -> should be blocked (403)
    res_bad = client.post('/api/tasks', json={'title': 'Malicious Task'}, headers={
        'X-CSRFToken': 'invalid-token-value'
    })
    assert res_bad.status_code == 403
    assert res_bad.get_json()['ok'] is False
    assert 'Invalid CSRF token' in res_bad.get_json()['error']

    # POST request with valid CSRF token -> should not be rejected for CSRF (may be 401 unauth)
    res_valid_csrf = client.post('/api/tasks', json={'title': 'Legit Task'}, headers={
        'X-CSRFToken': valid_token
    })
    # CSRF passed; rejected by auth instead of CSRF 403
    assert res_valid_csrf.status_code == 401
