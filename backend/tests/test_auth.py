from conftest import auth_headers, signup


def test_onboarding_and_first_user_is_admin(client):
    cfg = client.get("/api/config").json()
    assert cfg["onboarding"] is True

    r = signup(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "admin"
    assert client.get("/api/config").json()["onboarding"] is False

    me = client.get("/api/auths/me", headers=auth_headers(body["token"])).json()
    assert me["email"] == "admin@example.com"


def test_second_user_is_pending_by_default(client):
    signup(client)
    r = signup(client, email="bob@example.com", name="Bob")
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["user"]["role"] == "pending"
    # pending users can't use verified-only endpoints
    assert client.get("/api/users", headers=auth_headers(token)).status_code == 403


def test_signup_can_be_disabled(client):
    admin = signup(client).json()
    h = auth_headers(admin["token"])
    r = client.put("/api/admin/config", json={"enable_signup": False}, headers=h)
    assert r.status_code == 200 and r.json()["enable_signup"] is False
    assert client.get("/api/config").json()["features"]["enable_signup"] is False

    r = signup(client, email="eve@example.com")
    assert r.status_code == 403

    # Admins can still create accounts
    r = client.post(
        "/api/users",
        json={"name": "Eve", "email": "eve@example.com", "password": "password123", "role": "user"},
        headers=h,
    )
    assert r.status_code == 200
    assert client.post("/api/auths/signin", json={"email": "eve@example.com", "password": "password123"}).status_code == 200


def test_default_role_user(client):
    h = auth_headers(signup(client).json()["token"])
    client.put("/api/admin/config", json={"default_user_role": "user"}, headers=h)
    assert signup(client, email="u@example.com").json()["user"]["role"] == "user"
    assert client.put("/api/admin/config", json={"default_user_role": "admin"}, headers=h).status_code == 400


def test_signin_and_bad_password(client):
    signup(client)
    assert client.post("/api/auths/signin", json={"email": "ADMIN@example.com", "password": "password123"}).status_code == 200
    assert client.post("/api/auths/signin", json={"email": "admin@example.com", "password": "nope-nope"}).status_code == 400


def test_admin_user_management_guards(client):
    admin = signup(client).json()
    h = auth_headers(admin["token"])
    bob = signup(client, email="bob@example.com").json()["user"]

    # activate bob
    r = client.patch(f"/api/users/{bob['id']}", json={"role": "user"}, headers=h)
    assert r.json()["role"] == "user"
    # can't demote or delete yourself
    assert client.patch(f"/api/users/{admin['user']['id']}", json={"role": "user"}, headers=h).status_code == 400
    assert client.delete(f"/api/users/{admin['user']['id']}", headers=h).status_code == 400
    assert client.delete(f"/api/users/{bob['id']}", headers=h).status_code == 200
    assert len(client.get("/api/users", headers=h).json()) == 1


def test_password_change_and_settings(client):
    tok = signup(client).json()["token"]
    h = auth_headers(tok)
    assert client.put("/api/auths/me/password", json={"password": "wrong-pass", "new_password": "newpassword1"}, headers=h).status_code == 400
    assert client.put("/api/auths/me/password", json={"password": "password123", "new_password": "newpassword1"}, headers=h).status_code == 200
    assert client.post("/api/auths/signin", json={"email": "admin@example.com", "password": "newpassword1"}).status_code == 200

    r = client.put("/api/auths/me/settings", json={"theme": "light", "evil": 1}, headers=h)
    assert r.json() == {"theme": "light"}


def test_unauthenticated(client):
    assert client.get("/api/auths/me").status_code == 401
    assert client.get("/api/auths/me", headers=auth_headers("garbage")).status_code == 401


def test_spa_fallback(client):
    r = client.get("/some/route")
    assert r.status_code == 200 and "Open Cowork" in r.text
    assert client.get("/api/nope").status_code == 404
