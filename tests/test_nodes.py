"""Ingest theo loại node: node bồn gửi mực nước, node ống gửi lưu lượng và trạng thái bơm."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import events, ingest
from app.models import Telemetry
from test_commands import mk_dev, mk_pair

TANK = {"distance_cm": 10, "level_pct": 72.5}
PIPE = {"flow_lpm": 3.2, "flow_total_l": 1.5, "pump_on": True}


def send(code, seq=1, age_s=0, **fields):
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"device_id": code, "boot_id": "b1", "seq": seq, "ts": ts, "rssi": -60, **fields}
    ingest.handle_message(f"wms/{code}/telemetry", json.dumps(payload).encode())


def rows(db):
    db.expire_all()
    return db.scalars(select(Telemetry).order_by(Telemetry.id)).all()


def test_each_node_type_stores_only_its_own_fields(db):
    mk_pair(db)
    send("wms-tank-01", **TANK)
    send("wms-pipe-01", **PIPE)
    t, p = rows(db)
    assert (t.distance_cm, t.level_pct, t.flow_lpm, t.flow_total_l, t.pump_on) == (10, 72.5, None, None, None)
    assert (p.flow_lpm, p.flow_total_l, p.pump_on, p.level_pct, p.distance_cm) == (3.2, 1.5, True, None, None)


def test_fields_of_the_other_node_type_are_ignored_not_stored(db):
    mk_pair(db)
    send("wms-tank-01", **TANK, flow_lpm=9, flow_total_l=9, pump_on=True)          # node bồn không có bơm hay lưu lượng
    send("wms-pipe-01", **PIPE, level_pct=50, distance_cm=5)
    t, p = rows(db)
    assert (t.flow_lpm, t.flow_total_l, t.pump_on) == (None, None, None)
    assert (p.level_pct, p.distance_cm) == (None, None)


@pytest.mark.parametrize("code,fields", [
    ("wms-tank-01", {"level_pct": 72.5}),                                  # thiếu distance_cm
    ("wms-tank-01", {"distance_cm": 10}),                                  # thiếu level_pct
    ("wms-tank-01", PIPE),                                                 # gửi trường của node ống
    ("wms-pipe-01", {"flow_lpm": 3.2, "flow_total_l": 1.5}),              # thiếu pump_on
    ("wms-pipe-01", {"flow_lpm": 3.2, "pump_on": True}),                   # thiếu flow_total_l
    ("wms-pipe-01", TANK),                                                 # gửi trường của node bồn
])
def test_missing_required_fields_for_the_node_type_are_rejected(db, code, fields):
    mk_pair(db)
    send(code, **fields)
    assert rows(db) == []


@pytest.mark.parametrize("code,fields", [
    ("wms-tank-01", {"distance_cm": 10, "level_pct": 999}),
    ("wms-tank-01", {"distance_cm": -1, "level_pct": 50}),
    ("wms-pipe-01", {**PIPE, "flow_lpm": -1}),
    ("wms-pipe-01", {**PIPE, "flow_lpm": 500}),
    ("wms-pipe-01", {**PIPE, "flow_total_l": -5}),
])
def test_out_of_range_values_are_rejected(db, code, fields):
    mk_pair(db)
    send(code, **fields)
    assert rows(db) == []


def test_telemetry_event_carries_node_type_and_site(db):
    site, tank, pipe = mk_pair(db)
    seen = []
    events.set_event_callback(lambda e, p: seen.append((e, p)))
    try:
        send("wms-tank-01", **TANK)
        send("wms-pipe-01", **PIPE)
    finally:
        events.set_event_callback(lambda e, p: None)
    t, p = [d for e, d in seen if e == "telemetry"]
    assert t["type"] == "tank" and t["site_id"] == site.id and t["level_pct"] == 72.5 and t["flow_lpm"] is None
    assert p["type"] == "pipe" and p["site_id"] == site.id and p["pump_on"] is True and p["level_pct"] is None


def test_low_level_works_end_to_end_through_ingest(db, alert_env):
    mk_pair(db)
    for i in range(5):                                                      # mực nước thấp 20 giây, cách nhau 5 giây
        send("wms-tank-01", seq=i, age_s=20 - 5 * i, **{"distance_cm": 22, "level_pct": 10})
    topic, payload, _ = alert_env.publisher.published[0]
    assert topic == "wms/wms-pipe-01/cmd" and payload["value"] == "on"     # tự bật bơm ở node ống của cùng site


def test_a_tank_without_a_pipe_node_in_its_site_cannot_start_a_pump(db, alert_env):
    mk_dev(db, "wms-tank-01", dtype="tank")
    for i in range(5):
        send("wms-tank-01", seq=i, age_s=20 - 5 * i, **{"distance_cm": 22, "level_pct": 10})
    assert alert_env.publisher.published == []
