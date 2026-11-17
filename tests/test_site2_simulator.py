import time
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.broker_admin import get_broker_admin
from app.main import app
from app.models import Device, Telemetry
from app.schemas import TelemetryIn, missing_fields
from test_api import auth, mk_user
from test_commands import mk_pair
from tools.simulate_site2 import CODES, Simulation, prepare


def test_software_site_preparation_is_separate_idempotent_and_scoped(client, db, publisher, broker):
    physical_site, tank, pipe = mk_pair(db)
    mk_user(db, 'sim-admin@example.test', 'Admin')
    operator = mk_user(db, 'physical-op@example.test', 'Operator')
    client.headers.update(auth(client, 'sim-admin@example.test'))
    original = [(d.id, d.device_code, d.site_id, d.state) for d in (tank, pipe)]
    cache = {}
    app.dependency_overrides[get_broker_admin] = lambda: broker
    try:
        site = prepare(client, cache)
        prepare(client, cache)
        assert site['id'] != physical_site.id
        assert set(cache) == set(CODES.values())
        nodes = list(db.scalars(select(Device).where(Device.device_code.in_(CODES.values()))))
        assert len(nodes) == 2 and all(d.site_id == site['id'] for d in nodes)
        assert all(d.state == 'Provisioned' and not d.online for d in nodes)
        assert list(db.scalars(select(Telemetry))) == []  # no seeded/fabricated physical samples
        db.expire_all()
        assert [(d.id, d.device_code, d.site_id, d.state) for d in (tank, pipe)] == original
        client.put(f'/api/users/{operator.id}/devices', json={'device_ids': [tank.id, pipe.id]})
        scoped = auth(client, 'physical-op@example.test')
        assert [s['id'] for s in client.get('/api/sites', headers=scoped).json()] == [physical_site.id]
        for node in nodes:
            assert client.get(f'/api/devices/{node.id}/telemetry/latest', headers=scoped).status_code == 404
            assert client.get(f'/api/devices/{node.id}/config', headers=scoped).status_code == 404
    finally:
        app.dependency_overrides.pop(get_broker_admin, None)


def test_software_physics_moves_only_simulated_water_and_clamps_after_leak():
    normal = Simulation()
    normal.pump = True
    normal.deadline = time.monotonic() + 60
    assert normal.tick() == 1.08
    assert normal.level_cm > 2.8 and normal.total_l > 0
    leak = Simulation('leak')
    assert leak.tick(30) == 0
    assert abs(leak.level_cm - 5.5) < .001
    leak.tick(600)
    assert leak.level_cm == 4.0
    assert all(code.startswith('wms-sim-') for code in CODES.values())


@pytest.mark.parametrize('role', ['tank', 'pipe'])
def test_software_node_payload_matches_the_backend_contract(monkeypatch, role):
    from tools import simulate_site2
    fake = MagicMock()
    monkeypatch.setattr(simulate_site2.mqtt, 'Client', lambda *a, **kw: fake)
    node = simulate_site2.SoftwareNode(role, 'unit-test-only', 'unused-ca', 'localhost', 18883, Simulation())
    node.sample(0)
    topic, wire = fake.publish.call_args.args
    parsed = TelemetryIn.model_validate(json.loads(wire))
    assert parsed.device_id == CODES[role] and len(parsed.boot_id) <= 16
    assert not missing_fields(parsed, role)
    assert topic == f'wms/{CODES[role]}/telemetry'
