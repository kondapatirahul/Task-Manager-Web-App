# 🧪 Manual QA Checklist (M8)

| Feature | Test Action | Expected Result | Status |
| :--- | :--- | :--- | :---: |
| **Auth** | Signup with valid credentials | Account created, 201 response | [x] |
| **Auth** | Login with incorrect password | Returns 401 Unauthorized | [x] |
| **Tasks** | View tasks when not logged in | Returns 401 Unauthorized | [x] |
| **Tasks** | Create new task via API | Task stored in SQLite database | [x] |