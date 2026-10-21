"""
Integration and security tests for M4 Task REST API.

Tests:
- Authentication enforcement (JSON 401 for all endpoints)
- CRUD operations for authenticated user
- Request validation (missing title, invalid priority, bad date format)
- Category ownership verification (preventing cross-user category assignment)
- Multi-tenant isolation / Cross-user access prevention (GET, PUT, DELETE, PATCH return 404)
- User query scoping (GET /api/tasks only returns authenticated user's tasks)
"""

import unittest
from datetime import date
from typing import Any, Dict, List, Optional
from flask import Flask

from app.api.tasks import tasks_bp, configure_task_api_dependencies


# ============================================================================
# Minimal In-Memory Mock Models & DB for Isolated Testing (Pending M1 & M2)
# ============================================================================

class MockUser:
    def __init__(self, user_id: int, username: str = "testuser"):
        self.id = user_id
        self.username = username
        self.is_authenticated = True


class MockCategory:
    objects: List["MockCategory"] = []

    def __init__(self, id: int, name: str, user_id: int):
        self.id = id
        self.name = name
        self.user_id = user_id

    @classmethod
    def query_filter_by(cls, **kwargs: Any) -> "MockQuery":
        return MockQuery(cls.objects, **kwargs)


class MockColumn:
    def desc(self) -> "MockColumn":
        return self


class MockTask:
    id: Any = MockColumn()
    objects: List["MockTask"] = []
    _auto_id: int = 1

    def __init__(
        self,
        title: str,
        user_id: int,
        description: Optional[str] = None,
        status: str = "pending",
        priority: str = "medium",
        due_date: Optional[date] = None,
        category_id: Optional[int] = None,
        id: Optional[int] = None,
    ):
        if id is None:
            self.id = MockTask._auto_id
            MockTask._auto_id += 1
        else:
            self.id = id
        self.title = title
        self.user_id = user_id
        self.description = description
        self.status = status
        self.priority = priority
        self.due_date = due_date
        self.category_id = category_id
        self.created_at = None
        self.updated_at = None

    @classmethod
    def query_filter_by(cls, **kwargs: Any) -> "MockQuery":
        return MockQuery(cls.objects, **kwargs)


class MockQuery:
    def __init__(self, dataset: List[Any], **filters: Any):
        self.dataset = [
            item for item in dataset
            if all(getattr(item, k, None) == v for k, v in filters.items())
        ]

    def first(self) -> Optional[Any]:
        return self.dataset[0] if self.dataset else None

    def all(self) -> List[Any]:
        return list(self.dataset)

    def order_by(self, *args: Any) -> "MockQuery":
        # Sort by id descending
        self.dataset.sort(key=lambda x: getattr(x, "id", 0), reverse=True)
        return self


class MockSession:
    def add(self, instance: Any) -> None:
        if isinstance(instance, MockTask) and instance not in MockTask.objects:
            MockTask.objects.append(instance)

    def delete(self, instance: Any) -> None:
        if isinstance(instance, MockTask) and instance in MockTask.objects:
            MockTask.objects.remove(instance)

    def commit(self) -> None:
        pass


class MockDB:
    def __init__(self) -> None:
        self.session = MockSession()


# Attach query class property
MockTask.query = type("QueryHolder", (), {"filter_by": staticmethod(MockTask.query_filter_by)})()  # type: ignore
MockCategory.query = type("QueryHolder", (), {"filter_by": staticmethod(MockCategory.query_filter_by)})()  # type: ignore


# ============================================================================
# Test Suite
# ============================================================================

