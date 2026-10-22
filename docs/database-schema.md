# TaskNest Database Schema

The application uses **SQLite** managed via **Flask-SQLAlchemy**.

## Entity Relationship Summary
```
+--------------------+ 1 : N +--------------------+ 1 : N +--------------------+
|   organizations    | ----< |    departments     | ----< |       teams        |
+--------------------+       +--------------------+       +--------------------+
          | 1                          | 1                          | 1
          |                            |                            |
          | N                          | N                          | N
+--------------------+                 |                            |
|       users        | <---------------+----------------------------+
+--------------------+
    | 1            | 1 (reports_to)           | M
    |              v                          v
    |          users (manager)        +--------------------+
    | 1 : N                           |    team_members    |
    +--------------+                  +--------------------+
    |              |
    v              v
+---------+  +------------+ 1 : N (optional)
| tasks   |  | categories | --------------------+
+---------+  +------------+                     |
    |                                           |
    +-------------------------------------------+ (tasks.category_id)
    |
    +------------> team_id (optional -> teams.id)
    |
    +------------> assigned_to_id (optional -> users.id)
```

---

## 1. `users` Table
Stores registered user accounts, authentication credentials, organizational placement, and account state.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique identifier for user |
| `username` | `VARCHAR(80)` | `NOT NULL, UNIQUE` | Unique login username |
| `full_name` | `VARCHAR(100)` | `NOT NULL, DEFAULT ''` | Display name for greeting & profile |
| `email` | `VARCHAR(120)` | `NOT NULL, UNIQUE` | Unique email for authentication |
| `password_hash` | `VARCHAR(256)` | `NOT NULL` | Secure Werkzeug scrypt/pbkdf2 hash |
| `created_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Registration timestamp |
| `role` | `VARCHAR(20)` | `NOT NULL, DEFAULT 'employee'` | Role: `super_admin`, `admin`, `hr`, `team_lead`, `employee` |
| `account_active` | `BOOLEAN` | `NOT NULL, DEFAULT 1` | Active status: `1` (active) or `0` (deactivated) |
| `organization_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (organizations.id ON DELETE SET NULL)` | Organization identifier |
| `department_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (departments.id ON DELETE SET NULL)` | Department identifier |
| `job_title` | `VARCHAR(100)` | `NULLABLE` | Job title / position designation |
| `phone` | `VARCHAR(30)` | `NULLABLE` | Contact telephone number |
| `reports_to_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (users.id ON DELETE SET NULL)` | Reporting manager user identifier |

- **Relationships**:
  - `organization`: References `Organization` via `organization_id`.
  - `department`: References `Department` via `department_id`.
  - `reports_to` / `direct_reports`: Self-referencing reporting hierarchy.
  - `teams`: Many-to-many relationship with `Team` via `team_members` association table.
  - `tasks`: 1-to-many relationship with `Task` created by this user (`cascade='all, delete-orphan'`).
  - `assigned_tasks`: 1-to-many relationship with `Task` delegated/assigned to this user.
  - `categories`: 1-to-many relationship with `Category` (`cascade='all, delete-orphan'`).
- **Deactivation Policy**:
  - Soft-deactivation via `account_active = 0`. Prevents login while preserving all historic tasks, logs, and relationships.

---

## 2. `organizations` Table
Stores enterprise organizations / tenants.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique organization identifier |
| `name` | `VARCHAR(100)` | `NOT NULL, UNIQUE` | Organization name |
| `description` | `TEXT` | `NULLABLE` | Company mission, description, or notes |
| `created_by_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (users.id ON DELETE SET NULL)` | Founder / creator user identifier |
| `created_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Creation timestamp |

- **Relationships**:
  - `departments`: 1-to-many relationship with `Department` (`cascade='all, delete-orphan'`).
  - `teams`: 1-to-many relationship with `Team` (`cascade='all, delete-orphan'`).
  - `members`: 1-to-many relationship with `User` members.

---

