"""Test setup: isolated temp database, fresh client per test, no real emails."""
import os
import tempfile
import uuid

# must be set BEFORE importing the app
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""  # keep the real bot out of tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seed_admin():
    """First user ever registered becomes admin — create that user once."""
    with TestClient(app) as c:
        r = c.post("/api/register", json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
        })
        assert r.status_code == 200


@pytest.fixture()
def client():
    """Fresh TestClient (no cookies carried over between tests)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_rate_limit():
    from app.main import _login_attempts
    _login_attempts.clear()
    yield
    _login_attempts.clear()


@pytest.fixture()
def authed_user(client):
    """Register + login a fresh user; returns (client, user dict)."""
    name = "user" + uuid.uuid4().hex[:8]
    r = client.post("/api/register", json={
        "username": name,
        "email": f"{name}@example.com",
        "password": "secret123",
    })
    assert r.status_code == 200
    return client, r.json()["user"]
