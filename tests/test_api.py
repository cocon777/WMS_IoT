from datetime import timedelta

import jwt
import pytest

from app import accounts, lifecycle
from app.config import settings
from app.db import utcnow
from app.models import Telemetry

PW = "Passw0rd!x"


def mk_user(db, email, role):
    return accounts.create_user(db, email=email, password=PW, full_name=role, role=role, actor_id=None, ip="t")


def mk_device(db, code, state="Active", dtype="tank"):
    d = lifecycle.create_device(db, device_code=code, name=code, hw_version="v1", device_type=dtype,
                                actor_id=None, ip="t")
    d.state = state
    db.commit()
    return d


def login(client, email, pw=PW):
    return client.post("/api/auth/login", json={"email": email, "password": pw})


def auth(client, email):
    return {"Authorization": "Bearer " + login(client, email).json()["access_token"]}


def add_tel(db, dev, seq, secs_ago=10, level=50.0, boot="b1"):
    now = utcnow()
    values = ({"distance_cm": 10, "level_pct": level} if dev.type == "tank"
              else {"flow_lpm": 1.0, "flow_total_l": 5.0, "pump_on": False})       # mỗi loại node chỉ có trường của mình
    db.add(Telemetry(device_id=dev.id, boot_id=boot, seq=seq, ts=now - timedelta(seconds=secs_ago),
                     received_at=now, rssi=-60, **values))
    db.commit()


def test_login_me_and_no_hash_leak(client, db):
    mk_user(db, "a@x.vn", "Admin")
    r = login(client, "a@x.vn")
    assert r.status_code == 200 and "password" not in r.text
    me = client.get("/api/me", headers={"Authorization": "Bearer " + r.json()["access_token"]})
    assert me.status_code == 200 and me.json()["email"] == "a@x.vn"


def test_wrong_credentials_same_message(client, db):
    mk_user(db, "a@x.vn", "Admin")
    r1, r2 = login(client, "a@x.vn", "sai-mat-khau"), login(client, "khong@x.vn", "sai-mat-khau")
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()


def test_S6_lockout_after_5_failures(client, db):
    mk_user(db, "a@x.vn", "Admin")
    for _ in range(4):
        assert login(client, "a@x.vn", "sai-mat-khau").status_code == 401
    assert login(client, "a@x.vn", "sai-mat-khau").status_code == 429
    assert login(client, "a@x.vn").status_code == 429       # đúng mật khẩu vẫn bị khóa


