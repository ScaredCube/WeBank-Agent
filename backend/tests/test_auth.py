def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm"]["mode"] == "mock"


def test_login_success(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "demo", "password": "demo123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["username"] == "demo"


def test_login_failure(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "demo", "password": "wrong"},
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me(client, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["display_name"] == "演示用户"
