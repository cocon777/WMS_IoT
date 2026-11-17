"""Bounded serial capture for TV1 diagnostics; never writes bytes or flashes.

Disconnect the pump adapter first. Opening/closing a USB-UART can still reset
some boards even with DTR/RTS deasserted; record the opening time separately.
Raw logs belong in ignored deployment/runtime, not in a public handoff.
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import time

import serial


def stamp():
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="milliseconds")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ports", nargs="+", required=True)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--output", type=Path, default=Path("deployment/runtime/serial-capture"))
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600 or len(set(args.ports)) != len(args.ports):
        parser.error("Use 1–600 seconds and distinct ports")
    if any(not re.fullmatch(r"COM\d+", port, re.I) for port in args.ports):
        parser.error("Expected Windows COM port names")
    args.output.mkdir(parents=True, exist_ok=True)
    opened = []
    try:
        for name in args.ports:
            port = serial.Serial(port=None, baudrate=115200, timeout=0.1,
                                 rtscts=False, dsrdtr=False)
            port.dtr = False
            port.rts = False
            port.port = name
            port.open()
            try:
                # COM1..COM9 remain reserved Windows device names even with an extension.
                handle = (args.output / f"serial-{name}.log").open("w", encoding="utf-8")
            except Exception:
                port.close()
                raise
            opened.append((name, port, handle))
            line = f"{stamp()} OPEN {name} baud=115200 DTR=0 RTS=0; possible initial driver reset is not a spontaneous failure"
            handle.write(line + "\n")
            handle.flush()
            print(line, flush=True)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            for name, port, handle in opened:
                payload = port.read_until(b"\n", 2048)
                if not payload:
                    continue
                text = payload.decode("utf-8", errors="replace").rstrip()
                line = f"{stamp()} {text}"
                handle.write(line + "\n")
                handle.flush()
                # Keep console concise; full raw logs remain local.
                if any(word in text for word in ("MQTT", "RESET", "BOOT ", "disconnected", "Brownout", "PUMP OFF", "TLS error", "Guru Meditation", "NET ")):
                    print(name + " " + line, flush=True)
        print(f"{stamp()} Capture finished; {len(opened)} ports closing.", flush=True)
    finally:
        for _, port, handle in opened:
            port.close()
            handle.close()


if __name__ == "__main__":
    main()
