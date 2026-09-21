import pytest

from conftest import checkin, csrf_token, login


@pytest.mark.parametrize("role,account,dashboard", [("teacher", "T1", "/teacher/"), ("student", "S1", "/student/")])
def test_login_logout_and_password(client, role, account, dashboard):
    assert login(client, role, account, "wrong").status_code == 401
    with client.session_transaction() as session:
        session["old_state"] = "clear-me"
    response = login(client, role, account)
    assert response.status_code == 302 and response.location == dashboard
    with client.session_transaction() as session:
        assert session["role"] == role and session["user_id"] == 1
        assert "old_state" not in session
    assert client.get(dashboard).status_code == 200
    assert client.post("/logout", data={"csrf_token": csrf_token(client)}).status_code == 302
    assert client.get(dashboard).status_code == 302


def test_unauthenticated_and_role_permissions(client):
    assert client.get("/teacher/").status_code == 302
    assert client.get("/student/").status_code == 302
    assert checkin(client).status_code == 401
    login(client)
    assert client.get("/teacher/").status_code == 403
    assert client.get("/teacher/tasks/new").status_code == 403
    assert client.post("/teacher/tasks/new", data={"csrf_token": csrf_token(client)}).status_code == 403
    login(client, "teacher", "T1")
    assert client.get("/student/").status_code == 403
    assert client.get("/student/records").status_code == 403
    assert checkin(client).status_code == 403
    assert client.get("/teacher/tasks/2").status_code == 403
    assert "任务2" not in client.get("/teacher/").get_data(as_text=True)


@pytest.mark.parametrize("path,payload", [("/login", {"role":"teacher","account":"T1","password":"test-pass"}),
    ("/logout", {}), ("/teacher/tasks/new", {})])
@pytest.mark.parametrize("token", [None, "bad-token"])
def test_form_csrf(client, path, payload, token):
    login(client, "teacher", "T1")
    data = dict(payload)
    if token:
        data["csrf_token"] = token
    result = client.post(path, data=data)
    assert result.status_code == 400
    assert "CSRF" in result.get_data(as_text=True)


@pytest.mark.parametrize("headers", [{}, {"X-CSRFToken": "invalid"}])
def test_json_csrf(client, headers):
    login(client)
    response = client.post("/student/tasks/1/checkin", json={"latitude":0,"longitude":0}, headers=headers)
    assert response.status_code == 400 and "CSRF" in response.json["message"]
    assert checkin(client).status_code == 200


def test_csrf_not_transferable_between_clients(app):
    first, second = app.test_client(), app.test_client()
    login(first)
    login(second)
    assert checkin(second, token=csrf_token(first)).status_code == 400


def test_invalid_role_and_missing_user(client, app):
    assert login(client, "administrator", "T1").status_code == 401
    with client.session_transaction() as session:
        session.update(role="student", user_id=999)
    assert checkin(client).status_code == 401
