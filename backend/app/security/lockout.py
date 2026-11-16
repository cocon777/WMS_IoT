"""TV3 sliding-window login limit, adapted for bounded memory and trusted proxy handling."""
from collections import OrderedDict, deque
import ipaddress
import threading
from time import monotonic

from fastapi import HTTPException, Request
from ..config import settings

_buckets: OrderedDict[str, deque] = OrderedDict()
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(peer)
        trusted = any(address in ipaddress.ip_network(c.strip(), strict=False)
                      for c in settings.trusted_proxy_cidrs.split(",") if c.strip())
        forwarded = request.headers.get("x-real-ip", "")
        if trusted and forwarded:
            return str(ipaddress.ip_address(forwarded))
    except ValueError:
        pass
    return peer


def check_login_rate_limit(request: Request) -> None:
    if settings.login_ip_max_attempts <= 0:
        return
    ip, now = client_ip(request), monotonic()
    with _lock:
        bucket = _buckets.setdefault(ip, deque())
        while bucket and bucket[0] <= now - settings.login_ip_window_s:
            bucket.popleft()
        _buckets.move_to_end(ip)
        while len(_buckets) > 10000:
            _buckets.popitem(last=False)
        if len(bucket) >= settings.login_ip_max_attempts:
            retry = max(1, int(settings.login_ip_window_s - (now - bucket[0])) + 1)
            raise HTTPException(status_code=429, detail="Quá nhiều lần đăng nhập từ địa chỉ này, vui lòng thử lại.",
                                headers={"Retry-After": str(retry)})
        bucket.append(now)


def reset_rate_limiter() -> None:
    with _lock:
        _buckets.clear()


# TV3 shared interface.
get_client_ip = client_ip
