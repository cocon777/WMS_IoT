"""Fast physical-demo rules must reject noise and missing/off-state evidence."""
from datetime import timedelta

from test_alerts import Rig, all_alerts, set_config, set_rule
from test_commands import mk_pair


def setup(db, monkeypatch):
    _, tank, pipe = mk_pair(db)
    for dev in (tank, pipe):
        set_config(db, dev, tank_height_cm=8, low_pct=37.5, high_pct=100,
                   auto_mode=False, sample_interval_s=1)
    set_rule(db, tank, "LEAK_SUSPECT", window_s=20, window_min=1,
             rate_cm_per_min=1, min_drop_cm=0.6, settle_s=5, max_gap_s=5)
    rig = Rig(tank, pipe, 0, step=1)
    monkeypatch.setattr('app.alerts.utcnow', lambda: rig.t)
    return tank, pipe, rig


def test_fast_leak_requires_full_window_then_opens_and_clears(db, alert_env, monkeypatch):
    tank, _, rig = setup(db, monkeypatch)
    for second in range(25):
        rig.tick((7 - second * 0.05) / 8 * 100)
        assert not all_alerts(db, 'LEAK_SUSPECT')
    rig.tick((7 - 25 * 0.05) / 8 * 100)
    alert, = all_alerts(db, 'LEAK_SUSPECT')
    assert alert.device_id == tank.id and alert.state == 'open'
    for _ in range(25):
        rig.tick(5.75 / 8 * 100)
    assert all_alerts(db, 'LEAK_SUSPECT')[0].state == 'closed'


def test_fast_leak_rejects_small_drop_despite_rate_over_threshold(db, alert_env, monkeypatch):
    _, _, rig = setup(db, monkeypatch)
    for second in range(40):
        rig.tick((7 - 0.025 * second) / 8 * 100)
    assert not all_alerts(db, 'LEAK_SUSPECT') # median-group drop≈0.4cm, below0.6


def test_fast_leak_rejects_single_echo_spike_and_running_pump(db, alert_env, monkeypatch):
    _, _, rig = setup(db, monkeypatch)
    for second in range(40):
        height = 6 if second == 23 else 7 + (0.08 if second % 2 else -0.08)
        rig.tick(height / 8 * 100)
    assert not all_alerts(db, 'LEAK_SUSPECT')
    for second in range(40):
        rig.tick((7 - second * 0.05) / 8 * 100, pump=True)
    assert not all_alerts(db, 'LEAK_SUSPECT')


def test_fast_leak_discards_window_on_gap_and_requires_fresh_pipe(db, alert_env, monkeypatch):
    tank, _, rig = setup(db, monkeypatch)
    for second in range(23):
        rig.tick((7 - second * 0.05) / 8 * 100)
    rig.t += timedelta(seconds=7)
    for second in range(10):
        rig.tick((5.5 - second * 0.05) / 8 * 100)
    assert not all_alerts(db, 'LEAK_SUSPECT')
    # Only tank reports after the pipe goes stale; a drop must not prove a leak.
    from app import alerts
    for second in range(30):
        alerts.evaluate(alerts.Sample(tank.id, rig.t, level_pct=(5 - second * 0.05) / 8 * 100))
        rig.t += timedelta(seconds=1)
    assert not all_alerts(db, 'LEAK_SUSPECT')