## 3. `departments` Table
Represents business units or divisions within an organization.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique department identifier |
| `name` | `VARCHAR(100)` | `NOT NULL` | Department name (e.g., Engineering, Sales) |
| `description` | `TEXT` | `NULLABLE` | Department summary or focus |
| `organization_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (organizations.id ON DELETE CASCADE)` | Associated organization |
| `head_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (users.id ON DELETE SET NULL)` | Department Head user identifier |
| `created_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Creation timestamp |

- **Relationships**:
  - `organization`: References `Organization` via `organization_id`.
  - `head`: References `User` via `head_id`.
  - `members`: 1-to-many relationship with `User` members assigned to this department.
  - `teams`: 1-to-many relationship with `Team` under this department.
- **Safe Deletion Policy**:
  - Upon deletion, associated employees have their `department_id` set to `NULL`, preventing user deletion.

---

## 4. `teams` Table
Represents cross-functional or departmental squads led by team leads.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique team identifier |
| `name` | `VARCHAR(100)` | `NOT NULL` | Team name (e.g., Frontend Core, DevOps) |
| `description` | `TEXT` | `NULLABLE` | Team focus or responsibilities |
| `organization_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (organizations.id ON DELETE CASCADE)` | Associated organization |
| `department_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (departments.id ON DELETE SET NULL)` | Associated department |
| `lead_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (users.id ON DELETE SET NULL)` | Appointed Team Lead user identifier |
| `created_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Creation timestamp |

- **Relationships**:
  - `organization`: References `Organization` via `organization_id`.
  - `department`: References `Department` via `department_id`.
  - `lead`: References `User` via `lead_id`.
  - `members`: Many-to-many relationship with `User` via `team_members`.
  - `tasks`: 1-to-many relationship with `Task` assigned to this team workspace.

---

## 5. `team_members` Association Table
Represents team membership rosters and role within team.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `team_id` | `INTEGER` | `PRIMARY KEY, FOREIGN KEY (teams.id ON DELETE CASCADE)` | Team identifier |
| `user_id` | `INTEGER` | `PRIMARY KEY, FOREIGN KEY (users.id ON DELETE CASCADE)` | Member user identifier |
| `role` | `VARCHAR(20)` | `NOT NULL, DEFAULT 'member'` | Team role: `lead` or `member` |
| `joined_at` | `DATETIME` | `NOT NULL, DEFAULT utcnow` | Membership start timestamp |

---

## 6. `categories` Table
Organizes personal tasks into customizable workspaces per user.

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

## 7. `tasks` Table
Stores actionable task records, priority flags, statuses, deadlines, and ownership/delegation.

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
| `user_id` | `INTEGER` | `NOT NULL, FOREIGN KEY (users.id)` | Owning / author user identifier |
| `category_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (categories.id ON DELETE SET NULL)` | Optional category assignment |
| `team_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (teams.id ON DELETE SET NULL)` | Optional team workspace assignment |
| `assigned_to_id` | `INTEGER` | `NULLABLE, FOREIGN KEY (users.id ON DELETE SET NULL)` | Optional delegated assignee user identifier |

- **Foreign Keys**:
  - `user_id` references `users.id`.
  - `category_id` references `categories.id` (`ondelete='SET NULL'`).
  - `team_id` references `teams.id` (`ondelete='SET NULL'`).
  - `assigned_to_id` references `users.id` (`ondelete='SET NULL'`).

---



---

## 8. 	ask_status_history Table
Stores immutable audit log records for every status transition and review event on a task.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique history record identifier |
| 	ask_id | INTEGER | NOT NULL, FOREIGN KEY (tasks.id ON DELETE CASCADE) | Associated task identifier |
| changed_by_id | INTEGER | NULLABLE, FOREIGN KEY (users.id ON DELETE SET NULL) | User who triggered the status change |
| old_status | VARCHAR(30) | NULLABLE | Previous task status |
| 
ew_status | VARCHAR(30) | NOT NULL | New task status |
| comment | TEXT | NULLABLE | Transition reason, review notes, or submission summary |
| created_at | DATETIME | NOT NULL, DEFAULT utcnow | Timestamp of status event |

- **Foreign Keys**:
  - 	ask_id references 	asks.id (ondelete='CASCADE').
  - changed_by_id references users.id (ondelete='SET NULL').

## Database Initialization & Automatic Migrations
The database schema can be initialized at any time from the command line:

```powershell
flask --app run.py init-db
```

Or via direct python startup (`python run.py`), which calls `db.create_all()` within application context to ensure all tables exist safely without dropping existing data.

### Automated Schema Evolution:
`app/__init__.py` incorporates an automatic SQLite schema inspector that scans the `users` and `tasks` tables upon startup and dynamically executes non-destructive `ALTER TABLE ADD COLUMN` statements for newly introduced columns (`role`, `account_active`, `organization_id`, `department_id`, `job_title`, `phone`, `reports_to_id` on `users`; `team_id`, `assigned_to_id` on `tasks`), ensuring zero data loss across upgrades.
