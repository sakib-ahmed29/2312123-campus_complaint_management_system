"""Create demo accounts and sample data for the instructor (idempotent).

Run from the backend folder with the SAME environment values as production, so the
password hashes verify on the deployed API:

    DATABASE_URL=...  JWT_SECRET=...  PASSWORD_PEPPER=...  DEMO_PASSWORD='Choose-a-demo-pass1' \
    python seed_demo.py

The demo password is read from the environment, never stored in the repository.
The script prints user IDs and roles (not passwords) for the README.
"""
import os
import sys

from sqlmodel import Session, SQLModel, select

from main import (Complaint, Group, GroupMember, GroupRecord, User, engine, hash_password)

ACCOUNTS = [
    ("admin1@campuscare.test", "Demo Admin One", "admin"),
    ("admin2@campuscare.test", "Demo Admin Two", "admin"),
    ("student1@campuscare.test", "Demo Student One", "user"),
    ("student2@campuscare.test", "Demo Student Two", "user"),
    ("student3@campuscare.test", "Demo Student Three", "user"),
]

COMPLAINTS = [
    ("student1@campuscare.test", "Library air conditioner not working", "The air conditioner on the second floor of the library has not worked for a week.", "library", "pending"),
    ("student2@campuscare.test", "Slow campus Wi-Fi in Block B", "Wi-Fi in Block B is very slow during afternoon classes and drops often.", "it_network", "in_progress"),
    ("student3@campuscare.test", "Cafeteria hygiene concern", "Tables in the cafeteria are not cleaned between lunch rounds.", "cafeteria", "pending"),
    ("student1@campuscare.test", "Late university bus", "The 8:00 AM university bus has been arriving 20 minutes late all month.", "transport", "resolved"),
]

GROUP_NAME = "Hostel Maintenance Team"


def main() -> None:
    password = os.getenv("DEMO_PASSWORD", "")
    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        sys.exit("Set DEMO_PASSWORD (8+ characters, with a letter and a number) in the environment.")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        users: dict[str, User] = {}
        for email, name, role in ACCOUNTS:
            user = db.exec(select(User).where(User.email == email)).first()
            if not user:
                user = User(email=email, full_name=name, password_hash=hash_password(password), role=role)
            else:
                user.role = role
                user.password_hash = hash_password(password)
                user.is_banned = False
                user.suspended_until = None
            db.add(user)
            db.commit()
            db.refresh(user)
            users[email] = user

        for email, title, description, category, status in COMPLAINTS:
            owner = users[email]
            exists = db.exec(select(Complaint).where(Complaint.owner_id == owner.id, Complaint.title == title)).first()
            if not exists:
                db.add(Complaint(owner_id=owner.id, title=title, description=description,
                                 category=category, status=status))
        db.commit()

        owner = users["student1@campuscare.test"]
        group = db.exec(select(Group).where(Group.name == GROUP_NAME, Group.owner_id == owner.id)).first()
        if not group:
            group = Group(name=GROUP_NAME, owner_id=owner.id)
            db.add(group)
            db.commit()
            db.refresh(group)
        permissions = {
            "student1@campuscare.test": (True, True, True),   # owner
            "student2@campuscare.test": (True, True, False),  # create + edit
            "student3@campuscare.test": (False, False, True), # assign only
        }
        for email, (can_create, can_edit, can_assign) in permissions.items():
            member = db.exec(select(GroupMember).where(GroupMember.group_id == group.id,
                                                       GroupMember.user_id == users[email].id)).first()
            if not member:
                member = GroupMember(group_id=group.id, user_id=users[email].id)
            member.can_create, member.can_edit, member.can_assign = can_create, can_edit, can_assign
            db.add(member)
        db.commit()
        if not db.exec(select(GroupRecord).where(GroupRecord.group_id == group.id)).first():
            db.add(GroupRecord(group_id=group.id, created_by=owner.id, title="Fix leaking tap in Hostel A",
                               body="Tap on the third floor of Hostel A has been leaking since Monday."))
            db.add(GroupRecord(group_id=group.id, created_by=users["student2@campuscare.test"].id,
                               title="Replace broken hallway light", body="Light near room 214 is broken."))
            db.commit()

        print("Demo data ready. Add these to the README (never the password):")
        for email, _, role in ACCOUNTS:
            print(f"  id={users[email].id:<4} role={role:<6} {email}")
        print(f"  group '{GROUP_NAME}' id={group.id} owner id={owner.id}")
        print("  student2: create+edit | student3: assign only | student1: owner (all + manage)")


if __name__ == "__main__":
    main()
