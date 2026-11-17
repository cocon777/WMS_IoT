import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from analyze_export import stats


def analyze(messages):
    latency, live_latency, push = [], [], []
    telemetry = 0
    for message in messages:
        if message.get("event") != "telemetry":
            continue
        telemetry += 1
        data = message["data"]
        ts = datetime.fromisoformat(data["ts"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()*1000
        received = message["client_received_epoch_ms"]
        value = received-ts
        latency.append(value)
        backend = datetime.fromisoformat(data["received_at"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()*1000
        if backend-ts <= 10000:  # separate long-delayed backfill from live samples
            live_latency.append(value)
        if "sent_at" in message:
            sent = datetime.fromisoformat(message["sent_at"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()*1000
            push.append(received-sent)
    return {"telemetry_count": telemetry, "sensor_to_capture_all_ms": stats(latency),
            "sensor_to_capture_live_ms": stats(live_latency), "server_push_to_capture_ms": stats(push),
            "note": "Client receipt measures network/application arrival, excludes browser rendering. Synchronize ESP32, server and client clocks; negative values indicate clock skew. Backfill split uses <=10s at backend."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    args = parser.parse_args()
    messages = [json.loads(line) for line in args.jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(analyze(messages), indent=2, ensure_ascii=False))
