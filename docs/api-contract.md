# TaskNest API Contract

Base URL: `/api`

All API endpoints return JSON in a standardized envelope format:

### Success Response Envelope
```json
{
  "ok": true,
  "data": { ... },
  "message": "Optional human-readable confirmation message"
}
```

### Error Response Envelope
```json
{
  "ok": false,
  "error": "Human-readable error message"
}
```

---

## 1. Authentication (`/api/auth`)

| Method | Endpoint | Description | Request Body | Success Response | Error Codes |
|--------|----------|-------------|--------------|------------------|-------------|
| `POST` | `/api/auth/signup` | Register a new user | `{"email": "...", "password": "...", "full_name": "...", "username": "..."}` | `201 { "ok": true, "data": User, "message": "User registered successfully" }` | `400`, `409` |
| `POST` | `/api/auth/login` | Authenticate user & start session | `{"email": "...", "password": "...", "remember": true/false}` | `200 { "ok": true, "data": User, "message": "Logged in successfully" }` | `400`, `401` |
| `POST` | `/api/auth/logout` | Terminate session & log out | — | `200 { "ok": true, "message": "Logged out successfully" }` | `401` |
| `GET` | `/api/auth/me` | Retrieve authenticated user profile | — | `200 { "ok": true, "data": User }` | `401` |

> Note: `/api/auth/register` is supported as an alias for `/api/auth/signup`.

---

## 2. Tasks (`/api/tasks`)

| Method | Endpoint | Description | Query Parameters / Body | Success Response | Error Codes |
|--------|----------|-------------|-------------------------|------------------|-------------|
| `GET` | `/api/tasks` | List user tasks with optional filters | `q`, `status`, `priority`, `category_id`, `due_before`, `due_after`, `sort` | `200 { "ok": true, "data": [Task, ...] }` | `401` |
| `POST` | `/api/tasks` | Create a new task | `{"title": "...", "description": "...", "priority": "...", "status": "...", "due_date": "YYYY-MM-DD", "category_id": 1}` | `201 { "ok": true, "data": Task, "message": "Task created successfully" }` | `400`, `401`, `404` |
| `GET` | `/api/tasks/<id>` | Retrieve a single task by ID | — | `200 { "ok": true, "data": Task }` | `401`, `404` |
| `PUT` | `/api/tasks/<id>` | Update an existing task | `{"title": "...", "description": "...", "priority": "...", "status": "...", "due_date": "YYYY-MM-DD", "category_id": 1}` | `200 { "ok": true, "data": Task, "message": "Task updated successfully" }` | `400`, `401`, `404` |
| `DELETE` | `/api/tasks/<id>` | Delete a task | — | `200 { "ok": true, "message": "Task deleted successfully" }` | `401`, `404` |
| `PATCH` | `/api/tasks/<id>/complete` | Toggle or set task completion | `{"status": "completed"}` *(optional body)* | `200 { "ok": true, "data": Task, "message": "Task status updated" }` | `400`, `401`, `404` |

### Task Query Parameters:
- `q`: Full-text substring search across `title` and `description`.
- `status`: Allowed values: `pending`, `completed`.
- `priority`: Allowed values: `low`, `medium`, `high`.
- `category_id`: Integer ID of a category belonging to current user.
- `due_before`: ISO Date string `YYYY-MM-DD`.
- `due_after`: ISO Date string `YYYY-MM-DD`.
- `sort`: Supported allowlist: `due_date_asc`, `due_date_desc`, `created_at_desc` (default), `created_at_asc`, `priority_desc`, `priority_asc`, `title_asc`.

---

## 3. Categories (`/api/categories`)

| Method | Endpoint | Description | Request Body | Success Response | Error Codes |
|--------|----------|-------------|--------------|------------------|-------------|
| `GET` | `/api/categories` | List current user's categories | — | `200 { "ok": true, "data": [Category, ...] }` | `401` |
| `POST` | `/api/categories` | Create a new category | `{"name": "..."}` | `201 { "ok": true, "data": Category, "message": "Category created successfully" }` | `400`, `401`, `409` |
| `DELETE` | `/api/categories/<id>` | Safely delete category (unassigns associated tasks) | — | `200 { "ok": true, "message": "Category deleted and associated tasks unassigned successfully" }` | `401`, `404` |

---

## 4. Statistics (`/api/stats`)

| Method | Endpoint | Description | Success Response | Error Codes |
|--------|----------|-------------|------------------|-------------|
| `GET` | `/api/stats` | Real-time task statistics & counts | `200 { "ok": true, "data": Stats }` | `401` |

### Stats Data Model:
```json
{
  "total": 12,
  "pending": 8,
  "completed": 4,
  "overdue": 1,
  "due_today": 2,
  "high_priority": 3,
  "completion_rate": 33,
  "by_category": [
    { "id": 1, "name": "Work", "total": 6, "pending": 4 }
  ],
  "upcoming": [ ... ]
}
```
*Note: Overdue tasks are strictly defined as pending tasks whose `due_date` is earlier than today's local date.*

## 5. Reports (`/api/reports`)

| Method | Endpoint | Description | Query Parameters | Success Response | Error Codes |
|--------|----------|-------------|------------------|------------------|-------------|
| `GET` | `/api/reports/productivity` | Productivity metrics, daily completion counts, status/priority distributions, and management workload | `range_days` (7–90; defaults to 30; legacy alias: `days`) | `200 { "ok": true, "data": ProductivityReport }` | `400`, `401`, `403` |
| `GET` | `/api/reports/export/tasks` | Download task data as CSV | — | `200 text/csv` | `401`, `403` |
| `GET` | `/api/reports/export/attendance` | Download attendance data as CSV | — | `200 text/csv` | `401`, `403` |

The productivity report includes `metrics` (`completed_tasks`, `on_time_rate`, `overdue_incomplete_tasks`, and `blocked_tasks`), `completion_trends` (one `completed_count` for each date in the selected inclusive range), `status_distribution`, `priority_distribution`, and `workload_distribution`. Completion metrics and workload completions use the selected date range. Overdue and blocked counts, active workload, and status/priority distributions describe the user's currently visible task set. Task visibility follows the same role-based scoping as the task list. Legacy top-level `total_tasks`, `completed_count`, `overdue_count`, and `on_time_rate` fields, plus the trend `completed` count, remain available for existing API consumers.
