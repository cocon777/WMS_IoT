"""Analyze the backend telemetry CSV export, without inventing measurement results."""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def stats(values):
    if not values:
        return {"n": 0, "mean": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {"n": len(values), "mean": sum(values) / len(values),
            "p95": ordered[math.ceil(.95 * len(values)) - 1], "max": ordered[-1]}


def analyze(rows):
    boots = defaultdict(list)
    latency = []
    for row in rows:
        boots[row["boot_id"]].append(int(row["seq"]))
        ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
        received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
        latency.append((received - ts).total_seconds() * 1000)
    runs = {}
    for boot, sequence in boots.items():
        unique = set(sequence)
        expected = max(unique) - min(unique) + 1
        runs[boot] = {"received_unique": len(unique), "seq_start": min(unique), "seq_end": max(unique),
                      "missing_inside_observed_window": expected - len(unique),
                      "duplicate_rows": len(sequence) - len(unique),
                      "gap_percent": 100 * (expected - len(unique)) / expected}
    return {"device_to_backend_ms": stats(latency), "boots": runs,
            "interpretation": "Seq gaps include skipped sensor/time/calibration samples and buffer drops; not pure network loss. No inference outside first/last observed seq. Analyze each device export separately."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with args.csv_file.open(encoding="utf-8-sig", newline="") as stream:
        result = analyze(list(csv.DictReader(stream)))
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
