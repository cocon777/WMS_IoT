"""Explicit physical experiment: requires --allow-pump and an assigned pipe device ID."""
import argparse
import csv
import getpass
import os
import time
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--allow-pump", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("tests/evidence/commands.csv"))
    args = parser.parse_args()
    if not args.allow_pump or not 1 <= args.count <= 100:
        parser.error("Requires --allow-pump and count 1..100. Ensure source water and destination capacity.")
    token = os.getenv("WMS_TOKEN")
    with httpx.Client(base_url=args.base, timeout=10) as client:
        if not token:
            response = client.post("/api/auth/login", json={"email": input("Email: "), "password": getpass.getpass("Password: ")})
            response.raise_for_status()
            token = response.json()["access_token"]
        client.headers["Authorization"] = "Bearer " + token
        path = f"/api/devices/{args.device}/commands"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["iteration", "cmd_id", "status", "reason", "request_to_terminal_ms", "sent_to_ack_ms"])
            writer.writeheader()
            try:
                for index in range(args.count):
                    start = time.monotonic()
                    response = client.post(path, json={"action": "pump", "value": "on", "duration_s": 1})
                    response.raise_for_status()
                    command = response.json()
                    while command["status"] == "sent" and time.monotonic()-start < 12:
                        time.sleep(.1)
                        response = client.get(path + "/" + command["cmd_id"])
                        response.raise_for_status()
                        command = response.json()
                    from datetime import datetime
                    ack_ms = ""
                    if command["acked_at"]:
                        ack_ms = (datetime.fromisoformat(command["acked_at"].replace("Z", "+00:00"))-
                                  datetime.fromisoformat(command["sent_at"].replace("Z", "+00:00"))).total_seconds()*1000
                    writer.writerow({"iteration": index+1, "cmd_id": command["cmd_id"], "status": command["status"],
                                     "reason": command["reason"], "request_to_terminal_ms": (time.monotonic()-start)*1000,
                                     "sent_to_ack_ms": ack_ms})
                    stream.flush()
                    if command["status"] != "ok":
                        raise RuntimeError("Stopped experiment: command failed or timed out; inspect the recorded reason")
                    time.sleep(2)  # let 1s pump run finish before next command
            finally:
                try:
                    client.post(path, json={"action": "pump", "value": "off"}).raise_for_status()
                except Exception as error:
                    print("OFF could not be confirmed; local firmware deadline still applies:", type(error).__name__)


if __name__ == "__main__":
    main()
