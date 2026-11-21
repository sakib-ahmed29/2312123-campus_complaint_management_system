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
