"""Read-only WebSocket capture. Login interactively or use WMS_TOKEN from environment."""
import argparse
import asyncio
import getpass
import json
import os
import time
from pathlib import Path
import httpx
import websockets


async def capture(args, token):
    url = args.base.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws"
    end = time.monotonic() + args.seconds
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Append captures: every run also has a local wall-clock receive time.
    with args.out.open("a", encoding="utf-8") as stream:
        delay = 1
        while time.monotonic() < end:
            try:
                async with websockets.connect(url) as socket:
                    await socket.send(json.dumps({"type": "auth", "token": token}))
                    delay = 1
                    while time.monotonic() < end:
                        raw = await asyncio.wait_for(socket.recv(), timeout=min(35, max(.1, end-time.monotonic())))
                        message = json.loads(raw)
                        message["client_received_epoch_ms"] = time.time_ns() / 1_000_000
                        stream.write(json.dumps(message, ensure_ascii=False) + "\n")
                        stream.flush()
            except (OSError, asyncio.TimeoutError, websockets.ConnectionClosed) as error:
                if isinstance(error, websockets.ConnectionClosed) and error.code == 4401:
                    raise SystemExit("JWT expired/revoked; login again and resume capture. Existing log kept.")
                stream.write(json.dumps({"event": "capture_disconnect", "client_received_epoch_ms": time.time_ns()/1_000_000,
                                         "detail": type(error).__name__}) + "\n")
                await asyncio.sleep(min(delay, max(0, end-time.monotonic())))
                delay = min(delay*2, 30)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--email")
    parser.add_argument("--out", type=Path, default=Path("tests/evidence/ws.jsonl"))
    args = parser.parse_args()
    token = os.getenv("WMS_TOKEN")
    if not token:
        email = args.email or input("Email: ")
        response = httpx.post(args.base.rstrip("/") + "/api/auth/login",
                              json={"email": email, "password": getpass.getpass("Password: ")}, timeout=10)
        response.raise_for_status()
        token = response.json()["access_token"]
    asyncio.run(capture(args, token))


if __name__ == "__main__":
    main()
