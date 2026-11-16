"""Compatibility across the TV2 flat modules and TV3 package integration."""
import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from sqlalchemy.dialects.mysql import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from app.config import settings
from app.db import Base
from app.models import AuditLog, User
from app.realtime import load_identity
from app.security.auth import create_access_token, revoke_token
from test_api import mk_user


def test_existing_mysql_schema_does_not_need_a_migration():
    before = json.loads((Path(__file__).parent / "fixtures/pre-rebase-schema.json").read_text(encoding="utf-8"))
    after = {
        table.name: {
            "ddl": str(CreateTable(table).compile(dialect=dialect())),
            "indexes": sorted(str(CreateIndex(index).compile(dialect=dialect())) for index in table.indexes),
        }
        for table in Base.metadata.sorted_tables
    }
    assert after == before


def test_existing_tv2_token_remains_valid_then_revoke_survives_module_reload(client, db):
    user = mk_user(db, "existing@example.test", "Admin")
    # Exact old claim shape: no TV3 role or jti claim required.
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": str(user.id), "tv": user.token_version,
                        "iat": now, "exp": now + timedelta(minutes=5)},
                       settings.jwt_secret, algorithm="HS256")
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/me", headers=headers).status_code == 200
    assert load_identity(token).user_id == user.id
    revoke_token(token)
    from app.security import auth
    importlib.reload(auth)
    assert client.get("/api/me", headers=headers).status_code == 401
    assert load_identity(token) is None


def test_tv3_token_factory_reads_existing_account_version_and_roles(client, db):
    user = mk_user(db, "tv3-interface@example.test", "Operator")
    token = create_access_token(user.id, user.role)
    response = client.get("/api/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200 and response.json()["role"] == "Operator"


def test_tv3_audit_service_remains_atomic_with_business_transaction(db):
    from app.services import audit
    entry = audit.log(db, None, "integration.rollback", "device", 1,
                      detail={"password": "must-not-persist", "nested": [{"token": "secret"}]})
    db.flush()
    assert "must-not-persist" not in entry.detail and '"secret"' not in entry.detail
    db.rollback()
    assert db.query(AuditLog).filter_by(action="integration.rollback").first() is None


def test_tv3_rbac_is_used_by_real_routes_with_tv2_case_and_scope(client, db):
    from app.models import Device, UserDevice
    from app.security.rbac import can_access_device
    admin = mk_user(db, "admin-rebase@example.test", "Admin")
    viewer = mk_user(db, "viewer-rebase@example.test", "Viewer")
    own = Device(device_code="own", type="tank")
    other = Device(device_code="other", type="tank")
    db.add_all([own, other])
    db.flush()
    db.add(UserDevice(user_id=viewer.id, device_id=own.id))
    db.commit()
    token = create_access_token(viewer.id, viewer.role)
    headers = {"Authorization": "Bearer " + token}
    assert can_access_device(viewer, own.id, db) and not can_access_device(viewer, other.id, db)
    assert can_access_device(admin, other.id, db)
    assert client.get(f"/api/devices/{own.id}", headers=headers).status_code == 200
    assert client.get(f"/api/devices/{other.id}", headers=headers).status_code == 404
    assert client.get("/api/users", headers=headers).status_code == 403
