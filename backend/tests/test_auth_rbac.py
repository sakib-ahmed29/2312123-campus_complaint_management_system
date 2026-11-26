import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["JWT_SECRET"] = "test-only-secret-with-enough-entropy"
os.environ["PASSWORD_PEPPER"] = "test-only-pepper"
os.environ["COOKIE_SECURE"] = "false"

import jwt
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import app, engine, User, now


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def signup(client, email):
    response = client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Campus User", "password": "campus1234"
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "campus1234"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_protected_endpoint_rejects_missing_and_expired_tokens(client):
    assert client.get("/api/v1/users/me").status_code == 401
    expired = jwt.encode({"sub": "1", "exp": now() - timedelta(minutes=1)}, os.environ["JWT_SECRET"], algorithm="HS256")
    assert client.get("/api/v1/users/me", headers=headers(expired)).status_code == 401


def test_user_can_only_read_own_complaints(client):
    signup(client, "first@example.test")
    first_token = login(client, "first@example.test")
    created = client.post("/api/v1/complaints", headers=headers(first_token), json={
        "title": "Broken library air conditioner",
        "description": "The air conditioner in the library has stopped working.",
        "category": "library"
    })
    assert created.status_code == 201, created.text
    assert "id" in created.json(), created.text
    complaint_id = created.json()["id"]

    signup(client, "second@example.test")
    second_token = login(client, "second@example.test")
    assert client.get(f"/api/v1/complaints/{complaint_id}", headers=headers(second_token)).status_code == 404
    assert client.patch(f"/api/v1/complaints/{complaint_id}", headers=headers(second_token),
                        json={"title": "Try to edit another user's record"}).status_code == 404
    assert client.delete(f"/api/v1/complaints/{complaint_id}", headers=headers(second_token)).status_code == 404


def test_normal_user_cannot_change_complaint_status(client):
    signup(client, "student@example.test")
    token = login(client, "student@example.test")
    created = client.post("/api/v1/complaints", headers=headers(token), json={
        "title": "Broken classroom projector",
        "description": "The projector in classroom 302 is not working.",
        "category": "academic"
    })
    assert created.status_code == 201
    assert "id" in created.json(), created.text
    denied = client.patch(f"/api/v1/complaints/{created.json()['id']}/status",
                          headers=headers(token), json={"status": "in_progress"})
    assert denied.status_code == 403


def test_admin_can_change_status_but_cannot_ban_another_admin(client):
    admin_id = signup(client, "admin@example.test")
    signup(client, "student2@example.test")
    student_token = login(client, "student2@example.test")
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        admin.role = "admin"
        db.add(admin)
        db.commit()
    admin_token = login(client, "admin@example.test")
    created = client.post("/api/v1/complaints", headers=headers(student_token), json={
        "title": "Network connection is unavailable",
        "description": "The campus network is unavailable in the north building.",
        "category": "it_network"
    })
    assert created.status_code == 201
    assert "id" in created.json(), created.text
    changed = client.patch(f"/api/v1/complaints/{created.json()['id']}/status",
                           headers=headers(admin_token), json={"status": "in_progress"})
    assert changed.status_code == 200
    assert client.post(f"/api/v1/admin/users/{admin_id}/ban", headers=headers(admin_token),
                       json={"reason": "Test"}).status_code == 403


def test_group_permissions_are_enforced(client):
    owner_id = signup(client, "owner@example.test")
    owner_token = login(client, "owner@example.test")
    member_id = signup(client, "member@example.test")
    member_token = login(client, "member@example.test")
    group = client.post("/api/v1/groups", headers=headers(owner_token), json={"name": "Facilities team"})
    assert group.status_code == 201
    assert "id" in group.json(), group.text
    group_id = group.json()["id"]
    added = client.post(f"/api/v1/groups/{group_id}/members", headers=headers(owner_token), json={
        "user_id": member_id, "can_create": True, "can_edit": False, "can_assign": False
    })
    assert added.status_code == 200
    record = client.post(f"/api/v1/groups/{group_id}/records", headers=headers(member_token), json={
        "title": "Repair library lights", "body": "Several lights need replacement."
    })
    assert record.status_code == 201
    denied = client.patch(f"/api/v1/groups/{group_id}/records/{record.json()['id']}",
                          headers=headers(member_token), json={"body": "Unauthorized edit"})
    assert denied.status_code == 403

    assigner_id = signup(client, "assigner@example.test")
    assigner_token = login(client, "assigner@example.test")
    added_assigner = client.post(f"/api/v1/groups/{group_id}/members", headers=headers(owner_token), json={
        "user_id": assigner_id, "can_create": False, "can_edit": False, "can_assign": True
    })
    assert added_assigner.status_code == 200
    assigned = client.patch(f"/api/v1/groups/{group_id}/records/{record.json()['id']}",
                            headers=headers(assigner_token), json={"assignee_id": owner_id})
    assert assigned.status_code == 200
    edit_denied = client.patch(f"/api/v1/groups/{group_id}/records/{record.json()['id']}",
                               headers=headers(assigner_token), json={"body": "Still cannot edit"})
    assert edit_denied.status_code == 403
    assert client.delete(f"/api/v1/groups/{group_id}", headers=headers(member_token)).status_code == 404



