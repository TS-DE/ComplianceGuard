"""鉴权用例：注册、登录成功/失败、未授权 401、me。"""

from fastapi.testclient import TestClient

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
CRED = {"username": "alice", "password": "secret123"}


def test_health_no_auth(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"


def test_register_success_returns_brief(client: TestClient) -> None:
    resp = client.post(REGISTER, json=CRED)
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["username"] == "alice"
    assert body["data"]["role"] == "operator"
    assert "password" not in str(body["data"])


def test_register_duplicate_409(client: TestClient) -> None:
    client.post(REGISTER, json=CRED)
    resp = client.post(REGISTER, json=CRED)
    assert resp.status_code == 409
    assert resp.json()["code"] == 409


def test_register_short_password_400(client: TestClient) -> None:
    resp = client.post(REGISTER, json={"username": "bob", "password": "123"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 400


def test_password_stored_as_bcrypt(client: TestClient, db) -> None:
    from sqlalchemy import text

    client.post(REGISTER, json=CRED)
    stored = db.execute(
        text("SELECT password_hash FROM users WHERE username='alice'")
    ).scalar_one()
    assert stored.startswith("$2b$")
    assert CRED["password"] not in stored


def test_login_success_returns_token(client: TestClient) -> None:
    client.post(REGISTER, json=CRED)
    resp = client.post(LOGIN, json=CRED)
    data = resp.json()["data"]
    assert resp.status_code == 200
    assert data["token_type"] == "bearer"
    assert data["access_token"].count(".") == 2
    assert data["user"]["username"] == "alice"


def test_login_wrong_password_401(client: TestClient) -> None:
    client.post(REGISTER, json=CRED)
    resp = client.post(LOGIN, json={"username": "alice", "password": "wrong-pass"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 401


def test_login_unknown_user_same_message(client: TestClient) -> None:
    """不存在的用户与密码错误返回同一提示，防账号枚举。"""
    client.post(REGISTER, json=CRED)
    wrong_pwd = client.post(LOGIN, json={"username": "alice", "password": "wrong-pass"})
    no_user = client.post(LOGIN, json={"username": "nobody", "password": "whatever"})
    assert no_user.status_code == 401
    assert no_user.json()["msg"] == wrong_pwd.json()["msg"]


def test_me_without_token_401(client: TestClient) -> None:
    resp = client.get(ME)
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_me_with_bad_token_401(client: TestClient) -> None:
    resp = client.get(ME, headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


def test_me_with_token(client: TestClient, auth_headers: dict) -> None:
    resp = client.get(ME, headers=auth_headers)
    data = resp.json()["data"]
    assert resp.status_code == 200
    assert data["username"] == "pytest_user"
    assert "created_at" in data


def test_inactive_user_cannot_login(client: TestClient, db) -> None:
    from sqlalchemy import text

    client.post(REGISTER, json=CRED)
    db.execute(text("UPDATE users SET is_active=0 WHERE username='alice'"))
    db.commit()
    resp = client.post(LOGIN, json=CRED)
    assert resp.status_code == 401
