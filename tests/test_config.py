import json

import pytest
from sqlalchemy import select

from app import ingest
from app.config import settings
from app.models import DeviceConfig
from test_alerts import Timeline, all_alerts
from test_api import auth, mk_user
from test_commands import mk_dev, setup_operator

DEFAULT_CFG = {"sample_interval_s": 5, "tank_height_cm": 25, "low_pct": 20, "high_pct": 90,
               "pump_max_run_s": 120, "auto_mode": True, "leak_flow_lpm": 0.3, "leak_minutes": 10}


def url(dev):
    return f"/api/devices/{dev.id}/config"


def put(client, h, dev, **body):
    return client.put(url(dev), json=body, headers=h)


def test_get_returns_defaults_limits_and_enforces_roles(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    body = client.get(url(d), headers=ho).json()
    assert body["version"] == 0 and body["config"] == DEFAULT_CFG and body["sync_status"] == "default"
    assert body["limits"]["low_pct"]["max"] == 100 and body["limits"]["pump_max_run_s"]["max"] == settings.pump_max_duration_s
    mk_user(db, "v@x.vn", "Viewer")
    mk_user(db, "o2@x.vn", "Operator")
    assert client.get(url(d), headers=auth(client, "v@x.vn")).status_code == 403
    assert client.get(url(d), headers=auth(client, "o2@x.vn")).status_code == 404         # ngoài phạm vi (S1)
    assert put(client, auth(client, "o2@x.vn"), d, low_pct=25).status_code == 404
    assert client.get(url(d)).status_code == 401


def test_put_saves_bumps_version_and_publishes_retained(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    r = put(client, ho, d, low_pct=25, sample_interval_s=10)
    body = r.json()
    assert r.status_code == 200 and body["version"] == 1 and body["delivery"] == "published"
    assert body["changed"] == ["low_pct", "sample_interval_s"] and body["updated_by"] == "o@x.vn"
    assert body["updated_at"].endswith("Z") or body["updated_at"].endswith("+00:00")
    topic, payload, qos = publisher.published[0]
    assert (topic, qos, publisher.retain_flags[0]) == ("wms/wms-001/config", 1, True)
    assert payload == {"version": 1, **DEFAULT_CFG, "low_pct": 25, "sample_interval_s": 10}   # bản đầy đủ, đúng thứ tự khóa
    assert list(payload)[:3] == ["version", "sample_interval_s", "tank_height_cm"]


def test_row_versions_track_last_change_per_key(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    put(client, ho, d, low_pct=25, sample_interval_s=10)                  # v1
    assert put(client, ho, d, low_pct=30).json()["version"] == 2          # v2
    db.expire_all()
    assert {r.key: r.version for r in db.scalars(select(DeviceConfig))} == {"low_pct": 2, "sample_interval_s": 1}
    assert publisher.published[-1][1]["version"] == 2 and publisher.published[-1][1]["sample_interval_s"] == 10


def test_noop_put_does_not_bump_or_publish(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    put(client, ho, d, low_pct=25)
    n = len(publisher.published)
    r = put(client, ho, d, low_pct=25, auto_mode=True)                    # trùng giá trị hiện tại
    assert r.status_code == 200 and r.json()["delivery"] == "unchanged" and r.json()["version"] == 1
    assert len(publisher.published) == n


@pytest.mark.parametrize("body", [
    {}, {"low_pct": -1}, {"low_pct": 101}, {"tank_height_cm": 0}, {"sample_interval_s": 0},
    {"sample_interval_s": 5.5}, {"dry_run_s": 1},       # dry_run_s đã bị bỏ ở hệ thống 2 node: khóa lạ
    {"leak_flow_lpm": 0}, {"leak_flow_lpm": 11}, {"leak_minutes": 0}, {"leak_minutes": 121}, {"leak_minutes": 2.5}, {"pump_max_run_s": settings.pump_max_duration_s + 1},
    {"low_pct": 85},                                    # high 90 - low 85 < 10
    {"high_pct": 25},                                   # high 25 - low 20 < 10
    {"bogus": 1}, {"low_pct": "20"}, {"auto_mode": "true"}, {"sample_interval_s": True}, {"low_pct": None, "high_pct": None},
])
def test_invalid_config_is_rejected_and_nothing_is_published(client, db, publisher, body):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    assert put(client, ho, d, **body).status_code == 422
    assert publisher.published == []
    assert client.get(url(d), headers=ho).json()["version"] == 0


def test_expected_version_guards_concurrent_edits(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    assert put(client, ho, d, version=0, low_pct=25).status_code == 200
    assert put(client, ho, d, version=0, low_pct=30).status_code == 409   # người khác đã sửa
    assert put(client, ho, d, version=1, low_pct=30).status_code == 200


def test_publish_failure_keeps_saved_config_and_can_be_resent(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    publisher.fail = True
    r = put(client, ho, d, low_pct=25)
    assert r.status_code == 200 and r.json()["delivery"] == "failed" and r.json()["version"] == 1
    publisher.fail = False
    r = client.post(url(d) + "/publish", headers=ho)
    assert r.status_code == 200 and r.json()["delivery"] == "published"
    assert publisher.published[-1][1]["version"] == 1 and publisher.retain_flags[-1] is True


def test_cannot_publish_before_any_config_or_after_decommission(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    assert client.post(url(d) + "/publish", headers=ho).status_code == 409
    d.state = "Decommissioned"
    db.commit()
    assert put(client, ho, d, low_pct=25).status_code == 409
    assert client.get(url(d), headers=ho).status_code == 200              # vẫn xem được


def test_sync_status_follows_heartbeat_config_version(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    put(client, ho, d, low_pct=25)                                        # v1
    assert client.get(url(d), headers=ho).json()["sync_status"] == "unknown"
    ingest.handle_message("wms/wms-001/status", b'{"status":"online","config_version":1}')
    body = client.get(url(d), headers=ho).json()
    assert body["sync_status"] == "applied" and body["applied_version"] == 1
    put(client, ho, d, low_pct=30)                                        # v2: thiết bị chưa báo
    assert client.get(url(d), headers=ho).json()["sync_status"] == "pending"
    ingest.handle_message("wms/wms-001/status", json.dumps({"status": "online", "config_version": 2}).encode())
    assert client.get(url(d), headers=ho).json()["sync_status"] == "applied"


def test_new_threshold_reaches_alert_engine_immediately(client, db, publisher, alert_env):
    d = mk_dev(db, dtype="tank")           # ngưỡng mực nước thuộc cấu hình của node bồn
    ho = setup_operator(client, db, d)
    Timeline(d, 600).add(60)                    # nạp cache của engine với low_pct mặc định (20)
    put(client, ho, d, low_pct=25)
    Timeline(d, 20).add(22, n=5)                # 22% > 20 nhưng < 25 mới
    assert len(all_alerts(db, "LOW_LEVEL")) == 1


def test_pump_command_duration_is_limited_by_device_config(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    put(client, ho, d, pump_max_run_s=30)
    cmd = f"/api/devices/{d.id}/commands"
    assert client.post(cmd, json={"value": "on", "duration_s": 60}, headers=ho).status_code == 422
    r = client.post(cmd, json={"value": "on"}, headers=ho)                # mặc định 60 bị hạ xuống 30
    assert r.status_code == 202 and r.json()["duration_s"] == 30


def test_config_changes_are_audited_with_diff(client, db, publisher):
    d = mk_dev(db)
    ho = setup_operator(client, db, d)
    put(client, ho, d, low_pct=25)
    logs = client.get("/api/audit-logs", params={"action": "config.update"}, headers=auth(client, "a@x.vn")).json()
    assert logs["total"] == 1 and "low_pct 20.0->25.0" in logs["items"][0]["detail"] and "v0->v1" in logs["items"][0]["detail"]


def test_leak_settings_are_saved_and_published_to_the_pipe_node(client, db, publisher):
    d = mk_dev(db, "wms-pipe-01", dtype="pipe")
    ho = setup_operator(client, db, d)
    r = put(client, ho, d, leak_flow_lpm=0.5, leak_minutes=5)
    assert r.status_code == 200 and r.json()["changed"] == ["leak_flow_lpm", "leak_minutes"]
    topic, payload, qos = publisher.published[0]
    assert topic == "wms/wms-pipe-01/config" and payload["leak_flow_lpm"] == 0.5 and payload["leak_minutes"] == 5
    assert list(payload)[-2:] == ["leak_flow_lpm", "leak_minutes"] and "dry_run_s" not in payload