def test_logout_invalidates_access_and_refresh_session(client):
    signup(client, "logout@example.test")
    token = login(client, "logout@example.test")
    assert client.get("/api/v1/users/me", headers=headers(token)).status_code == 200
    response = client.post("/api/v1/auth/logout", headers=headers(token))
    assert response.status_code == 204
    assert client.get("/api/v1/users/me", headers=headers(token)).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_rotation_rejects_reused_refresh_token(client):
    signup(client, "rotation@example.test")
    login(client, "rotation@example.test")
    old_cookie = client.cookies.get("campuscare_refresh")
    assert old_cookie
    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    new_cookie = client.cookies.get("campuscare_refresh")
    assert new_cookie and new_cookie != old_cookie
    replay = client.post("/api/v1/auth/refresh", cookies={"campuscare_refresh": old_cookie})
    assert replay.status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_banned_user_is_rejected_on_the_next_request(client):
    admin_id = signup(client, "ban-admin@example.test")
    signup(client, "to-ban@example.test")
    user_token = login(client, "to-ban@example.test")
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        admin.role = "admin"
        db.add(admin)
        db.commit()
    admin_token = login(client, "ban-admin@example.test")
    users = client.get("/api/v1/admin/users", headers=headers(admin_token)).json()
    target = next(user for user in users if user["email"] == "to-ban@example.test")
    banned = client.post(f"/api/v1/admin/users/{target['id']}/ban", headers=headers(admin_token),
                         json={"reason": "Automated security test"})
    assert banned.status_code == 200
    assert client.get("/api/v1/users/me", headers=headers(user_token)).status_code == 401


def test_admin_can_suspend_and_restore_a_user_account(client):
    admin_id = signup(client, "suspension-admin@example.test")
    target_id = signup(client, "suspended-user@example.test")
    user_token = login(client, "suspended-user@example.test")
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        admin.role = "admin"
        db.add(admin)
        db.commit()
    admin_token = login(client, "suspension-admin@example.test")

    suspended = client.post(
        f"/api/v1/admin/users/{target_id}/suspend",
        headers=headers(admin_token),
        json={"reason": "Temporary policy review", "hours": 2},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"
    assert client.get("/api/v1/users/me", headers=headers(user_token)).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "email": "suspended-user@example.test", "password": "campus1234"
    }).status_code == 401

    listing = client.get("/api/v1/admin/users?status=suspended", headers=headers(admin_token))
    assert listing.status_code == 200
    assert any(row["email"] == "suspended-user@example.test" and row["status"] == "suspended"
               for row in listing.json())

    restored = client.post(
        f"/api/v1/admin/users/{target_id}/unsuspend",
        headers=headers(admin_token),
        json={"reason": "Review completed"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "active"
    assert client.post("/api/v1/auth/login", json={
        "email": "suspended-user@example.test", "password": "campus1234"
    }).status_code == 200



def test_admin_can_demote_self_when_another_admin_remains(client):
    first_admin_id = signup(client, "self-demote@example.test")
    second_admin_id = signup(client, "remaining-admin@example.test")
    with Session(engine) as db:
        first_admin = db.get(User, first_admin_id)
        second_admin = db.get(User, second_admin_id)
        first_admin.role = "admin"
        second_admin.role = "admin"
        db.add(first_admin)
        db.add(second_admin)
        db.commit()

    token = login(client, "self-demote@example.test")
    demoted = client.patch("/api/v1/users/me/role", headers=headers(token))
    assert demoted.status_code == 200, demoted.text
    assert demoted.json() == {"id": first_admin_id, "role": "user"}
    assert client.get("/api/v1/users/me", headers=headers(token)).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401
    with Session(engine) as db:
        assert db.get(User, first_admin_id).role == "user"
        assert db.get(User, second_admin_id).role == "admin"


def test_invalid_email_and_validation_errors_use_one_error_shape(client):
    bad_email = client.post("/api/v1/auth/signup", json={
        "email": "not-an-email", "full_name": "Campus User", "password": "campus1234"})
    assert bad_email.status_code == 422
    assert isinstance(bad_email.json()["detail"], str)
    short_name = client.post("/api/v1/auth/signup", json={
        "email": "shortname@example.test", "full_name": "A", "password": "campus1234"})
    assert short_name.status_code == 422
    assert isinstance(short_name.json()["detail"], str)


def test_admin_endpoints_reject_normal_users_and_activity_stores_forwarded_ip(client):
    admin_id = signup(client, "audit-admin@example.test")
    signup(client, "audit-user@example.test")
    user_token = login(client, "audit-user@example.test")
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        admin.role = "admin"
        db.add(admin)
        db.commit()
    assert client.get("/api/v1/admin/stats", headers=headers(user_token)).status_code == 403
    assert client.get("/api/v1/admin/export/users", headers=headers(user_token)).status_code == 403

    response = client.post("/api/v1/auth/login", json={"email": "audit-admin@example.test", "password": "campus1234"},
                           headers={"X-Forwarded-For": "203.0.113.9", "User-Agent": "pytest-browser"})
    assert response.status_code == 200
    admin_token = response.json()["access_token"]
    events = client.get("/api/v1/admin/activity?event=login", headers=headers(admin_token)).json()
    assert any(e["ip_address"] == "203.0.113.9" and e["user_agent"] == "pytest-browser" for e in events)


def test_user_export_respects_status_and_role_filters(client):
    admin_id = signup(client, "export-admin@example.test")
    target_id = signup(client, "export-target@example.test")
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        admin.role = "admin"
        db.add(admin)
        db.commit()
    admin_token = login(client, "export-admin@example.test")
    assert client.post(f"/api/v1/admin/users/{target_id}/ban", headers=headers(admin_token),
                       json={"reason": "Export test"}).status_code == 200
    banned = client.get("/api/v1/admin/export/users?status=banned", headers=headers(admin_token))
    assert banned.status_code == 200
    assert "export-target@example.test" in banned.text
    assert "export-admin@example.test" not in banned.text
    admins = client.get("/api/v1/admin/export/users?role=admin", headers=headers(admin_token))
    assert "export-admin@example.test" in admins.text
    assert "export-target@example.test" not in admins.text
