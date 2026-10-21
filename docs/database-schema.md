# TaskNest Database Schema

The application uses **SQLite** managed via **Flask-SQLAlchemy**.

## Entity Relationship Summary
```
+----------------+          1 : N          +--------------------+
|     users      | ----------------------< |       tasks        |
+----------------+                         +--------------------+
        | 1                                          | N
        |                                            |
        | N                                          | 1 (nullable)
+----------------+                         +--------------------+
|   categories   | ------------------------+     category_id    |
+----------------+
```

---

## 1. `users` Table
Stores registered user accounts, authentication credentials, and account timestamps.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique identifier for user |
| `username` | `VARCHAR(80)` | `NOT NULL, UNIQUE` | Unique login username |
| `full_name` | `VARCHAR(100)` | `NOT NULL` | Display name for greeting & profile |
| `email` | `VARCHAR(120)` | `NOT NULL, UNIQUE` | Unique email for authentication |
| `password_hash` | `VARCHAR(256)` | `NOT NULL` | Secure Werkzeug scrypt/pbkdf2 hash |
| `created_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Registration timestamp |

- **Relationships**:
  - `tasks`: 1-to-many relationship with `Task` (`cascade='all, delete-orphan'`).
  - `categories`: 1-to-many relationship with `Category` (`cascade='all, delete-orphan'`).

---

## 2. `categories` Table
Organizes tasks into customizable workspaces per user.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique category identifier |
| `name` | `VARCHAR(50)` | `NOT NULL` | Category name (e.g., Work, Personal) |
| `user_id` | `INTEGER` | `NOT NULL, FOREIGN KEY (users.id)` | Owner user identifier |
| `created_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Creation timestamp |

- **Foreign Key**: `user_id` references `users.id`.
- **Relationships**:
  - `tasks`: 1-to-many relationship with `Task`.
- **Safe Deletion Policy**:
  - When a category is deleted, any tasks assigned to it are automatically unassigned (`category_id` set to `NULL`), ensuring zero accidental task loss.

---

## 3. `tasks` Table
Stores actionable task records, priority flags, statuses, deadlines, and ownership.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique task identifier |
| `title` | `VARCHAR(200)` | `NOT NULL` | Task title |
| `description` | `TEXT` | `NULLABLE` | Detailed notes or task description |
| `status` | `VARCHAR(20)` | `NOT NULL, DEFAULT 'pending'` | Status: `pending` or `completed` |
| `priority` | `VARCHAR(10)` | `NOT NULL, DEFAULT 'medium'` | Priority: `low`, `medium`, or `high` |
| `due_date` | `DATE` | `NULLABLE` | Optional completion target date |
| `created_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Creation timestamp |
| `completed_at` | `DATETIME` | `NULLABLE` | Timestamp when marked completed |
| `user_id` | `INTEGER` | `NOT NULL, FOREIGN KEY (users.id)` | Owning user identifier |
| `category_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (categories.id ON DELETE SET NULL)` | Optional category assignment |

- **Foreign Keys**:
  - `user_id` references `users.id`.
  - `category_id` references `categories.id` (`ondelete='SET NULL'`).

---

## Database Initialization
The database schema can be initialized at any time from the command line:

```powershell
flask --app run.py init-db
```

Or via direct python startup (`python run.py`), which calls `db.create_all()` within application context to ensure all tables exist safely without dropping existing data.
