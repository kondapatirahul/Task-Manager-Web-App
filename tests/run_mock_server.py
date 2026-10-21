"""
Standalone Mock Server for Manual Testing with Postman or Thunder Client.

Usage:
    python tests/run_mock_server.py

Endpoints available:
    GET    http://127.0.0.1:5000/api/tasks
    POST   http://127.0.0.1:5000/api/tasks
    GET    http://127.0.0.1:5000/api/tasks/<id>
    PUT    http://127.0.0.1:5000/api/tasks/<id>
    DELETE http://127.0.0.1:5000/api/tasks/<id>
    PATCH  http://127.0.0.1:5000/api/tasks/<id>/complete

Testing multi-tenancy and authentication via headers:
    - Send header "X-User-Id: 1" to act as User 1 (default)
    - Send header "X-User-Id: 2" to act as User 2 (for cross-user testing)
    - Send header "X-Anonymous: true" to simulate an unauthenticated request (returns 401)
"""

import sys
import os

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, request
from app.api.tasks import tasks_bp, configure_task_api_dependencies
from tests.test_tasks_api import MockTask, MockCategory, MockDB, MockUser

app = Flask(__name__)
mock_db = MockDB()

# Seed initial test data
MockCategory.objects = [
    MockCategory(id=1, name="Work Category", user_id=1),
    MockCategory(id=2, name="Personal Category", user_id=2),
]

MockTask.objects = [
    MockTask(
        id=1,
        title="Setup Postman Collection",
        description="Verify all M4 CRUD endpoints",
        priority="high",
        status="pending",
        user_id=1,
        category_id=1,
    ),
    MockTask(
        id=2,
        title="Secret Task of User 2",
        description="Should return 404 if accessed by User 1",
        priority="low",
        status="pending",
        user_id=2,
        category_id=2,
    ),
]


def dynamic_current_user():
    # Simulate unauthenticated requests
    if request.headers.get("X-Anonymous", "").lower() == "true":
        return None

    # Allow toggling user id via request header
    user_id_str = request.headers.get("X-User-Id", "1")
    try:
        user_id = int(user_id_str)
    except ValueError:
        user_id = 1

    return MockUser(user_id=user_id, username=f"user_{user_id}")


configure_task_api_dependencies(
    db=mock_db,
    Task=MockTask,
    Category=MockCategory,
    get_current_user=dynamic_current_user,
)

app.register_blueprint(tasks_bp)

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  M4 Task API Mock Server Running for Postman / Thunder Client")
    print("  Listening on: http://127.0.0.1:5000")
    print("=" * 65)
    print("  Endpoints:")
    print("    - GET    http://127.0.0.1:5000/api/tasks")
    print("    - POST   http://127.0.0.1:5000/api/tasks")
    print("    - GET    http://127.0.0.1:5000/api/tasks/<id>")
    print("    - PUT    http://127.0.0.1:5000/api/tasks/<id>")
    print("    - DELETE http://127.0.0.1:5000/api/tasks/<id>")
    print("    - PATCH  http://127.0.0.1:5000/api/tasks/<id>/complete")
    print("\n  Headers for testing:")
    print("    - X-User-Id: 1 (default) or 2")
    print("    - X-Anonymous: true (tests 401 Unauthorized)")
    print("=" * 65 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