def test_S2_bad_tokens_rejected(client, db):
    u = mk_user(db, "a@x.vn", "Admin")
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer abc"}).status_code == 401
    expired = jwt.encode({"sub": str(u.id), "tv": 0, "exp": utcnow() - timedelta(minutes=1)},
                         settings.jwt_secret, algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_logout_revokes_token(client, db):
    mk_user(db, "a@x.vn", "Admin")
    h = auth(client, "a@x.vn")
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    assert client.get("/api/me", headers=h).status_code == 401


def test_S1_operator_only_sees_assigned_devices(client, db):
    mk_user(db, "a@x.vn", "Admin")
    op = mk_user(db, "o@x.vn", "Operator")
    d1, d2 = mk_device(db, "wms-001"), mk_device(db, "wms-002")
    ha = auth(client, "a@x.vn")
    assert client.put(f"/api/users/{op.id}/devices", json={"device_ids": [d1.id]}, headers=ha).status_code == 200
    ho = auth(client, "o@x.vn")
    assert client.get(f"/api/devices/{d1.id}", headers=ho).status_code == 200
    assert client.get(f"/api/devices/{d2.id}", headers=ho).status_code == 404
    assert client.get(f"/api/devices/{d2.id}/telemetry", headers=ho).status_code == 404
    assert [d["id"] for d in client.get("/api/devices", headers=ho).json()] == [d1.id]


def test_role_permissions(client, db):
    mk_user(db, "v@x.vn", "Viewer")
    mk_user(db, "o@x.vn", "Operator")
    d = mk_device(db, "wms-001")
    hv, ho = auth(client, "v@x.vn"), auth(client, "o@x.vn")
    assert client.post("/api/devices", json={"device_code": "wms-009", "type": "pipe"}, headers=hv).status_code == 403
    assert client.get(f"/api/devices/{d.id}/telemetry/export", headers=hv).status_code == 403
    assert client.get("/api/audit-logs", headers=hv).status_code == 403
    assert client.get("/api/audit-logs", headers=ho).status_code == 403
    assert client.get("/api/users", headers=ho).status_code == 403


def test_operator_may_only_set_maintenance(client, db):
    mk_user(db, "a@x.vn", "Admin")
    op = mk_user(db, "o@x.vn", "Operator")
    d = mk_device(db, "wms-001")
    client.put(f"/api/users/{op.id}/devices", json={"device_ids": [d.id]}, headers=auth(client, "a@x.vn"))
    ho = auth(client, "o@x.vn")
    r = client.patch(f"/api/devices/{d.id}/state", json={"state": "Decommissioned", "confirm": True}, headers=ho)
    assert r.status_code == 403
    r = client.patch(f"/api/devices/{d.id}/state", json={"state": "Maintenance"}, headers=ho)
    assert r.status_code == 200 and r.json()["state"] == "Maintenance"


def test_admin_cannot_lock_self_and_disabled_user_loses_access(client, db):
    admin = mk_user(db, "a@x.vn", "Admin")
    op = mk_user(db, "o@x.vn", "Operator")
    ha, ho = auth(client, "a@x.vn"), auth(client, "o@x.vn")
    assert client.patch(f"/api/users/{admin.id}", json={"status": "disabled"}, headers=ha).status_code == 409
    assert client.patch(f"/api/users/{op.id}", json={"status": "disabled"}, headers=ha).status_code == 200
    assert client.get("/api/me", headers=ho).status_code == 401
    assert login(client, "o@x.vn").status_code == 403


def test_telemetry_aggregation_and_limits(client, db):
    mk_user(db, "a@x.vn", "Admin")
    d = mk_device(db, "wms-001")
    for i in range(3):
        add_tel(db, d, seq=i, secs_ago=10 + i)
    h = auth(client, "a@x.vn")
    body = client.get(f"/api/devices/{d.id}/telemetry", params={"interval": "1m"}, headers=h).json()
    assert body["interval"] == "1m" and sum(p["n"] for p in body["points"]) == 3
    raw = client.get(f"/api/devices/{d.id}/telemetry", headers=h).json()      # auto, 1h -> raw
    assert raw["interval"] == "raw" and len(raw["points"]) == 3
    too_long = {"from": (utcnow() - timedelta(hours=7)).isoformat() + "Z", "interval": "raw"}
    assert client.get(f"/api/devices/{d.id}/telemetry", params=too_long, headers=h).status_code == 422
    assert client.get(f"/api/devices/{d.id}/telemetry/latest", headers=h).json()["level_pct"] == 50.0


def test_csv_export_neutralizes_formulas_and_is_audited(client, db):
    mk_user(db, "a@x.vn", "Admin")
    d = mk_device(db, "wms-001")
    add_tel(db, d, seq=1, boot="=cmd()")
    h = auth(client, "a@x.vn")
    r = client.get(f"/api/devices/{d.id}/telemetry/export", headers=h)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    assert "'=cmd()" in r.text
    logs = client.get("/api/audit-logs", params={"action": "telemetry.export"}, headers=h).json()
    assert logs["total"] == 1


def test_audit_records_login_with_ip(client, db):
    mk_user(db, "a@x.vn", "Admin")
    h = auth(client, "a@x.vn")
    logs = client.get("/api/audit-logs", params={"action": "auth.login"}, headers=h).json()
    assert logs["total"] >= 1 and logs["items"][0]["user_email"] == "a@x.vn" and logs["items"][0]["ip"]


def test_each_node_type_reports_only_its_own_fields(client, db):
    mk_user(db, "a@x.vn", "Admin")
    tank, pipe = mk_device(db, "wms-tank-01", dtype="tank"), mk_device(db, "wms-pipe-01", dtype="pipe")
    add_tel(db, tank, seq=1, level=61.5)
    add_tel(db, pipe, seq=1)
    h = auth(client, "a@x.vn")
    t = client.get(f"/api/devices/{tank.id}/telemetry/latest", headers=h).json()
    p = client.get(f"/api/devices/{pipe.id}/telemetry/latest", headers=h).json()
    assert t["device_type"] == "tank" and t["level_pct"] == 61.5 and t["flow_lpm"] is None and t["pump_on"] is None
    assert p["device_type"] == "pipe" and p["flow_lpm"] == 1.0 and p["pump_on"] is False and p["level_pct"] is None
    series = client.get(f"/api/devices/{pipe.id}/telemetry", params={"interval": "1m"}, headers=h).json()
    point = series["points"][0]
    assert series["device_type"] == "pipe" and point["flow_lpm"] == 1.0 and point["pump_on"] is False
    assert point["level_pct"] is None
    csv = client.get(f"/api/devices/{tank.id}/telemetry/export", headers=h).text.splitlines()
    assert csv[0].split(",") == ["ts", "received_at", "boot_id", "seq", "distance_cm", "level_pct", "flow_lpm",
                                 "flow_total_l", "pump_on", "rssi"]
    assert csv[1].split(",")[4:9] == ["10.0", "61.5", "", "", ""]       # ô trống khi trường không áp dụng cho node bồn
