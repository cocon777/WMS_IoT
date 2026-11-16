"""Alert engine cho hệ thống 2 node: node bồn (tank) đo mực nước, node ống (pipe) đo lưu lượng và điều khiển bơm."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import alerts, device_params, ingest
from app.db import utcnow
from app.models import Alert, AlertRule, Command, Device, DeviceConfig
from test_commands import mk_dev, mk_pair


class Timeline:
    """Phát mẫu telemetry cách nhau 5 giây cho MỘT node; mẫu đầu cách 'now' đúng duration_s giây."""

    def __init__(self, dev, duration_s, step=5):
        self.dev, self.step = dev, step
        self.t = utcnow() - timedelta(seconds=duration_s)

    def add(self, level=None, *, flow=None, pump=None, n=1):
        """Node bồn: add(mực nước). Node ống: add(flow=..., pump=...)."""
        for _ in range(n):
            alerts.evaluate(alerts.Sample(self.dev.id, self.t, level, flow, pump))
            self.t += timedelta(seconds=self.step)

    def skip(self, seconds):
        self.t += timedelta(seconds=seconds)


class Rig:
    """Hai node cùng một site: mỗi tick() phát một mẫu cho CẢ HAI node tại cùng thời điểm (bồn trước, ống sau)."""

    def __init__(self, tank, pipe, duration_s, step=5):
        self.tank, self.pipe, self.step = tank, pipe, step
        self.t = utcnow() - timedelta(seconds=duration_s)

    def tick(self, level, *, flow=0.0, pump=False, n=1):
        for _ in range(n):
            alerts.evaluate(alerts.Sample(self.tank.id, self.t, level_pct=level))
            alerts.evaluate(alerts.Sample(self.pipe.id, self.t, flow_lpm=flow, pump_on=pump))
            self.t += timedelta(seconds=self.step)


def all_alerts(db, type_=None):
    db.expire_all()
    stmt = select(Alert).order_by(Alert.id)
    if type_:
        stmt = stmt.where(Alert.type == type_)
    return db.scalars(stmt).all()


def set_config(db, dev, **values):
    for key, value in values.items():
        row = db.scalars(select(DeviceConfig).where(DeviceConfig.device_id == dev.id, DeviceConfig.key == key)).first()
        if row is None:
            db.add(DeviceConfig(device_id=dev.id, key=key, value=device_params.store(value)))
        else:
            row.value = device_params.store(value)
    db.commit()
    alerts.invalidate()


def set_rule(db, dev, type_, **params):
    alerts.load_rules(db, dev)                      # tạo quy tắc mặc định của node này
    db.commit()
    row = db.scalars(select(AlertRule).where(AlertRule.device_id == dev.id, AlertRule.type == type_)).one()
    row.params_json = json.dumps({**json.loads(row.params_json), **params})
    db.commit()
    alerts.invalidate()


def published(alert_env):
    return alert_env.publisher.published


def test_default_rules_depend_on_the_node_type(db, alert_env):
    site, tank, pipe = mk_pair(db)
    assert set(alerts.load_rules(db, tank)) == {"LOW_LEVEL", "HIGH_LEVEL", "LEAK_SUSPECT", "DEVICE_OFFLINE"}
    assert set(alerts.load_rules(db, pipe)) == {"LEAK_SUSPECT", "PUMP_NO_RISE", "DEVICE_OFFLINE"}
    assert "window_min" in alerts.load_rules(db, tank)["LEAK_SUSPECT"].params
    assert "usage_start_h" in alerts.load_rules(db, pipe)["LEAK_SUSPECT"].params


# ----------------------------------------------------------------------------- node bồn: mực thấp / cao
def test_low_level_needs_min_duration_then_auto_pumps_the_pipe_node(db, alert_env):
    site, tank, pipe = mk_pair(db)
    tl = Timeline(tank, 20)
    tl.add(10, n=2)                                     # mới 5 giây liên tục: chưa đủ 10 giây
    assert all_alerts(db) == []
    tl.add(10, n=3)
    (a,) = all_alerts(db, "LOW_LEVEL")
    assert a.device_id == tank.id and a.state == "open" and a.severity == "warning" and a.value == 10
    topic, payload, qos = published(alert_env)[0]
    assert topic == "wms/wms-pipe-01/cmd" and payload["value"] == "on" and payload["duration_s"] == 60   # lệnh tới node ỐNG
    assert len(published(alert_env)) == 1               # chỉ gửi một lần khi cảnh báo mở
    cmd = db.scalars(select(Command)).one()
    assert cmd.device_id == pipe.id and cmd.user_id is None and "auto:LOW_LEVEL" in cmd.params_json
    assert any(e == "alert" and p["type"] == "LOW_LEVEL" and p["device_type"] == "tank" for e, p in alert_env.events)


def test_low_level_without_auto_mode_does_not_pump(db, alert_env):
    site, tank, pipe = mk_pair(db)
    set_config(db, tank, auto_mode=False)
    Timeline(tank, 20).add(10, n=5)
    assert len(all_alerts(db, "LOW_LEVEL")) == 1 and published(alert_env) == []


def test_low_level_alone_without_a_pipe_node_still_alerts_without_crashing(db, alert_env):
    tank = mk_dev(db, "wms-tank-01", dtype="tank")      # chưa vào site, không có node ống để bật bơm
    Timeline(tank, 20).add(10, n=5)
    assert len(all_alerts(db, "LOW_LEVEL")) == 1 and published(alert_env) == []


def test_low_level_does_not_restart_a_pump_that_is_already_running(db, alert_env):
    site, tank, pipe = mk_pair(db)
    Rig(tank, pipe, 20).tick(10, flow=3.2, pump=True, n=5)
    assert len(all_alerts(db, "LOW_LEVEL")) == 1 and published(alert_env) == []


def test_low_level_hysteresis_and_cooldown(db, alert_env):
    site, tank, pipe = mk_pair(db)
    tl = Timeline(tank, 120)
    tl.add(10, n=5)
    tl.add(24, n=2)                                     # 20..25: vùng hysteresis, vẫn mở
    assert all_alerts(db, "LOW_LEVEL")[0].state == "open"
    tl.add(26)                                          # > low + 5 thì đóng
    assert all_alerts(db, "LOW_LEVEL")[0].state == "closed"
    tl.add(10, n=5)                                     # tụt lại ngay: bị cooldown 5 phút chặn
    assert len(all_alerts(db, "LOW_LEVEL")) == 1
    tl.skip(310)
    tl.add(10, n=5)                                     # hết cooldown thì sinh cảnh báo mới
    assert len(all_alerts(db, "LOW_LEVEL")) == 2


def test_high_level_turns_the_pump_off_on_the_pipe_node(db, alert_env):
    site, tank, pipe = mk_pair(db)
    rig = Rig(tank, pipe, 15)
    rig.tick(95, flow=2.0, pump=True, n=3)
    (a,) = all_alerts(db, "HIGH_LEVEL")
    assert a.state == "open" and a.device_id == tank.id
    assert len(published(alert_env)) == 1               # có throttle, không spam lệnh
    topic, payload, _ = published(alert_env)[0]
    assert topic == "wms/wms-pipe-01/cmd" and payload["value"] == "off"
    rig.tick(84)                                        # < high - 5 thì đóng
    assert all_alerts(db, "HIGH_LEVEL")[0].state == "closed"


def test_high_level_does_not_command_when_the_pump_is_known_to_be_off(db, alert_env):
    site, tank, pipe = mk_pair(db)
    rig = Rig(tank, pipe, 10)
    rig.tick(50)                                        # node ống báo bơm tắt
    rig.tick(95, n=2)
    assert len(all_alerts(db, "HIGH_LEVEL")) == 1 and published(alert_env) == []


def test_high_level_sends_off_when_the_pump_state_is_unknown(db, alert_env):
    site, tank, pipe = mk_pair(db)
    Timeline(tank, 10).add(95, n=3)                     # chưa có mẫu nào của node ống: an toàn hơn là ngắt bơm
    assert [p[1]["value"] for p in published(alert_env)] == ["off"]


# ----------------------------------------------------------------------------- node ống: bơm chạy mà mực không tăng
def test_pump_no_rise_sets_the_pipe_node_to_fault_and_turns_it_off(db, alert_env):
    site, tank, pipe = mk_pair(db)
    Rig(tank, pipe, 60).tick(50, flow=3.2, pump=True, n=13)         # bơm chạy 60 giây, mực nước đứng yên
    (a,) = all_alerts(db, "PUMP_NO_RISE")
    assert a.device_id == pipe.id and a.severity == "critical" and a.state == "open"
    db.expire_all()
    assert db.get(Device, pipe.id).state == "Fault" and db.get(Device, tank.id).state == "Active"
    assert [(p[0], p[1]["value"]) for p in published(alert_env)] == [("wms/wms-pipe-01/cmd", "off")]   # lệnh tắt đi được dù đã Fault
    assert any(e == "device_state" and p["state"] == "Fault" and p["type"] == "pipe" for e, p in alert_env.events)


def test_pump_no_rise_needs_the_tank_level(db, alert_env):
    site, tank, pipe = mk_pair(db)
    Timeline(pipe, 70).add(flow=3.2, pump=True, n=15)   # không có mẫu mực nước: không đủ cơ sở kết luận
    assert all_alerts(db) == []  # no claim of PUMP_NO_RISE without a level measurement
    assert [p[1]["value"] for p in published(alert_env)] == ["off"]  # new stale-level guard


def test_normal_pumping_raises_no_alert(db, alert_env):
    site, tank, pipe = mk_pair(db)
    rig = Rig(tank, pipe, 70)
    for i in range(15):
        rig.tick(30 + i, flow=3.2, pump=True)           # mực nước tăng 1% mỗi 5 giây
    assert all_alerts(db) == []


# ----------------------------------------------------------------------------- rò rỉ
def test_leak_by_flow_after_leak_minutes_and_clears_when_the_flow_stops(db, alert_env):
    site, tank, pipe = mk_pair(db)
    set_config(db, pipe, leak_minutes=1)
    tl = Timeline(pipe, 200)
    tl.add(flow=0.6, pump=False, n=12)                  # 55 giây
    assert all_alerts(db, "LEAK_SUSPECT") == []
    tl.add(flow=0.6, pump=False, n=2)                   # đủ 1 phút
    (a,) = all_alerts(db, "LEAK_SUSPECT")
    assert a.device_id == pipe.id and a.severity == "critical" and a.value == 0.6
    tl.add(flow=0.0, pump=False, n=8)                   # lưu lượng về 0 đủ 30 giây (clear_s)
    assert all_alerts(db, "LEAK_SUSPECT")[0].state == "closed"


def test_leak_by_flow_ignores_a_running_pump_and_the_usage_window(db, alert_env):
    site, tank, pipe = mk_pair(db)
    set_config(db, pipe, leak_minutes=1)
    Timeline(pipe, 400).add(flow=3.2, pump=True, n=30)  # bơm chạy bình thường 2,5 phút: dòng chảy là hợp lệ
    assert all_alerts(db) == []
    set_rule(db, pipe, "LEAK_SUSPECT", usage_start_h=0, usage_end_h=24)     # cả ngày là giờ dùng nước
    Timeline(pipe, 120).add(flow=0.6, pump=False, n=25)
    assert all_alerts(db, "LEAK_SUSPECT") == []


def test_leak_by_flow_outside_the_usage_window_still_alerts(db, alert_env):
    site, tank, pipe = mk_pair(db)
    set_config(db, pipe, leak_minutes=1)
    hour = utcnow().hour
    set_rule(db, pipe, "LEAK_SUSPECT", usage_start_h=(hour + 3) % 24, usage_end_h=(hour + 4) % 24, utc_offset_h=0)
    Timeline(pipe, 100).add(flow=0.6, pump=False, n=15)
    assert len(all_alerts(db, "LEAK_SUSPECT")) == 1


def test_leak_by_level_opens_then_closes_when_the_level_is_stable(db, alert_env):
    site, tank, pipe = mk_pair(db)
    rig = Rig(tank, pipe, 1000)
    level = 80.0
    for _ in range(67):                                 # ~5,5 phút, giảm 2%/phút = 0,5 cm/phút (> 0,3), bơm tắt
        rig.tick(level)
        level -= 2.0 / 12
    (a,) = all_alerts(db, "LEAK_SUSPECT")
    assert a.device_id == tank.id and a.severity == "critical" and a.state == "open" and a.value > 0.3
    rig.tick(level, n=80)                               # mực nước ổn định đủ lâu
    assert all_alerts(db, "LEAK_SUSPECT")[0].state == "closed"


def test_leak_by_level_needs_to_know_the_pump_is_off(db, alert_env):
    site, tank, pipe = mk_pair(db)
    tl = Timeline(tank, 1000)                           # chỉ có mẫu của node bồn: không biết bơm tắt hay đang chạy
    level = 80.0
    for _ in range(90):
        tl.add(level)
        level -= 2.0 / 12
    assert all_alerts(db, "LEAK_SUSPECT") == []


def test_slow_drop_is_not_a_leak(db, alert_env):
    site, tank, pipe = mk_pair(db)
    rig = Rig(tank, pipe, 500)
    level = 80.0
    for _ in range(90):                                 # 0,4%/phút = 0,1 cm/phút < 0,3
        rig.tick(level)
        level -= 0.4 / 12
    assert all_alerts(db, "LEAK_SUSPECT") == []


# ----------------------------------------------------------------------------- dữ liệu cũ, đảo thứ tự, sai loại
def test_stale_samples_raise_alert_but_take_no_action(db, alert_env):
    site, tank, pipe = mk_pair(db)
    Timeline(tank, 600).add(10, n=3)                    # mẫu gửi bù từ 10 phút trước
    assert len(all_alerts(db, "LOW_LEVEL")) == 1 and published(alert_env) == []


def test_out_of_order_samples_are_ignored(db, alert_env):
    site, tank, pipe = mk_pair(db)
    tl = Timeline(tank, 30)
    tl.add(50)
    older = tl.t - timedelta(seconds=60)
    for i in range(5):
        alerts.evaluate(alerts.Sample(tank.id, older + timedelta(seconds=5 * i), level_pct=5.0))
    assert all_alerts(db) == []


def test_a_sample_without_the_fields_of_its_node_type_is_ignored(db, alert_env):
    site, tank, pipe = mk_pair(db)
    tl = Timeline(pipe, 60)
    for _ in range(13):
        alerts.evaluate(alerts.Sample(pipe.id, tl.t, level_pct=5.0))      # mẫu kiểu node bồn gửi cho node ống
        tl.skip(5)
    assert all_alerts(db) == [] and published(alert_env) == []


# ----------------------------------------------------------------------------- mất kết nối
def test_offline_alert_via_ingest_then_recovery_and_cooldown(db, alert_env):
    tank = mk_dev(db, "wms-tank-01", dtype="tank")
    ingest.handle_message("wms/wms-tank-01/status", b'{"status":"offline"}')
    (a,) = all_alerts(db, "DEVICE_OFFLINE")
    assert a.state == "open" and a.severity == "warning" and a.device_id == tank.id
    db.expire_all()
    assert db.get(Device, tank.id).state == "Offline"

    payload = {"device_id": "wms-tank-01", "boot_id": "b1", "seq": 1,
               "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "distance_cm": 10, "level_pct": 72.5}
    ingest.handle_message("wms/wms-tank-01/telemetry", json.dumps(payload).encode())
    assert all_alerts(db, "DEVICE_OFFLINE")[0].state == "closed"
    db.expire_all()
    assert db.get(Device, tank.id).state == "Active"

    ingest.handle_message("wms/wms-tank-01/status", b'{"status":"offline"}')    # rớt mạng lại: cooldown
    assert len(all_alerts(db, "DEVICE_OFFLINE")) == 1


def test_offline_alert_is_not_duplicated(db, alert_env):
    site, tank, pipe = mk_pair(db)
    alerts.on_device_offline(pipe.id)
    alerts.on_device_offline(pipe.id)
    assert len(all_alerts(db, "DEVICE_OFFLINE")) == 1


def test_a_pipe_node_going_offline_makes_its_pump_state_unknown(db, alert_env):
    site, tank, pipe = mk_pair(db)
    Rig(tank, pipe, 15).tick(50, n=3)
    assert alerts._sites[site.id].pump_ts is not None and alerts._sites[site.id].level_ts is not None
    alerts.on_device_offline(pipe.id)
    assert alerts._sites[site.id].pump_ts is None and alerts._sites[site.id].level_ts is not None
    alerts.on_device_offline(tank.id)
    assert alerts._sites[site.id].level_ts is None