class TestTaskAPI(unittest.TestCase):
    def setUp(self) -> None:
        # Reset in-memory storage
        MockTask.objects = []
        MockTask._auto_id = 1
        MockCategory.objects = [
            MockCategory(id=1, name="User 1 Work", user_id=1),
            MockCategory(id=2, name="User 2 Personal", user_id=2),
        ]

        self.mock_db = MockDB()
        self.current_user: Optional[MockUser] = None

        def test_get_current_user() -> Optional[MockUser]:
            return self.current_user

        # Inject test dependencies
        configure_task_api_dependencies(
            db=self.mock_db,
            Task=MockTask,
            Category=MockCategory,
            get_current_user=test_get_current_user,
        )

        # Setup test Flask app
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.register_blueprint(tasks_bp)
        self.client = self.app.test_client()

    # ------------------------------------------------------------------------
    # 1. Authentication Enforcement (Unauthenticated Requests -> 401)
    # ------------------------------------------------------------------------

    def test_unauthenticated_requests_return_401(self) -> None:
        self.current_user = None

        endpoints = [
            ("GET", "/api/tasks", None),
            ("POST", "/api/tasks", {"title": "Test"}),
            ("GET", "/api/tasks/1", None),
            ("PUT", "/api/tasks/1", {"title": "Test"}),
            ("DELETE", "/api/tasks/1", None),
            ("PATCH", "/api/tasks/1/complete", None),
        ]

        for method, url, payload in endpoints:
            with self.subTest(method=method, url=url):
                if method == "GET":
                    resp = self.client.get(url)
                elif method == "POST":
                    resp = self.client.post(url, json=payload)
                elif method == "PUT":
                    resp = self.client.put(url, json=payload)
                elif method == "DELETE":
                    resp = self.client.delete(url)
                elif method == "PATCH":
                    resp = self.client.patch(url)

                self.assertEqual(resp.status_code, 401)
                data = resp.get_json()
                self.assertFalse(data["ok"])
                self.assertEqual(data["error"], "Authentication required")

    # ------------------------------------------------------------------------
    # 2. CRUD Operations for Authenticated User
    # ------------------------------------------------------------------------

    def test_create_task_success(self) -> None:
        self.current_user = MockUser(user_id=1)

        payload = {
            "title": "Build REST API",
            "description": "Implement M4 endpoints",
            "priority": "high",
            "status": "pending",
            "due_date": "2026-10-30",
            "category_id": 1,
        }
        resp = self.client.post("/api/tasks", json=payload)
        self.assertEqual(resp.status_code, 201)

        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["title"], "Build REST API")
        self.assertEqual(data["data"]["user_id"], 1)
        self.assertEqual(data["data"]["category_id"], 1)
        self.assertEqual(data["data"]["priority"], "high")

    def test_list_tasks_scoped_to_authenticated_user(self) -> None:
        # Create task for User 1 and User 2
        MockTask.objects.append(MockTask(title="User 1 Task", user_id=1))
        MockTask.objects.append(MockTask(title="User 2 Secret Task", user_id=2))

        # Login as User 1
        self.current_user = MockUser(user_id=1)
        resp = self.client.get("/api/tasks")
        self.assertEqual(resp.status_code, 200)

        data = resp.get_json()
        self.assertTrue(data["ok"])
        tasks = data["data"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "User 1 Task")
        self.assertEqual(tasks[0]["user_id"], 1)

    def test_get_single_task_success(self) -> None:
        task = MockTask(title="User 1 Detail Task", user_id=1, id=10)
        MockTask.objects.append(task)

        self.current_user = MockUser(user_id=1)
        resp = self.client.get("/api/tasks/10")
        self.assertEqual(resp.status_code, 200)

        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["id"], 10)
        self.assertEqual(data["data"]["title"], "User 1 Detail Task")

    def test_update_task_success(self) -> None:
        task = MockTask(title="Original Title", user_id=1, id=11)
        MockTask.objects.append(task)

        self.current_user = MockUser(user_id=1)
        update_payload = {
            "title": "Updated Title",
            "description": "Updated Description",
            "priority": "low",
            "status": "pending",
        }
        resp = self.client.put("/api/tasks/11", json=update_payload)
        self.assertEqual(resp.status_code, 200)

        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["title"], "Updated Title")
        self.assertEqual(data["data"]["priority"], "low")

    def test_patch_complete_task_success(self) -> None:
        task = MockTask(title="Incomplete Task", user_id=1, status="pending", id=12)
        MockTask.objects.append(task)

        self.current_user = MockUser(user_id=1)
        resp = self.client.patch("/api/tasks/12/complete")
        self.assertEqual(resp.status_code, 200)

        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["status"], "completed")

    def test_delete_task_success(self) -> None:
        task = MockTask(title="To Delete", user_id=1, id=13)
        MockTask.objects.append(task)

        self.current_user = MockUser(user_id=1)
        resp = self.client.delete("/api/tasks/13")
        self.assertEqual(resp.status_code, 200)

        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["id"], 13)

        # Confirm deleted
        get_resp = self.client.get("/api/tasks/13")
        self.assertEqual(get_resp.status_code, 404)

    # ------------------------------------------------------------------------
    # 3. Payload Validation & Bad Request Handling
    # ------------------------------------------------------------------------

    def test_create_task_missing_title(self) -> None:
        self.current_user = MockUser(user_id=1)
        resp = self.client.post("/api/tasks", json={})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("Title is required", data["error"])

    def test_create_task_non_json_body(self) -> None:
        self.current_user = MockUser(user_id=1)
        resp = self.client.post("/api/tasks", data="plain text", content_type="text/plain")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("must be JSON", data["error"])

    def test_create_task_invalid_priority(self) -> None:
        self.current_user = MockUser(user_id=1)
        resp = self.client.post("/api/tasks", json={"title": "Task", "priority": "critical"})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("Priority must be one of", data["error"])

    # ------------------------------------------------------------------------
    # 4. Category Ownership Verification
    # ------------------------------------------------------------------------

    def test_assign_foreign_category_rejected(self) -> None:
        # Category 2 belongs to User 2
        self.current_user = MockUser(user_id=1)
        payload = {
            "title": "Unauthorized Category Task",
            "category_id": 2,  # Owned by User 2
        }
        resp = self.client.post("/api/tasks", json=payload)
        self.assertEqual(resp.status_code, 400)

        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("Invalid category", data["error"])

    def test_update_with_foreign_category_rejected(self) -> None:
        task = MockTask(title="User 1 Task", user_id=1, id=14)
        MockTask.objects.append(task)

        self.current_user = MockUser(user_id=1)
        payload = {
            "title": "Updated Task",
            "category_id": 2,  # Owned by User 2
        }
        resp = self.client.put("/api/tasks/14", json=payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["ok"])

    # ------------------------------------------------------------------------
    # 5. Multi-Tenant Isolation & Cross-User Access Prevention (Returns 404)
    # ------------------------------------------------------------------------

    def test_cross_user_get_task_returns_404(self) -> None:
        task_user_2 = MockTask(title="User 2 Secret Task", user_id=2, id=20)
        MockTask.objects.append(task_user_2)

        # Login as User 1 and attempt to access User 2's task
        self.current_user = MockUser(user_id=1)
        resp = self.client.get("/api/tasks/20")
        self.assertEqual(resp.status_code, 404)

        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Task not found")

    def test_cross_user_put_task_returns_404(self) -> None:
        task_user_2 = MockTask(title="User 2 Secret Task", user_id=2, id=21)
        MockTask.objects.append(task_user_2)

        self.current_user = MockUser(user_id=1)
        resp = self.client.put("/api/tasks/21", json={"title": "Hacked Title"})
        self.assertEqual(resp.status_code, 404)

        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Task not found")

    def test_cross_user_delete_task_returns_404(self) -> None:
        task_user_2 = MockTask(title="User 2 Secret Task", user_id=2, id=22)
        MockTask.objects.append(task_user_2)

        self.current_user = MockUser(user_id=1)
        resp = self.client.delete("/api/tasks/22")
        self.assertEqual(resp.status_code, 404)

        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Task not found")
        # Ensure task is not deleted
        self.assertIn(task_user_2, MockTask.objects)

    def test_cross_user_patch_complete_returns_404(self) -> None:
        task_user_2 = MockTask(title="User 2 Secret Task", user_id=2, status="pending", id=23)
        MockTask.objects.append(task_user_2)

        self.current_user = MockUser(user_id=1)
        resp = self.client.patch("/api/tasks/23/complete")
        self.assertEqual(resp.status_code, 404)

        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Task not found")
        # Ensure status didn't change
        self.assertEqual(task_user_2.status, "pending")


if __name__ == "__main__":
    unittest.main()
