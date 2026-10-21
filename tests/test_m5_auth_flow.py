import unittest
from app import create_app, db
from app.models import User

class TaskNestM5AuthTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # 1. Page Template Rendering Tests
    def test_signup_page_renders_200(self):
        res = self.client.get('/signup')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Create your account', res.data)
        self.assertIn(b'signupForm', res.data)
        self.assertIn(b'username', res.data)
        self.assertIn(b'email', res.data)
        self.assertIn(b'password', res.data)
        self.assertIn(b'confirmPassword', res.data)
        self.assertIn(b'terms', res.data)

    def test_login_page_renders_200(self):
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Welcome back', res.data)
        self.assertIn(b'loginForm', res.data)
        self.assertIn(b'email', res.data)
        self.assertIn(b'password', res.data)

    def test_landing_page_renders_200(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'TaskNest', res.data)
        self.assertIn(b'Organize Today', res.data)

    # 2. Private Page Protection Tests
    def test_unauthenticated_dashboard_redirects_to_login(self):
        res = self.client.get('/dashboard')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

    def test_unauthenticated_tasks_redirects_to_login(self):
        res = self.client.get('/tasks')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

    # 3. Registration API Integration
    def test_registration_success(self):
        payload = {
            'username': 'Alex Taylor',
            'email': 'alex@example.com',
            'password': 'password123'
        }
        res = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data.get('message'), 'User created')

        with self.app.app_context():
            user = User.query.filter_by(email='alex@example.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, 'Alex Taylor')

    def test_registration_duplicate_email_returns_409(self):
        payload = {
            'username': 'Alex Taylor',
            'email': 'alex@example.com',
            'password': 'password123'
        }
        self.client.post('/api/auth/register', json=payload)
        res_dup = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(res_dup.status_code, 409)
        data = res_dup.get_json()
        self.assertIn('Email already registered', data.get('error', ''))

    # 4. Login API Integration
    def test_login_invalid_credentials_returns_401(self):
        payload = {'email': 'unknown@example.com', 'password': 'wrongpassword'}
        res = self.client.post('/api/auth/login', json=payload)
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn('Invalid credentials', data.get('error', ''))

    def test_login_success_and_session_flow(self):
        # Register user
        reg_payload = {
            'username': 'Alex Taylor',
            'email': 'alex@example.com',
            'password': 'password123'
        }
        self.client.post('/api/auth/register', json=reg_payload)

        # Login
        login_payload = {
            'email': 'alex@example.com',
            'password': 'password123'
        }
        res = self.client.post('/api/auth/login', json=login_payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('message'), 'Logged in')
        self.assertEqual(data['user']['username'], 'Alex Taylor')

        # Now access protected page /dashboard
        dash_res = self.client.get('/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b'Alex Taylor', dash_res.data)

        # Access /tasks
        tasks_res = self.client.get('/tasks')
        self.assertEqual(tasks_res.status_code, 200)

        # Logout
        logout_res = self.client.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)

        # Confirm session invalidated: /dashboard redirects to /login
        after_logout_res = self.client.get('/dashboard')
        self.assertEqual(after_logout_res.status_code, 302)
        self.assertIn('/login', after_logout_res.headers['Location'])

    # 5. Team API Preserved and Protected
    def test_team_api_endpoints_functional(self):
        # Unauthenticated calls should be 401
        res_unauth = self.client.get('/api/tasks')
        self.assertEqual(res_unauth.status_code, 401)

        # Register and login to test authenticated API
        reg = self.client.post('/api/auth/register', json={
            'username': 'API User',
            'email': 'api@example.com',
            'password': 'password123'
        })
        self.assertEqual(reg.status_code, 201)
        self.client.post('/api/auth/login', json={
            'email': 'api@example.com',
            'password': 'password123'
        })

        res_tasks = self.client.get('/api/tasks')
        self.assertEqual(res_tasks.status_code, 200)
        self.assertIsInstance(res_tasks.get_json(), list)

        res_categories = self.client.get('/api/categories')
        self.assertIn(res_categories.status_code, [200, 401])

        res_stats = self.client.get('/api/stats')
        self.assertEqual(res_stats.status_code, 200)

if __name__ == '__main__':
    unittest.main()
