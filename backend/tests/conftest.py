import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ccms.db")
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long-123456")
os.environ.setdefault("PASSWORD_PEPPER", "test-pepper-not-used-in-production")

import pytest
from fastapi.testclient import TestClient
import main


@pytest.fixture()
def client():
    main.SQLModel.metadata.drop_all(main.engine)
    main.SQLModel.metadata.create_all(main.engine)
    with TestClient(main.app) as test_client:
        yield test_client
    main.SQLModel.metadata.drop_all(main.engine)


def register(client, email, password="StrongPass123", name="Test User", role=None):
    response = client.post("/api/v1/auth/signup", json={"email": email, "name": name, "password": password})
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    if role:
        with main.Session(main.engine) as session:
            user = session.get(main.User, user_id)
            user.role = role
            session.add(user)
            session.commit()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return user_id, login.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}
