from app import create_app, db
from app.models import User, Category, Task
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    # Clear existing data
    Task.query.delete()
    Category.query.delete()
    User.query.delete()

    # Create demo users
    user1 = User(
        username="demo_user1",
        email="demo1@example.com",
        password_hash=generate_password_hash("password123")
    )

    user2 = User(
        username="demo_user2",
        email="demo2@example.com",
        password_hash=generate_password_hash("password123")
    )

    db.session.add_all([user1, user2])
    db.session.commit()

    # Create categories
    work = Category(name="Work", user_id=user1.id)
    personal = Category(name="Personal", user_id=user1.id)

    db.session.add_all([work, personal])
    db.session.commit()

    # Create 10 sample tasks
    tasks = [
        Task(
            title="Complete project documentation",
            description="Finish the project documentation",
            status="pending",
            priority="high",
            user_id=user1.id,
            category_id=work.id
        ),
        Task(
            title="Review database models",
            description="Review User, Category and Task models",
            status="in_progress",
            priority="high",
            user_id=user1.id,
            category_id=work.id
        ),
        Task(
            title="Prepare presentation",
            description="Prepare project presentation slides",
            status="pending",
            priority="medium",
            user_id=user1.id,
            category_id=work.id
        ),
        Task(
            title="Read Python notes",
            description="Review Flask and Python concepts",
            status="done",
            priority="low",
            user_id=user1.id,
            category_id=personal.id
        ),
        Task(
            title="Complete assignment",
            description="Finish pending assignment",
            status="pending",
            priority="high",
            user_id=user1.id,
            category_id=personal.id
        ),
        Task(
            title="Team meeting",
            description="Attend project team meeting",
            status="done",
            priority="medium",
            user_id=user2.id
        ),
        Task(
            title="Update GitHub repository",
            description="Push latest project changes",
            status="pending",
            priority="high",
            user_id=user2.id
        ),
        Task(
            title="Test application",
            description="Test application functionality",
            status="in_progress",
            priority="medium",
            user_id=user2.id
        ),
        Task(
            title="Fix UI issues",
            description="Check and fix frontend issues",
            status="pending",
            priority="low",
            user_id=user2.id
        ),
        Task(
            title="Write project report",
            description="Complete final project report",
            status="done",
            priority="medium",
            user_id=user2.id
        ),
    ]

    db.session.add_all(tasks)
    db.session.commit()

    print("Database seeded successfully!")
    print("Created 2 demo users and 10 sample tasks.")