# TaskNest — First Run and Role Login

## 1. Install and configure

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set a long random `SECRET_KEY`. Keep `.env` private. The default database is SQLite for local development.

## 2. Create the Admin account

```powershell
flask --app run.py create-admin
```

Enter the Admin email, full name, and a strong password when prompted. The password is not stored in plain text and no default admin credentials are included.

## 3. Start the site

```powershell
python run.py
```

Open **http://127.0.0.1:5000/**. The homepage includes the two-column introduction and login form. Select **Admin / HR** and sign in with the account created in step 2.

## 4. Create a Team Lead

In a second terminal, activate the same virtual environment and run:

```powershell
flask --app run.py create-user
```

Choose the `team_lead` role. To create an employee, repeat the command and choose `employee`. These roles are stored in the database; choosing a login portal never changes account permissions.

## 5. Role destinations

- Admin / HR: `/admin/dashboard`
- Team Lead: `/lead/dashboard`
- Employee: `/employee/dashboard`

The application also redirects `/dashboard` to the correct destination based on the signed-in account. The public homepage remains available at `/`.

## Troubleshooting

- If Flask is missing, activate `.venv` and run `python -m pip install -r requirements.txt`.
- If you already have an account but cannot use the Admin portal, its database role must be `admin` or `super_admin`; a normal employee cannot self-promote.
- If your old local database has accounts, they are not deleted by these changes. Use the appropriate existing administrative account or a carefully reviewed database migration to correct role assignments.
