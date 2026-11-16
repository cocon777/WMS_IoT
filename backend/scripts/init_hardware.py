"""Create the real two-node inventory without fake telemetry or pre-activated devices."""
from sqlalchemy import select
from app.db import Base, SessionLocal, engine
from app.models import Device, DeviceConfig, Site
from app import device_params


def main():
    # SQLite dev creates schema; MySQL must already be migrated by TV3.
    from app.config import settings
    if settings.is_sqlite:
        Base.metadata.create_all(engine)
    with SessionLocal() as s:
        site = s.scalar(select(Site).where(Site.name == "Prototype TV1"))
        if site is None:
            site = Site(name="Prototype TV1", description="Hai ESP32 vat ly")
            s.add(site)
            s.flush()
        for code, role in (("wms-tank-01", "tank"), ("wms-pipe-01", "pipe")):
            dev = s.scalar(select(Device).where(Device.device_code == code))
            if dev is not None:
                print(f"KEEP {code} id={dev.id} state={dev.state}")
                continue
            dev = Device(device_code=code, name=f"Node {role} TV1", type=role, site_id=site.id,
                         state="Registered", hw_version="breadboard-v2", fw_version="")
            s.add(dev)
            s.flush()
            cfg = {**device_params.DEFAULTS, "tank_height_cm": 8.0, "auto_mode": False,
                   "pump_max_run_s": 60, "sample_interval_s": 1, "low_pct": 37.5,
                   "high_pct": 100.0, "leak_minutes": 1}
            for key, value in cfg.items():
                s.add(DeviceConfig(device_id=dev.id, key=key, value=device_params.store(value), version=1))
            print(f"CREATED {code} id={dev.id} Registered; provision via API, publish config v1")
        s.commit()


if __name__ == "__main__":
    main()
