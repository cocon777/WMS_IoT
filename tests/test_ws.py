import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from app import events, ingest
from app.config import settings
from app.db import utcnow
from app.realtime import hub
from test_api import auth, mk_user
from test_commands import mk_dev, setup_operator

pytestmark = pytest.mark.timeout(30)       # không để test WebSocket treo vô hạn


@pytest.fixture
def rt(client, db, monkeypatch):
    hub.reset()
    events.set_event_callback(hub.publish)          # giống lifespan: sự kiện nội bộ -> hub
    monkeypatch.setattr(settings, "ws_revalidate_s", 0.2)
    monkeypatch.setattr(settings, "ws_auth_timeout_s", 0.5)
    yield client
    events.set_event_callback(lambda e, p: None)
    hub.reset()


def until_closed(ws):
    msgs = []
    while True:
        try:
            msgs.append(ws.receive_json())
        except WebSocketDisconnect as e:
            return msgs, e.code


def ev(device_id, **extra):
    return {"device_id": device_id, "device_code": f"d{device_id}", **extra}


def test_repeated_normal_disconnects_release_hub_connections(rt, db):
    d = mk_dev(db)
    headers = setup_operator(rt, db, d)
    for _ in range(20):
        with rt.websocket_connect('/ws', headers=headers) as ws:
            assert ws.receive_json()['event'] == 'ready'
        assert hub.count() == 0


def assign(client, user, dev):
    r = client.put(f"/api/users/{user.id}/devices", json={"device_ids": [dev.id]}, headers=auth(client, "a@x.vn"))
    assert r.status_code == 200


def iso(dt):
    return dt.isoformat() + "Z"


def test_header_auth_then_real_telemetry_push(rt, db):
    d = mk_dev(db)
    ho = setup_operator(rt, db, d)
    with rt.websocket_connect("/ws", headers=ho) as ws:
        ready = ws.receive_json()
        assert ready["event"] == "ready" and ready["data"]["role"] == "Operator"
        assert ready["data"]["device_ids"] == [d.id] and "command_result" in ready["data"]["events"]
        payload = {"device_id": "wms-001", "boot_id": "b1", "seq": 1,
                   "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "flow_lpm": 3.2, "flow_total_l": 1, "pump_on": True}
        ingest.handle_message("wms/wms-001/telemetry", json.dumps(payload).encode())
        msg = ws.receive_json()
        assert msg["event"] == "telemetry" and msg["data"]["device_code"] == "wms-001"
        assert msg["data"]["flow_lpm"] == 3.2 and msg["data"]["pump_on"] is True and msg["sent_at"].endswith("Z")
        assert msg["data"]["type"] == "pipe" and msg["data"]["level_pct"] is None


def test_first_message_auth_for_browsers(rt, db):
    d = mk_dev(db)
    ho = setup_operator(rt, db, d)
    token = ho["Authorization"].split()[1]
    with rt.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["event"] == "ready"


def test_bad_missing_or_expired_credentials_are_rejected(rt, db):
    d = mk_dev(db)
    user = mk_user(db, "o@x.vn", "Operator")
    with rt.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "abc"})
        msgs, code = until_closed(ws)
        assert code == 4401 and msgs[0]["event"] == "error" and msgs[0]["data"]["code"] == "unauthorized"
    with rt.websocket_connect("/ws") as ws:                     # không gửi gì: hết thời gian chờ auth
        assert until_closed(ws)[1] == 4401
    with rt.websocket_connect("/ws") as ws:                     # sai kiểu thông điệp đầu tiên
        ws.send_json({"type": "subscribe"})
        assert until_closed(ws)[1] == 4401
    expired = jwt.encode({"sub": str(user.id), "tv": 0, "exp": utcnow() - timedelta(minutes=1)},
                         settings.jwt_secret, algorithm="HS256")
    with rt.websocket_connect("/ws", headers={"Authorization": f"Bearer {expired}"}) as ws:
        assert until_closed(ws)[1] == 4401
    assert d and hub.count() == 0


