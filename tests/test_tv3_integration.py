import json
from datetime import timedelta

import pytest
from sqlalchemy import select
from starlette.requests import Request

from app import accounts
from app.audit import sanitize_detail, write_audit
from app.config import settings
from app.lifecycle import Conflict
from app.login_guard import client_ip
from app.models import AuditLog, User
from test_api import mk_user


def test_last_active_admin_is_preserved_without_changing_any_account(db):
    admin = mk_user(db, "sole@example.test", "Admin")
    with pytest.raises(Conflict, match="Admin"):
        accounts.update_user(db, admin.id, full_name=None, role="Viewer", status=None,
                             unlock=False, actor_id=None, ip="test")
    db.rollback()
    assert db.get(User, admin.id).role == "Admin"
    mk_user(db, "second@example.test", "Admin")
    accounts.update_user(db, admin.id, full_name=None, role="Viewer", status=None,
                         unlock=False, actor_id=None, ip="test")
    assert db.get(User, admin.id).role == "Viewer"


def test_audit_sanitizer_redacts_nested_json_and_bearer_without_committing(db):
    detail = {"node": 1, "nested": [{"MQTT_password": "private-one", "access_token": "private-two"}],
              "message": "Authorization: Bearer private-three"}
    write_audit(db, None, "test.sanitizer", "device", 1, "test", json.dumps(detail))
    db.flush()
    row = db.scalar(select(AuditLog))
    assert "private-" not in row.detail and "REDACTED" in row.detail
    assert '"node": 1' in row.detail
    db.rollback()
    assert db.scalar(select(AuditLog)) is None
    assert "secret-value" not in sanitize_detail('password="secret-value" reason=failed')


def test_login_ip_limit_covers_unknown_accounts_and_resets_after_window(client, monkeypatch):
    from app import login_guard
    clock = [100.0]
    monkeypatch.setattr(login_guard, "monotonic", lambda: clock[0])
    monkeypatch.setattr(settings, "login_ip_max_attempts", 3)
    monkeypatch.setattr(settings, "login_ip_window_s", 60)
    for i in range(3):
        assert client.post("/api/auth/login", json={"email": f"missing{i}@test.vn", "password": "bad"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"email": "another@test.vn", "password": "bad"})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    clock[0] += 61
    assert client.post("/api/auth/login", json={"email": "another@test.vn", "password": "bad"}).status_code == 401


def test_forwarded_ip_is_used_only_from_a_configured_trusted_proxy(monkeypatch):
    def request(peer):
        return Request({"type": "http", "client": (peer, 1234),
                        "headers": [(b"x-real-ip", b"203.0.113.8")]})
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "172.20.0.0/16")
    assert client_ip(request("172.20.0.4")) == "203.0.113.8"
    assert client_ip(request("198.51.100.4")) == "198.51.100.4"
