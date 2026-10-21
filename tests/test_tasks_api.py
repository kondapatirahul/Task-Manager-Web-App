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
from datetime import date, datetime
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
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
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
        self.created_at = created_at
        self.updated_at = updated_at

    @classmethod
    def query_filter_by(cls, **kwargs: Any) -> "MockQuery":
        return MockQuery(cls.objects, **kwargs)


class MockQuery:
    def __init__(self, dataset: List[Any], **filters: Any):
        self.dataset = [
            item for item in dataset
            if all(getattr(item, k, None) == v for k, v in filters.items())
        ]

    def filter_by(self, **filters: Any) -> "MockQuery":
        filtered = [
            item for item in self.dataset
            if all(getattr(item, k, None) == v for k, v in filters.items())
        ]
        return MockQuery(filtered)

    def filter(self, *criterion: Any) -> "MockQuery":
        filtered = list(self.dataset)
        for c in criterion:
            if callable(c):
                filtered = [item for item in filtered if c(item)]
        return MockQuery(filtered)

    def first(self) -> Optional[Any]:
        return self.dataset[0] if self.dataset else None

    def all(self) -> List[Any]:
        return list(self.dataset)

    def order_by(self, *args: Any) -> "MockQuery":
        dataset = list(self.dataset)
        sort_arg = str(args[0]) if args else "id"

        if "due_date" in sort_arg:
            dataset.sort(
                key=lambda x: (
                    x.due_date is None,
                    x.due_date if x.due_date is not None else date.max,
                    -getattr(x, "id", 0),
                )
            )
        elif "priority" in sort_arg:
            weight = {"high": 1, "medium": 2, "low": 3}
            dataset.sort(
                key=lambda x: (
                    weight.get(str(getattr(x, "priority", "")).lower(), 4),
                    -getattr(x, "id", 0),
                )
            )
        elif "created_at" in sort_arg:
            dataset.sort(
                key=lambda x: (
                    getattr(x, "created_at", None) or datetime.min,
                    getattr(x, "id", 0),
                ),
                reverse=True,
            )
        else:
            dataset.sort(key=lambda x: getattr(x, "id", 0), reverse=True)

        return MockQuery(dataset)


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

    # ------------------------------------------------------------------------
    # 6. Search, Filtering, Sorting, and Query Security Tests
    # ------------------------------------------------------------------------

    def test_search_by_title_and_case_insensitive(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Write Unit Tests for API", description="Test endpoints", user_id=1),
            MockTask(title="Deploy Frontend", description="Deploy to staging", user_id=1),
        ]

        # Case-insensitive title search
        resp = self.client.get("/api/tasks?q=unit")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["title"], "Write Unit Tests for API")

        # Uppercase search
        resp_upper = self.client.get("/api/tasks?q=UNIT")
        self.assertEqual(resp_upper.status_code, 200)
        self.assertEqual(len(resp_upper.get_json()["data"]), 1)

    def test_search_by_description(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Task A", description="Important database schema updates", user_id=1),
            MockTask(title="Task B", description="General styling polish", user_id=1),
        ]

        resp = self.client.get("/api/tasks?q=SCHEMA")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["title"], "Task A")

    def test_search_no_match_returns_empty_list(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Task A", description="Some description", user_id=1),
        ]

        resp = self.client.get("/api/tasks?q=nonexistent_token")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"], [])

    def test_filter_by_status(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Pending Task", status="pending", user_id=1),
            MockTask(title="Completed Task", status="completed", user_id=1),
        ]

        resp_pending = self.client.get("/api/tasks?status=pending")
        self.assertEqual(resp_pending.status_code, 200)
        data_pending = resp_pending.get_json()
        self.assertEqual(len(data_pending["data"]), 1)
        self.assertEqual(data_pending["data"][0]["status"], "pending")

        resp_completed = self.client.get("/api/tasks?status=completed")
        self.assertEqual(resp_completed.status_code, 200)
        data_completed = resp_completed.get_json()
        self.assertEqual(len(data_completed["data"]), 1)
        self.assertEqual(data_completed["data"][0]["status"], "completed")

    def test_filter_by_priority(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Low Task", priority="low", user_id=1),
            MockTask(title="Medium Task", priority="medium", user_id=1),
            MockTask(title="High Task", priority="high", user_id=1),
        ]

        resp = self.client.get("/api/tasks?priority=high")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["priority"], "high")

    def test_filter_by_category_id(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Work Task", category_id=1, user_id=1),
            MockTask(title="Uncategorized Task", category_id=None, user_id=1),
        ]

        resp = self.client.get("/api/tasks?category_id=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["category_id"], 1)

    def test_filter_by_due_before(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Due Early", due_date=date(2026, 10, 20), user_id=1),
            MockTask(title="Due Exact", due_date=date(2026, 10, 25), user_id=1),
            MockTask(title="Due Later", due_date=date(2026, 10, 30), user_id=1),
            MockTask(title="No Due Date", due_date=None, user_id=1),
        ]

        # Tasks due on or before 2026-10-25
        resp = self.client.get("/api/tasks?due_before=2026-10-25")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        titles = [t["title"] for t in data["data"]]
        self.assertIn("Due Early", titles)
        self.assertIn("Due Exact", titles)
        self.assertNotIn("Due Later", titles)
        self.assertNotIn("No Due Date", titles)

    def test_combined_search_and_filters(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(
                title="Prepare Financial Report",
                description="Quarterly review",
                status="pending",
                priority="high",
                category_id=1,
                due_date=date(2026, 10, 25),
                user_id=1,
            ),
            MockTask(
                title="Prepare Financial Summary",
                description="Completed review",
                status="completed",
                priority="high",
                category_id=1,
                due_date=date(2026, 10, 25),
                user_id=1,
            ),
            MockTask(
                title="Prepare HR Report",
                description="Quarterly review",
                status="pending",
                priority="low",
                category_id=1,
                due_date=date(2026, 10, 25),
                user_id=1,
            ),
        ]

        resp = self.client.get(
            "/api/tasks?q=Report&status=pending&priority=high&category_id=1&due_before=2026-10-31"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["title"], "Prepare Financial Report")

    # ------------------------------------------------------------------------
    # Invalid Query Parameter Rejections (Returns 400 Bad Request)
    # ------------------------------------------------------------------------

    def test_invalid_query_parameter_rejections(self) -> None:
        self.current_user = MockUser(user_id=1)

        test_cases = [
            ("/api/tasks?status=in_progress", "Invalid status filter"),
            ("/api/tasks?priority=critical", "Invalid priority filter"),
            ("/api/tasks?category_id=invalid", "category_id must be a positive integer"),
            ("/api/tasks?category_id=-1", "category_id must be a positive integer"),
            ("/api/tasks?due_before=bad-date", "due_before must be a valid date"),
            ("/api/tasks?due_before=2026-99-99", "due_before must be a valid date"),
            ("/api/tasks?sort=title", "Invalid sort parameter"),
            ("/api/tasks?sort=id", "Invalid sort parameter"),
        ]

        for url, expected_error in test_cases:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 400)
                data = resp.get_json()
                self.assertFalse(data["ok"])
                self.assertIn(expected_error, data["error"])

    # ------------------------------------------------------------------------
    # Sorting Tests (due_date, priority, created_at)
    # ------------------------------------------------------------------------

    def test_sort_by_due_date_nulls_last(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="No Due Date", due_date=None, user_id=1, id=1),
            MockTask(title="Due Oct 20", due_date=date(2026, 10, 20), user_id=1, id=2),
            MockTask(title="Due Oct 10", due_date=date(2026, 10, 10), user_id=1, id=3),
        ]

        resp = self.client.get("/api/tasks?sort=due_date")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        titles = [t["title"] for t in data["data"]]
        # Earliest due date first, None at the end
        self.assertEqual(titles, ["Due Oct 10", "Due Oct 20", "No Due Date"])

    def test_sort_by_priority(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Low Task", priority="low", user_id=1, id=1),
            MockTask(title="High Task", priority="high", user_id=1, id=2),
            MockTask(title="Medium Task", priority="medium", user_id=1, id=3),
        ]

        resp = self.client.get("/api/tasks?sort=priority")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        priorities = [t["priority"] for t in data["data"]]
        self.assertEqual(priorities, ["high", "medium", "low"])

    def test_sort_by_created_at(self) -> None:
        self.current_user = MockUser(user_id=1)
        MockTask.objects = [
            MockTask(title="Old Task", created_at=datetime(2026, 10, 1, 10, 0), user_id=1, id=1),
            MockTask(title="New Task", created_at=datetime(2026, 10, 20, 10, 0), user_id=1, id=2),
        ]

        resp = self.client.get("/api/tasks?sort=created_at")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        titles = [t["title"] for t in data["data"]]
        self.assertEqual(titles, ["New Task", "Old Task"])

    # ------------------------------------------------------------------------
    # Security: Multi-Tenant Query Scoping & User-ID Injection Resistance
    # ------------------------------------------------------------------------

    def test_search_and_filters_preserve_cross_user_isolation(self) -> None:
        # User 1 task and User 2 task share same keyword
        MockTask.objects = [
            MockTask(title="User 1 Secret Project", user_id=1),
            MockTask(title="User 2 Secret Blueprint", user_id=2),
        ]

        self.current_user = MockUser(user_id=1)
        resp = self.client.get("/api/tasks?q=Secret")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["title"], "User 1 Secret Project")
        self.assertEqual(data["data"][0]["user_id"], 1)

    def test_filter_by_foreign_category_returns_empty_and_does_not_expose(self) -> None:
        # Category 2 belongs to User 2
        MockTask.objects = [
            MockTask(title="User 2 Task in Category 2", category_id=2, user_id=2),
        ]

        self.current_user = MockUser(user_id=1)
        resp = self.client.get("/api/tasks?category_id=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["data"], [])

    def test_client_supplied_user_id_query_param_is_ignored(self) -> None:
        MockTask.objects = [
            MockTask(title="User 1 Task", user_id=1),
            MockTask(title="User 2 Task", user_id=2),
        ]

        # Authenticated as User 1, but client supplies ?user_id=2
        self.current_user = MockUser(user_id=1)
        resp = self.client.get("/api/tasks?user_id=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["title"], "User 1 Task")
        self.assertEqual(data["data"][0]["user_id"], 1)

    def test_unauthenticated_requests_with_query_params_return_401(self) -> None:
        self.current_user = None
        resp = self.client.get("/api/tasks?q=test&status=pending&sort=priority")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Authentication required")


if __name__ == "__main__":
    unittest.main()
