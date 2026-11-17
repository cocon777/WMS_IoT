"""Publish bản tin mẫu để thử MQTT subscriber khi chưa có firmware (hệ thống 2 node).
  python tests/publish_sample.py --user backend --password xxx
Kỳ vọng: mỗi node lưu 1 bản hợp lệ; bản trùng, sai dải, thiếu trường bắt buộc của loại node, device_id lệch topic
và không phải JSON bị loại (xem log backend: 'duplicate telemetry', 'reject telemetry ...').
"""
import argparse
import json
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="localhost")
ap.add_argument("--port", type=int, default=1883)
ap.add_argument("--user", default="backend")
ap.add_argument("--password", default="")
ap.add_argument("--tank", default="wms-tank-01")
ap.add_argument("--pipe", default="wms-pipe-01")
args = ap.parse_args()

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sample-publisher")
c.username_pw_set(args.user, args.password)
c.connect(args.host, args.port)
c.loop_start()


def pub(topic, payload):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    c.publish(topic, body, qos=1).wait_for_publish()
    print("->", topic, body[:100])


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tank(seq, **override):
    d = {"device_id": args.tank, "boot_id": "a3f9", "seq": seq, "ts": now(), "distance_cm": 18.4, "level_pct": 72.5, "rssi": -61}
    d.update(override)
    return d


def pipe(seq, **override):
    d = {"device_id": args.pipe, "boot_id": "b7c2", "seq": seq, "ts": now(), "flow_lpm": 3.2, "flow_total_l": 15.4,
         "pump_on": True, "rssi": -58}
    d.update(override)
    return d


for code in (args.tank, args.pipe):
    pub(f"wms/{code}/status", {"status": "online", "fw_version": "0.1.0", "free_heap": 210000})

t_topic, p_topic = f"wms/{args.tank}/telemetry", f"wms/{args.pipe}/telemetry"
# --- node bồn ---
pub(t_topic, tank(1))                                         # hợp lệ
pub(t_topic, tank(1))                                         # trùng (boot_id, seq) -> duplicate
pub(t_topic, tank(2, level_pct=999))                          # ngoài dải (S5)
bad = tank(3)
del bad["ts"]
pub(t_topic, bad)                                             # thiếu ts (S5)
pub(t_topic, tank(4, device_id="wms-999"))                    # device_id lệch topic
pub(t_topic, tank(5, boot_id="<i>x</i>"))                     # chuỗi lạ: lưu như dữ liệu, escape khi hiển thị
bad = tank(6)
del bad["level_pct"]
pub(t_topic, bad)                                             # thiếu trường bắt buộc của node bồn
# --- node ống ---
pub(p_topic, pipe(1))                                         # hợp lệ
pub(p_topic, pipe(1))                                         # trùng
bad = pipe(2)
del bad["pump_on"]
pub(p_topic, bad)                                             # thiếu pump_on (bắt buộc với node ống)
pub(p_topic, {"device_id": args.pipe, "boot_id": "b7c2", "seq": 3, "ts": now(), "distance_cm": 10, "level_pct": 50})   # gửi nhầm trường của node bồn
pub(p_topic, "không phải json")

c.loop_stop()
c.disconnect()
