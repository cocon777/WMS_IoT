from sqlalchemy import func, select
from app.models import Device, DeviceConfig, Site, Telemetry
from scripts import init_hardware


def test_real_inventory_is_idempotent_has_safe_defaults_and_preserves_existing_state(db):
    init_hardware.main()
    devices = list(db.scalars(select(Device)))
    assert len(devices) == 2
    assert {d.type for d in devices} == {"tank", "pipe"}
    assert {d.state for d in devices} == {"Registered"}
    assert len({d.site_id for d in devices}) == 1
    assert db.scalar(select(func.count()).select_from(Telemetry)) == 0
    configs = list(db.scalars(select(DeviceConfig)))
    assert all(c.value == "false" for c in configs if c.key == "auto_mode")
    assert all(float(c.value) == 8 for c in configs if c.key == "tank_height_cm")
    assert all(float(c.value) == 37.5 for c in configs if c.key == "low_pct")
    devices[0].state = "Maintenance"
    first_id = devices[0].id
    db.commit()
    init_hardware.main()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Device)) == 2
    assert db.scalar(select(func.count()).select_from(Site)) == 1
    assert db.get(Device, first_id).state == "Maintenance"
