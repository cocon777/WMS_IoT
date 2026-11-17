"""Read-only snapshot for physical-node troubleshooting; run inside backend.

PowerShell: Get-Content tools/diagnose_nodes.py -Raw | docker compose exec -T backend python -
Does not open serial ports, publish MQTT, change config or access credentials.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Command, Device, Telemetry


def main():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=3)
    result = {"captured_at_utc": now.isoformat() + "Z", "window_hours": 3, "devices": []}
    with SessionLocal() as session:
        devices = session.scalars(select(Device).where(
            Device.device_code.in_(["wms-tank-01", "wms-pipe-01"]))).all()
        for device in devices:
            boots = session.execute(select(
                Telemetry.boot_id, func.min(Telemetry.received_at), func.max(Telemetry.received_at),
                func.min(Telemetry.seq), func.max(Telemetry.seq), func.count(Telemetry.id),
            ).where(Telemetry.device_id == device.id, Telemetry.received_at >= cutoff)
                .group_by(Telemetry.boot_id).order_by(func.min(Telemetry.received_at))).all()
            latest = session.scalar(select(Telemetry).where(Telemetry.device_id == device.id)
                                    .order_by(Telemetry.ts.desc()).limit(1))
            result["devices"].append({
                "code": device.device_code, "state": device.state, "online": device.online,
                "last_seen_utc": device.last_seen, "firmware": device.fw_version,
                "applied_version": device.config_applied_version,
                "boots": [{"id": b, "first_received_utc": first, "last_received_utc": last,
                           "min_seq": lo, "max_seq": hi, "samples": count}
                          for b, first, last, lo, hi, count in boots],
                "latest": None if latest is None else {
                    k: getattr(latest, k) for k in ("ts", "received_at", "boot_id", "seq", "rssi",
                                                  "flow_total_l", "distance_cm", "level_pct")},
            })
        rows = session.execute(select(Command.sent_at, Command.acked_at, Command.status, Command.params_json)
                               .where(Command.sent_at >= cutoff).order_by(Command.sent_at)).all()
        result["commands"] = [{"sent_at_utc": sent, "acked_at_utc": acked, "status": status,
                               "params": json.loads(params)} for sent, acked, status, params in rows]
    result["limits"] = [
        "One boot_id means no restart observed in received telemetry; it cannot exclude resets that never reconnected.",
        "No serial reset reason or voltage measurement available; a brownout cannot be confirmed from this snapshot.",
        "Online/offline is the server's connection state, not a measurement of supply voltage or proof of reset.",
    ]
    print(json.dumps(result, default=str, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
