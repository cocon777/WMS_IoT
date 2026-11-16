"""Full manual/AUTO cycles using real ingest, DB, alert engine and API; MQTT is fake."""
import json
from collections import defaultdict, deque
from datetime import timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app import alerts, commands, ingest
from app.db import utcnow
from app.models import Command
from test_alerts import all_alerts, set_config
from test_commands import mk_pair, setup_operator

PROFILES = Path(__file__).resolve().parents[1] / 'deployment/demo'


@pytest.fixture
def refill(db, client, publisher, alert_env, monkeypatch):
    monkeypatch.setattr(ingest, '_rate', defaultdict(deque))  # isolated simulated devices per test
    _, tank, pipe = mk_pair(db)
    clock = [utcnow()]
    for module in (alerts, commands, ingest):
        monkeypatch.setattr(module, 'utcnow', lambda: clock[0])
    for dev in (tank, pipe):
        set_config(db, dev, **json.loads((PROFILES / f'{dev.type}-config.json').read_text()))
    headers = setup_operator(client, db, pipe)
    alerts.set_publisher(publisher)
    seq = [0]

    def sample(dev, **fields):
        seq[0] += 1
        data = dict(device_id=dev.device_code, boot_id='refill-test', seq=seq[0],
                    ts=clock[0].replace(tzinfo=timezone.utc).isoformat(), **fields)
        ingest.handle_message(f'wms/{dev.device_code}/telemetry', json.dumps(data).encode())

    def tick(height=2.8, on=False, *, tank_sample=True):
        clock[0] += timedelta(seconds=1)
        if tank_sample:
            sample(tank, distance_cm=16.5-height, level_pct=min(100, height/8*100))
        sample(pipe, flow_lpm=1.08 if on else 0, flow_total_l=1.0, pump_on=on)

    def sent():
        return [payload for topic, payload, _ in publisher.published if topic.endswith('/cmd')]

    return tank, pipe, headers, tick, sent, clock


@pytest.mark.parametrize('automatic', [False, True])
def test_low_to_full_cycle_stops_at_exact_100_percent(refill, db, client, automatic):
    tank, pipe, headers, tick, sent, _ = refill
    set_config(db, tank, auto_mode=automatic)
    for _ in range(11):
        tick()
    assert len(all_alerts(db, 'LOW_LEVEL')) == 1
    if not automatic:
        assert sent() == []  # user may decide not to pump
        response = client.post(f'/api/devices/{pipe.id}/commands', headers=headers,
                               json={'value': 'on', 'duration_s': 60})
        assert response.status_code == 202, response.text
    assert len(sent()) == 1 and sent()[0]['value'] == 'on' and sent()[0]['duration_s'] == 60
    commands.handle_ack(pipe.device_code, {'cmd_id': sent()[0]['cmd_id'], 'result': 'ok'})
    # Simulated rising water from2.8 to8cm; watchdog60 is not the normal stop time.
    for i in range(1, 46):
        tick(2.8 + 5.2*i/46, True)
    assert [p['value'] for p in sent()] == ['on']
    tick(8, True)
    assert [p['value'] for p in sent()] == ['on', 'off']
    assert len(all_alerts(db, 'HIGH_LEVEL')) == 1
    tick(8, False)
    response = client.post(f'/api/devices/{pipe.id}/commands', headers=headers,
                           json={'value': 'on', 'duration_s': 60})
    assert response.status_code == 409  # no restart at full level


def test_low_3cm_boundary_and_hysteresis_preserve_faucet_residue(refill, db):
    _, _, _, tick, sent, _ = refill
    for height in (4.0, 3.0):
        for _ in range(11):
            tick(height)
    assert all_alerts(db, 'LOW_LEVEL') == []
    for _ in range(11):
        tick(2.8)
    low = all_alerts(db, 'LOW_LEVEL')
    assert len(low) == 1 and low[0].state == 'open'
    tick(3.3)
    assert all_alerts(db, 'LOW_LEVEL')[0].state == 'open'
    tick(3.5)
    assert all_alerts(db, 'LOW_LEVEL')[0].state == 'closed'
    assert sent() == []  # TAY remains manual even below the threshold.


def test_enabling_auto_with_an_existing_low_alert_starts_once(refill, db):
    tank, _, _, tick, sent, _ = refill
    for _ in range(11):
        tick()
    assert len(all_alerts(db, 'LOW_LEVEL')) == 1 and sent() == []
    set_config(db, tank, auto_mode=True)
    tick()
    assert len(sent()) == 1 and sent()[0]['value'] == 'on'
    # No repeated ON even if no telemetry confirms pump start / ACK never arrives.
    for _ in range(12):
        tick()
    assert len(sent()) == 1


def test_missing_tank_samples_stop_running_pump_and_block_new_on(refill, client, db):
    _, pipe, headers, tick, sent, _ = refill
    tick(4, True)
    for _ in range(6):
        tick(on=True, tank_sample=False)
    assert [p['value'] for p in sent()] == ['off']
    row = db.scalar(select(Command).where(Command.cmd_id == sent()[0]['cmd_id']))
    assert 'guard:STALE_LEVEL' in row.params_json
    response = client.post(f'/api/devices/{pipe.id}/commands', headers=headers,
                           json={'value': 'on', 'duration_s': 60})
    assert response.status_code == 409


def test_full_stop_retries_after_publish_failure(refill, publisher):
    _, _, _, tick, sent, _ = refill
    tick(7.9, True)
    publisher.fail = True
    tick(8, True)
    assert sent() == []
    publisher.fail = False
    for key in list(alerts._last_action):
        alerts._last_action[key] -= 3
    tick(8, True)
    assert [p['value'] for p in sent()] == ['off']


def test_queued_auto_on_is_cancelled_if_user_selects_manual(refill, db, monkeypatch):
    tank, _, _, tick, sent, _ = refill
    queued = []
    monkeypatch.setattr(alerts, '_submit', queued.append)
    set_config(db, tank, auto_mode=True)
    for _ in range(11):
        tick()
    assert len(queued) == 1 and sent() == []
    set_config(db, tank, auto_mode=False)
    queued[0]()
    assert sent() == []
