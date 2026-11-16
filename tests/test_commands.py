import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import commands, events, ingest, lifecycle
from app.config import settings
from app.db import utcnow
from app.models import AuditLog, Command
from test_api import auth, mk_user


def mk_dev(db, code="wms-001", state="Active", online=True, dtype="pipe", site_id=None):
    """Mặc định là node ống (pipe): chỉ node ống nhận lệnh bơm."""
    d = lifecycle.create_device(db, device_code=code, name=code, hw_version="v1", device_type=dtype,
                                site_id=site_id, actor_id=None, ip="t")
    d.state, d.online = state, online
    db.commit()
    return d


def setup_operator(client, db, dev, email="o@x.vn"):
    """Admin + Operator được gán dev; trả header của Operator."""
    if not db.scalars(select(AuditLog.id).where(AuditLog.action == "user.create")).first():
        mk_user(db, "a@x.vn", "Admin")
    op = mk_user(db, email, "Operator")
    r = client.put(f"/api/users/{op.id}/devices", json={"device_ids": [dev.id]}, headers=auth(client, "a@x.vn"))
    assert r.status_code == 200
    return auth(client, email)


def send(client, h, dev, **body):
    return client.post(f"/api/devices/{dev.id}/commands", json=body or {"value": "on"}, headers=h)