def test_operator_only_receives_assigned_devices(rt, db):
    d1, d2 = mk_dev(db), mk_dev(db, "wms-002")
    ho = setup_operator(rt, db, d1)
    with rt.websocket_connect("/ws", headers=ho) as ws:
        ws.receive_json()
        events.emit("telemetry", ev(d2.id, marker=1))        # ngoài phạm vi: không được lọt qua (S1)
        events.emit("alert", ev(d2.id, marker=2))
        events.emit("telemetry", ev(d1.id, marker=3))
        assert ws.receive_json()["data"]["marker"] == 3


def test_admin_sees_every_device(rt, db):
    d1, d2 = mk_dev(db), mk_dev(db, "wms-002")
    setup_operator(rt, db, d1)
    with rt.websocket_connect("/ws", headers=auth(rt, "a@x.vn")) as ws:
        ready = ws.receive_json()
        assert ready["data"]["device_ids"] is None
        events.emit("telemetry", ev(d2.id, marker=1))
        assert ws.receive_json()["data"]["marker"] == 1


def test_viewer_never_receives_commands_or_config(rt, db):
    d = mk_dev(db)
    setup_operator(rt, db, d)
    viewer = mk_user(db, "v@x.vn", "Viewer")
    assign(rt, viewer, d)
    with rt.websocket_connect("/ws", headers=auth(rt, "v@x.vn")) as ws:
        ready = ws.receive_json()
        assert "command_result" not in ready["data"]["events"] and "config" not in ready["data"]["events"]
        events.emit("command_result", ev(d.id, status="ok"))
        events.emit("config", ev(d.id, version=2))
        events.emit("config_applied", ev(d.id, applied_version=2))
        events.emit("alert", ev(d.id, marker=1))
        assert ws.receive_json()["event"] == "alert"


def test_events_without_device_id_are_never_broadcast(rt, db):
    d = mk_dev(db)
    ho = setup_operator(rt, db, d)
    with rt.websocket_connect("/ws", headers=ho) as ws:
        ws.receive_json()
        events.emit("telemetry", {"marker": 1})                  # thiếu device_id
        events.emit("telemetry", ev(d.id, marker=2))
        assert ws.receive_json()["data"]["marker"] == 2


def test_subscribe_filters_and_validates(rt, db):
    d1, d2 = mk_dev(db), mk_dev(db, "wms-002")
    ho = setup_operator(rt, db, d1)
    with rt.websocket_connect("/ws", headers=ho) as ws:
        ws.receive_json()
        ws.send_json({"type": "subscribe", "device_ids": [d2.id]})
        assert ws.receive_json()["data"]["code"] == "forbidden_device"
        ws.send_json({"type": "subscribe", "events": ["nope"]})
        assert ws.receive_json()["data"]["code"] == "unknown_event"
        ws.send_json({"type": "subscribe", "device_ids": "all"})
        assert ws.receive_json()["data"]["code"] == "bad_message"
        ws.send_json({"type": "subscribe", "events": ["alert"]})
        assert ws.receive_json()["event"] == "subscribed"
        events.emit("telemetry", ev(d1.id, marker=1))
        events.emit("alert", ev(d1.id, marker=2))
        assert ws.receive_json()["data"]["marker"] == 2
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["event"] == "pong"
        ws.send_text("không phải json")
        assert ws.receive_json()["data"]["code"] == "bad_message"


def test_admin_can_narrow_to_one_device(rt, db):
    d1, d2 = mk_dev(db), mk_dev(db, "wms-002")
    setup_operator(rt, db, d1)
    with rt.websocket_connect("/ws", headers=auth(rt, "a@x.vn")) as ws:
        ws.receive_json()
        ws.send_json({"type": "subscribe", "device_ids": [d1.id]})
        assert ws.receive_json()["event"] == "subscribed"
        events.emit("telemetry", ev(d2.id, marker=1))
        events.emit("telemetry", ev(d1.id, marker=2))
        assert ws.receive_json()["data"]["marker"] == 2


