from conftest import register, auth


def test_protected_complaints_reject_missing_token(client):
    response = client.get("/api/v1/complaints")
    assert response.status_code == 401


def test_student_cannot_change_complaint_status(client):
    owner_id, student_token = register(client, "student@example.com")
    admin_id, admin_token = register(client, "admin@example.com", role="admin")
    created = client.post("/api/v1/complaints", headers=auth(student_token), json={
        "title": "Broken classroom fan", "description": "The fan has not worked since Monday.", "category": "academic"
    })
    assert created.status_code == 201
    denied = client.patch(f"/api/v1/complaints/{created.json()['id']}/status",
                          headers=auth(student_token), json={"status": "in_progress"})
    assert denied.status_code == 403


def test_student_cannot_read_another_students_complaint(client):
    _, token_a = register(client, "owner@example.com")
    _, token_b = register(client, "other@example.com")
    created = client.post("/api/v1/complaints", headers=auth(token_a), json={
        "title": "Library air conditioner", "description": "The library AC is not cooling the room.", "category": "library"
    })
    assert created.status_code == 201
    response = client.get(f"/api/v1/complaints/{created.json()['id']}", headers=auth(token_b))
    assert response.status_code == 404


def test_admin_can_list_all_complaints(client):
    _, student_token = register(client, "writer@example.com")
    _, admin_token = register(client, "administrator@example.com", role="admin")
    created = client.post("/api/v1/complaints", headers=auth(student_token), json={
        "title": "Cafeteria water issue", "description": "The drinking water tap is broken.", "category": "cafeteria"
    })
    assert created.status_code == 201
    response = client.get("/api/v1/complaints", headers=auth(admin_token))
    assert response.status_code == 200
    assert any(item["id"] == created.json()["id"] for item in response.json())


def test_admin_cannot_change_own_role(client):
    admin_id, admin_token = register(client, "chief@example.com", role="admin")
    response = client.patch(f"/api/v1/admin/users/{admin_id}/role", headers=auth(admin_token), json={"role": "user"})
    assert response.status_code == 400


def test_invalid_access_token_is_rejected(client):
    response = client.get("/api/v1/complaints", headers=auth("tampered.invalid.token"))
    assert response.status_code == 401
