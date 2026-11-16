"""Chế độ SQLite (mặc định của backend khi DATABASE_URL để trống)."""
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import device_params, ingest, retention
from app.config import Settings, settings
from app.db import engine, session_scope, utcnow
from app.models import Device, DeviceConfig, Site, Telemetry
from scripts import seed_dev
from test_commands import mk_dev


def telemetry_row(device_id, boot="b", seq=0, age_days=0):
    ts = utcnow() - timedelta(days=age_days)
    return Telemetry(device_id=device_id, boot_id=boot, seq=seq, ts=ts, received_at=ts, distance_cm=10, level_pct=50, rssi=-60)


def test_empty_database_url_falls_back_to_a_sqlite_file():
    cfg = Settings(database_url="", _env_file=None)
    assert cfg.is_sqlite and cfg.database_url.startswith("sqlite:///") and cfg.database_url.endswith("/wms.db")
    assert not Settings(database_url="mysql+pymysql://u:p@h/db", _env_file=None).is_sqlite


def test_tests_run_in_sqlite_mode():
    assert settings.is_sqlite


def test_pragmas_are_applied_to_every_connection():
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_foreign_keys_are_enforced(db):
    with pytest.raises(IntegrityError):
        with session_scope() as s:
            s.add(telemetry_row(device_id=999))


def test_concurrent_writers_do_not_hit_database_locked(db):
    dev = mk_dev(db)
    errors = []

    def worker(k):
        try:
            for i in range(25):
                with session_scope() as s:
                    s.add(telemetry_row(dev.id, boot=f"t{k}", seq=i))
        except Exception as e:          # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Telemetry)) == 200


def test_duplicate_telemetry_is_dropped_through_the_savepoint_path(db):
    dev = mk_dev(db)
    payload = {"device_id": "wms-001", "boot_id": "b1", "seq": 7,
               "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "flow_lpm": 0, "flow_total_l": 1, "pump_on": False}
    for _ in range(3):
        ingest.handle_message("wms/wms-001/telemetry", json.dumps(payload).encode())
    ingest.handle_message("wms/wms-001/telemetry", json.dumps({**payload, "seq": 8}).encode())
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Telemetry).where(Telemetry.device_id == dev.id)) == 2
    assert db.get(Device, dev.id).last_seen is not None     # phần còn lại của giao dịch (last_seen) vẫn được lưu


def test_purge_old_telemetry_keeps_recent_rows(db, monkeypatch):
    dev = mk_dev(db)
    db.add_all([telemetry_row(dev.id, seq=i, age_days=100 + i) for i in range(5)]
               + [telemetry_row(dev.id, seq=100 + i, age_days=i) for i in range(3)])
    db.commit()
    assert retention.purge_old_telemetry() == 5
    assert retention.purge_old_telemetry() == 0
    # A row created in this same clock tick can equal cutoff (strict '<').
    cutoff = utcnow() + timedelta(seconds=1)
    monkeypatch.setattr(retention, "utcnow", lambda: cutoff)
    assert retention.purge_old_telemetry(days=0, batch=2) == 3          # nhiều lô liên tiếp
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Telemetry)) == 0


def test_seed_is_idempotent_and_creates_a_two_node_system(db):
    seed_dev.main()
    seed_dev.main()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Site)) == 1
    devices = {d.device_code: d for d in db.scalars(select(Device))}
    assert set(devices) == {"wms-tank-01", "wms-pipe-01"}
    assert devices["wms-tank-01"].type == "tank" and devices["wms-pipe-01"].type == "pipe"
    assert devices["wms-tank-01"].site_id == devices["wms-pipe-01"].site_id is not None
    assert all(d.state == "Active" for d in devices.values())
    assert db.scalar(select(func.count()).select_from(DeviceConfig)) == 2 * len(device_params.DEFAULTS)
    assert db.scalar(select(func.count()).select_from(Telemetry)) == 2 * seed_dev.SAMPLES
    lo, hi = db.execute(select(func.min(Telemetry.level_pct), func.max(Telemetry.level_pct))).one()
    assert 20 <= lo and hi <= 90                                                    # mực nước (chỉ node bồn có)
    pipe_rows = db.scalars(select(Telemetry).where(Telemetry.device_id == devices["wms-pipe-01"].id)).all()
    assert all(r.level_pct is None and r.flow_lpm is not None and r.pump_on is not None for r in pipe_rows)
