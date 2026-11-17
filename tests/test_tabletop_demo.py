"""Exercise the reviewable demo payloads through the existing API and alert engine."""
import json
from pathlib import Path

from test_alerts import Rig, all_alerts
from test_commands import mk_pair, setup_operator

PROFILE = Path(__file__).resolve().parents[1] / "deployment" / "demo"


def test_tabletop_faucet_drop_triggers_tank_leak_with_zero_inlet_flow(client, db, publisher, alert_env, monkeypatch):
    _, tank, pipe = mk_pair(db)
    for dev in (tank, pipe):
        headers = setup_operator(client, db, dev, email=f"{dev.type}@demo.vn")
        config = json.loads((PROFILE / f"{dev.type}-config.json").read_text(encoding="utf-8"))
        response = client.put(f"/api/devices/{dev.id}/config", json=config, headers=headers)
        assert response.status_code == 200, response.text
        if dev.type == "tank":
            tank_headers = headers
    rules = json.loads((PROFILE / "tank-alert-rules.json").read_text(encoding="utf-8"))
    response = client.put(f"/api/devices/{tank.id}/alert-rules", json=rules, headers=tank_headers)
    assert response.status_code == 200, response.text
    # Real demo rule:5s settling +20s evidence, fresh paired samples.
    rig = Rig(tank, pipe, 0, step=1)
    monkeypatch.setattr('app.alerts.utcnow', lambda: rig.t)
    for second in range(26):
        height = 7.0 - 3.0 * second / 60
        rig.tick(height / 8.0 * 100, flow=0, pump=False)
    leaks = all_alerts(db, "LEAK_SUSPECT")
    assert len(leaks) == 1
    assert leaks[0].device_id == tank.id
    assert abs(leaks[0].value - 3.0) < 0.01
    # Faucet residue at 4cm is ABOVE the3cm LOW threshold.
    for _ in range(12):
        rig.tick(4.0 / 8.0 * 100, flow=0, pump=False)
    assert not all_alerts(db, "LOW_LEVEL")
    # The physical demo must remove more water to reach below3cm.
    for _ in range(12):
        rig.tick(2.8 / 8.0 * 100, flow=0, pump=False)
    assert any(a.device_id == tank.id for a in all_alerts(db, "LOW_LEVEL"))
    assert not any(topic.endswith("/cmd") for topic, _, _ in alert_env.publisher.published)