def test_logout_closes_open_connection(rt, db):
    mk_user(db, "a@x.vn", "Admin")
    h = auth(rt, "a@x.vn")
    with rt.websocket_connect("/ws", headers=h) as ws:
        ws.receive_json()
        assert rt.post("/api/auth/logout", headers=h).status_code == 204
        msgs, code = until_closed(ws)
        assert code == 4401 and msgs[-1]["data"]["code"] == "session_revoked"


def test_scope_changes_apply_to_open_connections(rt, db):
    d = mk_dev(db)
    setup_operator(rt, db, d)
    op2 = mk_user(db, "o2@x.vn", "Operator")                    # chưa được gán thiết bị nào
    with rt.websocket_connect("/ws", headers=auth(rt, "o2@x.vn")) as ws:
        assert ws.receive_json()["data"]["device_ids"] == []
        events.emit("telemetry", ev(d.id, marker=1))             # chưa có quyền: bị chặn
        assign(rt, op2, d)
        time.sleep(0.8)                                          # đợi chu kỳ kiểm tra lại phạm vi
        events.emit("telemetry", ev(d.id, marker=2))
        assert ws.receive_json()["data"]["marker"] == 2


def test_oversize_message_and_connection_limits(rt, db, monkeypatch):
    d = mk_dev(db)
    ho = setup_operator(rt, db, d)
    with rt.websocket_connect("/ws", headers=ho) as ws:
        ws.receive_json()
        ws.send_text("x" * 5000)
        assert until_closed(ws)[1] == 1009
    monkeypatch.setattr(settings, "ws_max_per_user", 1)
    with rt.websocket_connect("/ws", headers=ho) as first:
        first.receive_json()
        with rt.websocket_connect("/ws", headers=ho) as second:
            msgs, code = until_closed(second)
            assert code == 1013 and msgs[0]["data"]["code"] == "too_many_connections"


def test_origin_allow_list(rt, db, monkeypatch):
    d = mk_dev(db)
    ho = setup_operator(rt, db, d)
    monkeypatch.setattr(settings, "ws_allowed_origins", "https://app.example.vn")
    with pytest.raises(WebSocketDisconnect):
        with rt.websocket_connect("/ws", headers={**ho, "Origin": "https://evil.example"}):
            pass
    with rt.websocket_connect("/ws", headers={**ho, "Origin": "https://app.example.vn"}) as ws:
        assert ws.receive_json()["event"] == "ready"


def test_user_initiated_state_change_is_announced(rt, db, broker):
    from app import lifecycle
    mk_user(db, "a@x.vn", "Admin")
    with rt.websocket_connect("/ws", headers=auth(rt, "a@x.vn")) as ws:
        ws.receive_json()
        dev = lifecycle.create_device(db, device_code="wms-009", name="x", hw_version="v1", device_type="tank",
                                    actor_id=None, ip="t")
        msg = ws.receive_json()
        assert msg["event"] == "device_state" and msg["data"]["state"] == "Registered"
        lifecycle.provision(db, broker, dev.id, actor_id=None, ip="t")
        assert ws.receive_json()["data"]["state"] == "Provisioned"


def test_latency_stats_endpoint(rt, db):
    mk_user(db, "a@x.vn", "Admin")
    mk_user(db, "v@x.vn", "Viewer")
    ha, hv = auth(rt, "a@x.vn"), auth(rt, "v@x.vn")
    now = utcnow()
    for _ in range(3):
        events.emit("telemetry", {"device_id": 1, "ts": iso(now - timedelta(seconds=2)),
                                  "received_at": iso(now - timedelta(seconds=1))})
    body = rt.get("/api/metrics/latency", headers=ha).json()
    assert body["samples"] == 3 and body["end_to_push_ms"]["avg"] >= 2000
    assert body["backend_to_push_ms"]["avg"] >= 1000 and body["end_to_push_ms"]["p95"] >= body["end_to_push_ms"]["avg"]
    assert rt.get("/api/metrics/latency", headers=hv).status_code == 403
    assert rt.delete("/api/metrics/latency", headers=ha).status_code == 204
    assert rt.get("/api/metrics/latency", headers=ha).json()["samples"] == 0
