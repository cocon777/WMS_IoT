"""Giả lập HAI node của một hệ thống chạy liên tục (khi chưa có firmware):
  wms-tank-01  node bồn: gửi mực nước; nhận cấu hình; "còi" in ra màn hình khi mực nước ngoài ngưỡng
  wms-pipe-01  node ống: gửi lưu lượng và trạng thái bơm; nhận lệnh bơm và trả ack; nhận cấu hình
Hai node dùng chung một mô hình vật lý: bơm chạy thì lưu lượng 3,2 L/phút và mực nước ở bồn tăng dần.

    python tests/fake_device.py                       # từ thư mục gốc repo; Ctrl+C để dừng
    python tests/fake_device.py --leak                # mở "van rò rỉ": bơm tắt nhưng vẫn có dòng chảy và mực nước giảm
    python tests/fake_device.py --tank wms-tank-01 --pipe wms-pipe-01 --host localhost --port 1883

Cả hai thiết bị phải ở trạng thái Active và cùng một site trong CSDL (python -m scripts.seed_dev tạo sẵn).
Thử cảnh báo rò rỉ nhanh: PUT /api/devices/<id node ống>/config {"leak_minutes": 1} rồi chạy với --leak.
"""
import argparse
import json
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

ap = argparse.ArgumentParser()
ap.add_argument("--tank", default="wms-tank-01")
ap.add_argument("--pipe", default="wms-pipe-01")
ap.add_argument("--host", default="localhost")
ap.add_argument("--port", type=int, default=1883)
ap.add_argument("--leak", action="store_true", help="mô phỏng rò rỉ: bơm tắt vẫn có dòng chảy 0,6 L/phút, mực nước giảm")
args = ap.parse_args()

TICK_S, LEAK_FLOW, LEAK_DROP = 5, 0.6, 0.2
lock = threading.Lock()
state = {"pump_on": False, "off_at": 0.0, "level": 60.0, "total": 0.0, "low": 20.0, "high": 90.0, "buzzer": None,
         "seq": {"tank": 0, "pipe": 0}, "cfg_version": {"tank": 0, "pipe": 0}}
codes = {"tank": args.tank, "pipe": args.pipe}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_client(role: str, topics: list[str]) -> mqtt.Client:
    code = codes[role]
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"fake-{code}")

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{code}] không kết nối được broker:", reason_code)
            return
        c.subscribe([(f"wms/{code}/{t}", 1) for t in topics])
        print(f"[{code}] đã kết nối broker {args.host}:{args.port}, đang chờ: {', '.join(topics)}")

    def on_message(c, userdata, msg):
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        if msg.topic.endswith("/config"):
            with lock:
                state["cfg_version"][role] = int(data.get("version", state["cfg_version"][role]))
                if role == "tank":
                    state["low"], state["high"] = float(data.get("low_pct", state["low"])), float(data.get("high_pct", state["high"]))
            print(f"[{code}] nhận cấu hình phiên bản {data.get('version')}")
            return
        value, cmd_id = data.get("value"), data.get("cmd_id")        # chỉ node ống đăng ký topic cmd
        with lock:
            if value == "on":
                state["pump_on"], state["off_at"] = True, time.time() + float(data.get("duration_s", 30))
            elif value == "off":
                state["pump_on"] = False
        print(f"[{code}] nhận lệnh bơm: {value} {data.get('duration_s', '')}".rstrip(), "-> trả ack ok")
        c.publish(f"wms/{code}/ack", json.dumps({"cmd_id": cmd_id, "result": "ok", "reason": None, "ts": now_iso()}), qos=1)

    client.on_connect, client.on_message = on_connect, on_message
    client.will_set(f"wms/{code}/status", json.dumps({"status": "offline"}), qos=1)      # LWT
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()
    return client


clients = {"tank": make_client("tank", ["config"]), "pipe": make_client("pipe", ["cmd", "config"])}

try:
    tick = 0
    while True:
        with lock:
            if state["pump_on"] and time.time() >= state["off_at"]:
                state["pump_on"] = False
                print("[wms-pipe-01] hết thời gian bơm, tắt bơm")
            pumping = state["pump_on"]
            leaking = args.leak and not pumping
            if pumping:
                state["level"] = min(98.0, state["level"] + 0.4)
                state["total"] += 3.2 * TICK_S / 60
            else:
                state["level"] = max(5.0, state["level"] - (LEAK_DROP if leaking else 0.02))
            level, total = state["level"], state["total"]
            flow = 3.2 if pumping else (LEAK_FLOW if leaking else 0.0)
            cfg = dict(state["cfg_version"])
            buzzer = "thấp" if level < state["low"] else ("cao" if level > state["high"] else None)
            if buzzer != state["buzzer"]:
                state["buzzer"] = buzzer
                if buzzer:
                    print(f"[{codes['tank']}] CÒI: mực nước {buzzer} ({level:.1f}%)")
            state["seq"]["tank"] += 1
            state["seq"]["pipe"] += 1
            seq = dict(state["seq"])
        for role in ("tank", "pipe"):
            code = codes[role]
            if tick % 6 == 0:                                                  # heartbeat mỗi 30 giây
                clients[role].publish(f"wms/{code}/status", json.dumps(
                    {"status": "online", "fw_version": "sim-0.1", "free_heap": 200000, "config_version": cfg[role]}), qos=1)
        clients["tank"].publish(f"wms/{codes['tank']}/telemetry", json.dumps(
            {"device_id": codes["tank"], "boot_id": "sim", "seq": seq["tank"], "ts": now_iso(),
             "distance_cm": round(25 * (1 - level / 100), 1), "level_pct": round(level, 1), "rssi": -55}), qos=1)
        clients["pipe"].publish(f"wms/{codes['pipe']}/telemetry", json.dumps(
            {"device_id": codes["pipe"], "boot_id": "sim", "seq": seq["pipe"], "ts": now_iso(),
             "flow_lpm": flow, "flow_total_l": round(total, 2), "pump_on": pumping, "rssi": -57}), qos=1)
        tick += 1
        time.sleep(TICK_S)
except KeyboardInterrupt:
    for role, client in clients.items():
        client.publish(f"wms/{codes[role]}/status", json.dumps({"status": "offline"}), qos=1).wait_for_publish(timeout=2)
        client.loop_stop()
        client.disconnect()
    print("Đã dừng hai thiết bị giả lập")
