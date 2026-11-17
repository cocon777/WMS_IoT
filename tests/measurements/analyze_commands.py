import argparse
import csv
import json
from pathlib import Path
from collections import Counter
from analyze_export import stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()
    with args.csv_file.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    passed = [row for row in rows if row["status"] == "ok"]
    print(json.dumps({"terminal_states": dict(Counter(row["status"] for row in rows)),
                      "successful_sent_to_ack_ms": stats([float(row["sent_to_ack_ms"]) for row in passed if row["sent_to_ack_ms"]]),
                      "successful_request_to_terminal_ms": stats([float(row["request_to_terminal_ms"]) for row in passed]),
                      "note": "Do not mix failed/time-out requests into successful ACK latency. Polling/request time includes client overhead."},
                     ensure_ascii=False, indent=2))