def ack(code, cmd_id, result="ok", reason=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ingest.handle_message(f"wms/{code}/ack",
                          json.dumps({"cmd_id": cmd_id, "result": result, "reason": reason, "ts": ts}).encode())


def status_of(db, cmd_id):
    db.expire_all()
    return db.scalars(select(Command).where(Command.cmd_id == cmd_id)).one()


def test_send_publishes_cmd_qos1(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    r = send(client, h, d, value="on")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "sent" and body["duration_s"] == settings.pump_default_duration_s
    topic, payload, qos = publisher.published[0]
    assert topic == "wms/wms-001/cmd" and qos == 1
    assert payload["cmd_id"] == body["cmd_id"] and payload["action"] == "pump"
    assert payload["value"] == "on" and payload["duration_s"] == 60 and payload["issued_at"].endswith("Z")


def test_off_has_no_duration(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    assert send(client, h, d, value="off", duration_s=30).status_code == 202
    assert "duration_s" not in publisher.published[0][1]


def test_viewer_forbidden_and_other_operator_gets_404(client, db, publisher):
    d = mk_dev(db)
    setup_operator(client, db, d)
    mk_user(db, "v@x.vn", "Viewer")
    other = mk_user(db, "o2@x.vn", "Operator")
    assert send(client, auth(client, "v@x.vn"), d).status_code == 403
    assert send(client, auth(client, "o2@x.vn"), d).status_code == 404       # S1 với lệnh
    assert other and publisher.published == []


@pytest.mark.parametrize("state,online", [("Offline", False), ("Maintenance", False), ("Fault", True),
                                          ("Provisioned", False), ("Active", False)])
def test_blocked_unless_active_and_online(client, db, publisher, state, online):
    d = mk_dev(db, state=state, online=online)
    h = setup_operator(client, db, d)
    assert send(client, h, d).status_code == 409
    assert publisher.published == []


def test_duration_over_limit_rejected(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    r = send(client, h, d, value="on", duration_s=settings.pump_max_duration_s + 1)
    assert r.status_code == 422 and publisher.published == []


def test_second_command_blocked_while_pending(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    assert send(client, h, d).status_code == 202
    assert send(client, h, d, value="on").status_code == 409
    assert len(publisher.published) == 1


def test_off_is_allowed_while_pending_and_when_fault(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    assert send(client, h, d, value="on").status_code == 202
    assert send(client, h, d, value="off").status_code == 202       # lệnh tắt luôn được gửi
    d.state = "Fault"
    db.commit()
    assert send(client, h, d, value="off").status_code == 202       # kể cả khi thiết bị Fault
    assert send(client, h, d, value="on").status_code == 409


def test_ack_ok_updates_command_audit_and_emits_event(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    cmd_id = send(client, h, d).json()["cmd_id"]
    seen = []
    events.set_event_callback(lambda e, p: seen.append((e, p)))
    try:
        ack("wms-001", cmd_id)
    finally:
        events.set_event_callback(lambda e, p: None)
    c = status_of(db, cmd_id)
    assert c.status == "ok" and c.acked_at is not None
    assert seen and seen[0][0] == "command_result" and seen[0][1]["status"] == "ok"
    assert db.scalars(select(AuditLog).where(AuditLog.action == "command.ack")).first() is not None
    got = client.get(f"/api/devices/{d.id}/commands/{cmd_id}", headers=h).json()
    assert got["status"] == "ok" and got["acked_at"].endswith("Z")


def test_ack_fail_keeps_reason(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    cmd_id = send(client, h, d).json()["cmd_id"]
    ack("wms-001", cmd_id, result="fail", reason="tank_full")
    c = status_of(db, cmd_id)
    assert c.status == "fail" and c.reason == "tank_full"


def test_ack_from_other_device_is_ignored(client, db, publisher):
    d = mk_dev(db)
    mk_dev(db, code="wms-002")
    h = setup_operator(client, db, d)
    cmd_id = send(client, h, d).json()["cmd_id"]
    ack("wms-002", cmd_id)
    assert status_of(db, cmd_id).status == "sent"


def test_duplicate_and_invalid_acks_ignored(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    cmd_id = send(client, h, d).json()["cmd_id"]
    ack("wms-001", cmd_id, result="maybe")                  # sai schema
    assert status_of(db, cmd_id).status == "sent"
    ack("wms-001", cmd_id, result="ok")
    ack("wms-001", cmd_id, result="fail", reason="late-dup")    # trùng, không được ghi đè
    c = status_of(db, cmd_id)
    assert c.status == "ok" and c.reason == ""


def test_timeout_then_late_ack(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    cmd_id = send(client, h, d).json()["cmd_id"]
    c = status_of(db, cmd_id)
    c.sent_at = utcnow() - timedelta(seconds=settings.command_timeout_s + 1)
    db.commit()
    assert commands.mark_timed_out() == 1
    assert status_of(db, cmd_id).status == "timeout"
    ack("wms-001", cmd_id)                                  # thiết bị vẫn chạy lệnh trong TTL
    c = status_of(db, cmd_id)
    assert c.status == "ok" and "muộn" in c.reason


def test_publish_failure_marks_command_failed(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    publisher.fail = True
    assert send(client, h, d).status_code == 502
    db.expire_all()
    assert db.scalars(select(Command)).one().status == "fail"
    publisher.fail = False
    assert send(client, h, d).status_code == 202            # không bị kẹt vì lệnh cũ


def test_history_list_has_user_email(client, db, publisher):
    d = mk_dev(db)
    h = setup_operator(client, db, d)
    send(client, h, d)
    items = client.get(f"/api/devices/{d.id}/commands", headers=h).json()
    assert len(items) == 1 and items[0]["user_email"] == "o@x.vn"
    mk_user(db, "v@x.vn", "Viewer")
    assert client.get(f"/api/devices/{d.id}/commands", headers=auth(client, "v@x.vn")).status_code == 403


def mk_site(db, name="Nhà mẫu"):
    return lifecycle.create_site(db, name=name, description="", actor_id=None, ip="t")


def mk_pair(db, state="Active", online=True):
    """Một site có node bồn wms-tank-01 và node ống wms-pipe-01, cả hai Active và online."""
    site = mk_site(db)
    tank = mk_dev(db, "wms-tank-01", state, online, dtype="tank", site_id=site.id)
    pipe = mk_dev(db, "wms-pipe-01", state, online, dtype="pipe", site_id=site.id)
    return site, tank, pipe


def test_tank_node_cannot_receive_pump_commands(client, db, publisher):
    tank = mk_dev(db, "wms-tank-01", dtype="tank")
    h = setup_operator(client, db, tank)
    r = send(client, h, tank, value="on")
    assert r.status_code == 409 and "node ống" in r.json()["detail"]
    assert send(client, h, tank, value="off").status_code == 409        # kể cả lệnh tắt
    assert publisher.published == []
