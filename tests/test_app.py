from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.scheduler import humanize_interval


def test_register_login_flow(client):
    r = client.post("/api/register", json={
        "username": "carol",
        "email": "carol@example.com",
        "password": "secret123",
    })
    assert r.status_code == 200
    assert r.json()["user"]["is_admin"] is False

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "carol"

    r = client.post("/api/logout")
    assert r.status_code == 200
    assert client.get("/api/me").status_code == 401


def test_register_duplicate(client):
    r = client.post("/api/register", json={
        "username": "alice",
        "email": "other@example.com",
        "password": "secret123",
    })
    assert r.status_code == 400
    assert "already" in r.json()["detail"].lower()


def test_register_short_password(client):
    r = client.post("/api/register", json={
        "username": "shorty",
        "email": "shorty@example.com",
        "password": "123",
    })
    assert r.status_code == 400


def test_login_wrong_password(client):
    r = client.post("/api/login", json={"username": "alice", "password": "wrongpass"})
    assert r.status_code == 401


def test_login_rate_limit(client):
    for _ in range(5):
        client.post("/api/login", json={"username": "alice", "password": "badpass"})
    r = client.post("/api/login", json={"username": "alice", "password": "badpass"})
    assert r.status_code == 429


def test_change_password(client):
    client.post("/api/register", json={
        "username": "changer",
        "email": "changer@example.com",
        "password": "secret123",
    })
    r = client.post("/api/login", json={"username": "changer", "password": "secret123"})
    assert r.status_code == 200

    r = client.post("/api/change-password", json={
        "old_password": "secret123",
        "new_password": "newsecret456",
    })
    assert r.status_code == 200

    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "changer", "password": "secret123"}).status_code == 401
    assert client.post("/api/login", json={"username": "changer", "password": "newsecret456"}).status_code == 200


def test_create_interval_job_defaults_email(authed_user):
    client, user = authed_user
    r = client.post("/api/jobs", json={
        "name": "Drink water",
        "message": "Hydrate!",
        "interval_minutes": 120,
    })
    assert r.status_code == 200
    job = r.json()["job"]
    assert job["type"] == "repeat"
    assert job["interval_label"] == "Every 2 hours"
    assert job["email_to"] == user["email"]
    assert job["enabled"] is True
    assert job["next_run"] is not None


def test_create_send_once_job(authed_user):
    client, user = authed_user
    future = (datetime.now(ZoneInfo("Asia/Tehran")) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    r = client.post("/api/jobs", json={
        "name": "One shot",
        "send_once_at": future,
        "email_to": user["email"],
    })
    assert r.status_code == 200
    job = r.json()["job"]
    assert job["type"] == "once"
    assert job["interval_label"].startswith("Once · ")


def test_create_send_once_in_past_rejected(authed_user):
    client, user = authed_user
    past = (datetime.now(ZoneInfo("Asia/Tehran")) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r = client.post("/api/jobs", json={
        "name": "Too late",
        "send_once_at": past,
        "email_to": user["email"],
    })
    assert r.status_code == 400
    assert "future" in r.json()["detail"].lower()


def test_job_validation(authed_user):
    client, user = authed_user

    assert client.post("/api/jobs", json={"name": "X", "email_to": user["email"]}).status_code == 400

    assert client.post("/api/jobs", json={
        "name": "X", "interval_minutes": 60, "send_once_at": "2099-01-01T10:00",
        "email_to": user["email"],
    }).status_code == 400

    assert client.post("/api/jobs", json={"name": "X", "interval_minutes": 0, "email_to": user["email"]}).status_code == 400

    assert client.post("/api/jobs", json={"name": "X", "interval_minutes": 60, "email_to": "not-an-email"}).status_code == 400

    assert client.post("/api/jobs", json={"name": " ", "interval_minutes": 60, "email_to": user["email"]}).status_code == 400


def test_toggle_and_delete_job(authed_user):
    client, user = authed_user
    r = client.post("/api/jobs", json={
        "name": "Toggler", "interval_minutes": 60, "email_to": user["email"],
    })
    job_id = r.json()["job"]["id"]

    r = client.post(f"/api/jobs/{job_id}/toggle")
    assert r.status_code == 200
    assert r.json()["job"]["enabled"] is False

    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200

    jobs = client.get("/api/jobs").json()["jobs"]
    assert all(j["id"] != job_id for j in jobs)


def test_run_now_writes_log(authed_user, monkeypatch):
    client, user = authed_user
    sent = []

    def fake_send_email(to_email, subject, text_body, html_body=None):
        sent.append(to_email)

    monkeypatch.setattr("app.scheduler.send_email", fake_send_email)

    r = client.post("/api/jobs", json={
        "name": "Run now", "interval_minutes": 60, "email_to": user["email"],
    })
    job_id = r.json()["job"]["id"]

    r = client.post(f"/api/jobs/{job_id}/run-now")
    assert r.status_code == 200
    assert sent == [user["email"]]

    logs = client.get("/api/logs").json()["logs"]
    assert any(l["job_id"] == job_id and l["status"] == "success" for l in logs)


def test_admin_endpoints(client):
    r = client.post("/api/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 200

    r = client.get("/api/admin/overview")
    assert r.status_code == 200
    assert r.json()["users"] >= 2

    r = client.get("/api/admin/users")
    assert r.status_code == 200
    names = [u["username"] for u in r.json()["users"]]
    assert "alice" in names

    r = client.get("/api/admin/jobs")
    assert r.status_code == 200


def test_non_admin_forbidden(authed_user):
    client, _ = authed_user
    r = client.get("/api/admin/overview")
    assert r.status_code == 403


def test_humanize_interval():
    assert humanize_interval(1) == "Every 1 minute"
    assert humanize_interval(30) == "Every 30 minutes"
    assert humanize_interval(60) == "Every 1 hour"
    assert humanize_interval(120) == "Every 2 hours"
    assert humanize_interval(90) == "Every 1 hour 30 minutes"
    assert humanize_interval(1440) == "Every 1 day"
    assert humanize_interval(10080) == "Every 1 week"
    assert humanize_interval(43200) == "Every 1 month"
    assert humanize_interval(None) is None
