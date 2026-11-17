"""TV3 Khu B concept, adapted to real integrated REST + MQTT/TLS, separate software IDs.

No physical node topic, no seed telemetry on wms-tank-01/wms-pipe-01.
Credentials are saved only under ignored deployment/runtime/.
"""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import json
from pathlib import Path
import ssl
import threading
import time
import uuid

import httpx
import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]
CODES = {"tank": "wms-sim-tank-02", "pipe": "wms-sim-pipe-02"}


class Simulation:
    def __init__(self, scenario="normal"):
        self.scenario = scenario
        self.level_cm = 7.0 if scenario == "leak" else 2.8
        self.pump = False
        self.deadline = 0.0
        self.total_l = 0.0
        self.lock = threading.RLock()

    def tick(self, dt=1.0):
        with self.lock:
            if time.monotonic() >= self.deadline:
                self.pump = False
            flow = 1.08 if self.pump else 0.0
            volume = flow * dt / 60
            self.total_l += volume
            self.level_cm = min(8.5, self.level_cm + volume / (0.8 / 7))
            if self.scenario == "leak" and not self.pump:
                self.level_cm = max(4.0, self.level_cm - 3.0 * dt / 60)
            return flow


class SoftwareNode:
    def __init__(self, role, password, ca, host, port, sim):
        self.role, self.code, self.sim = role, CODES[role], sim
        if not self.code.startswith("wms-sim-"):
            raise ValueError("Simulator must use dedicated simulation IDs")
        self.seq, self.config_version = 0, 0
        self.boot = "sim-" + uuid.uuid4().hex[:12]  # MQTT schema boot_id max16
        self.connected = threading.Event()
        self.recent = {}
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.code + "-software")
        self.client.username_pw_set(self.code, password)
        self.client.tls_set(ca_certs=str(ca))
        self.client.will_set(f"wms/{self.code}/status", json.dumps({"status": "offline"}), qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = lambda *args: self.connected.clear()
        self.client.on_message = self.on_message
        self.client.connect(host, port, keepalive=20)
        self.client.loop_start()

    def publish(self, topic, data, retain=False):
        return self.client.publish(f"wms/{self.code}/{topic}", json.dumps(data), qos=1, retain=retain)

    def status(self):
        self.publish("status", {"status": "online", "fw_version": "software-simulator-1.0",
                                "config_version": self.config_version}, retain=True)

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            return
        client.subscribe([(f"wms/{self.code}/config", 1), (f"wms/{self.code}/cmd", 1)])
        self.connected.set()
        self.status()

    def on_message(self, client, userdata, message):
        try:
            data = json.loads(message.payload)
            if message.topic == f"wms/{self.code}/config":
                self.config_version = max(self.config_version, int(data["version"]))
                self.status()
            elif message.topic == f"wms/{self.code}/cmd":
                identity = data["cmd_id"]
                if identity in self.recent:
                    self.publish("ack", self.recent[identity])
                    return
                reason = None
                issued = datetime.fromisoformat(data["issued_at"].replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - issued).total_seconds()
                if self.role != "pipe" or data.get("action") != "pump":
                    reason = "wrong_node_or_action"
                elif age < -2 or age > 10:
                    reason = "expired"
                elif data.get("value") not in ("on", "off"):
                    reason = "invalid_value"
                elif data["value"] == "on" and not 1 <= int(data.get("duration_s", 0)) <= 60:
                    reason = "over_limit"
                if reason is None:
                    with self.sim.lock:
                        self.sim.pump = data["value"] == "on"
                        self.sim.deadline = time.monotonic() + (int(data["duration_s"]) if self.sim.pump else 0)
                ack = {"cmd_id": identity, "result": "fail" if reason else "ok", "reason": reason}
                self.recent[identity] = ack
                if len(self.recent) > 100:
                    self.recent.pop(next(iter(self.recent)))
                self.publish("ack", ack)
        except (ValueError, KeyError, TypeError):
            return

    def sample(self, flow):
        self.seq += 1
        data = {"device_id": self.code, "boot_id": self.boot, "seq": self.seq,
                "ts": datetime.now(timezone.utc).isoformat(), "rssi": -50}
        with self.sim.lock:
            if self.role == "tank":
                data.update(distance_cm=16.5 - self.sim.level_cm,
                            level_pct=max(0, min(100, self.sim.level_cm / 8 * 100)))
            else:
                data.update(flow_lpm=flow, flow_total_l=self.sim.total_l, pump_on=self.sim.pump)
        self.publish("telemetry", data)

    def close(self):
        self.publish("status", {"status": "offline"}, retain=True).wait_for_publish(timeout=3)
        self.client.disconnect()
        self.client.loop_stop()


def prepare(api, cache):
    def call(method, path, **kwargs):
        response = api.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()
    sites = call("GET", "/api/sites")
    site = next((s for s in sites if s["name"] == "Khu B — MÔ PHỎNG"), None)
    if site is None:
        site = call("POST", "/api/sites", json={"name": "Khu B — MÔ PHỎNG",
                    "description": "[MÔ PHỎNG] Hai software nodes qua MQTT/TLS; thử đa site và phân quyền. Không phải ESP32 vật lý."})
    devices = {d["device_code"]: d for d in call("GET", "/api/devices")}
    for role, code in CODES.items():
        dev = devices.get(code)
        if dev is None:
            dev = call("POST", "/api/devices", json={"device_code": code,
                       "name": f"MÔ PHỎNG Khu B — {role}", "type": role, "site_id": site["id"]})
        if dev["site_id"] != site["id"] or dev["type"] != role:
            raise RuntimeError("Existing simulation ID belongs to a different site/role; kept unchanged")
        if dev["state"] == "Registered":
            provision = call("POST", f"/api/devices/{dev['id']}/provision")
            cache[code] = provision["mqtt_password"]
        elif code not in cache or dev["state"] in ("Decommissioned", "Maintenance", "Fault"):
            raise RuntimeError("Simulator credential unavailable or node not runnable; use lifecycle UI, do not overwrite DB")
        cfg = call("GET", f"/api/devices/{dev['id']}/config")
        profile = json.loads((ROOT / "deployment/demo" / f"{role}-config.json").read_text())
        call("PUT", f"/api/devices/{dev['id']}/config", json={**profile, "version": cfg["version"]})
        rules = json.loads((ROOT / "deployment/demo" / f"{role}-alert-rules.json").read_text())
        call("PUT", f"/api/devices/{dev['id']}/alert-rules", json=rules)
    return site


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://localhost:8443")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=18883)
    parser.add_argument("--email", required=True)
    parser.add_argument("--scenario", choices=["normal", "leak"], default="normal")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--seconds", type=int, default=0, help="0 = until Ctrl+C")
    args = parser.parse_args()
    if httpx.URL(args.url).scheme != "https":
        raise SystemExit("HTTPS is required for simulator preparation")
    ca = ROOT / "deployment/certs/ca.crt"
    cache_path = ROOT / "deployment/runtime/site2-simulator.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    # One credential cache per API deployment. Never send saved credentials to a new server.
    if cache.get("url", args.url) != args.url:
        raise SystemExit("Cache belongs to another deployment; keep it and use a separate project checkout")
    cache["url"] = args.url
    nodes = []
    try:
        with httpx.Client(base_url=args.url, verify=ssl.create_default_context(cafile=str(ca)), timeout=15, trust_env=False) as api:
            response = api.post("/api/auth/login", json={"email": args.email, "password": getpass("Admin password: ")})
            response.raise_for_status()
            session = response.json()
            if session["user"]["role"] != "Admin":
                raise SystemExit("Admin is required to prepare the separate software site")
            api.headers["Authorization"] = "Bearer " + session["access_token"]
            try:
                site = prepare(api, cache)
            finally:
                cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
                cache_path.chmod(0o600)
            print("Prepared separate simulation site:", site["name"], "(no physical device changed)")
        if args.prepare_only:
            return
        sim = Simulation(args.scenario)
        for role in CODES:
            nodes.append(SoftwareNode(role, cache[CODES[role]], ca, args.host, args.port, sim))
        for node in nodes:
            if not node.connected.wait(8):
                raise RuntimeError("Simulation MQTT/TLS connection failed")
        print("SOFTWARE SIMULATION running; all water/flow is simulated. Ctrl+C to stop.")
        started = time.monotonic()
        while not args.seconds or time.monotonic() - started < args.seconds:
            flow = sim.tick()
            for node in nodes:
                node.sample(flow)
                node.status()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping software simulation.")
    finally:
        for node in nodes:
            node.close()


if __name__ == "__main__":
    main()
