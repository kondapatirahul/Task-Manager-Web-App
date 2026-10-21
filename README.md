# 🚀 Task Manager Web App

A collaborative, full-stack task management web application built by an 8-member engineering team using Python Flask, SQLite, and vanilla JavaScript.

---

## 🛠️ Tech Stack
- **Backend:** Python 3, Flask, Flask-SQLAlchemy, Flask-Login, python-dotenv
- **Frontend:** HTML5, CSS3, JavaScript (Fetch API)
- **Database:** SQLite (`tasks.db`)
- **Testing:** Pytest & automated API integration tests
---

## 📋 Features
- **User Authentication:** Signup, login, and logout with hashed passwords and session management.
- **Task Management (CRUD):** Create, view, update, delete, and mark tasks as done.
- **Categorization & Priorities:** Multi-category organization (`Work`, `Personal`, etc.) and 3 priority levels (`low`, `medium`, `high`).
- **Due Dates:** Track upcoming and overdue deadlines.
- **Executive Dashboard:** Live counters for pending, in-progress, completed, and high-priority tasks.
- **RESTful API:** Clean JSON endpoints for tasks, categories, auth, and statistics.
- **Search & Filters:** Real-time filtering by status, priority, and category.

---

## 📂 Project Architecture

```text
Task-Manager-Web-App/
├── app/
│   ├── __init__.py          # Application Factory (create_app) & DB initialization
│   ├── models.py            # SQLAlchemy Models: User, Category, Task
│   └── routes/
│       ├── __init__.py      # Blueprint definitions
│       ├── auth.py          # /api/auth routes (register, login, logout)
│       ├── tasks.py         # /api/tasks routes (CRUD operations)
│       ├── categories.py    # /api/categories routes
│       └── stats.py         # /api/stats route (dashboard metrics)
├── docs/
│   ├── api-contract.md      # API specification & JSON schemas
│   └── database-schema.md   # Relational table specifications
├── static/
│   ├── css/style.css        # Responsive styling and layout
│   └── js/
│       ├── api.js           # Reusable fetch client
│       ├── auth.js          # Client-side authentication logic
│       └── tasks.js         # Task board DOM rendering and event listeners
├── templates/
│   └── base.html            # Core HTML5 layout shell
├── tests/
│   └── test_api.py          # Pytest automated API suite
├── .env.example             # Environment variable template
├── .gitignore               # Ignored files (venv, instance, __pycache__)
├── requirements.txt         # Project dependencies
├── run.py                   # Development server entrypoint
└── README.md                # Project documentation