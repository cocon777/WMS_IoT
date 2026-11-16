import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditLog, User


# Based on TV3 services.audit; recursive and transactional in this integration.
_SENSITIVE = re.compile(r"password|passwd|secret|token|jwt|authorization|credential", re.I)
_TEXT_SECRET = re.compile(
    r'''((?:["']?)(?:[\w.-]*(?:password|passwd|secret|token|jwt|authorization|credential)[\w.-]*)(?:["']?)\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|Bearer\s+[^\s,;}]+|[^\s,;}]+)''',
    re.I,
)


def sanitize_detail(detail: Any) -> str:
    def clean(value, depth=0):
        if depth > 12:
            return "[TRUNCATED]"
        if isinstance(value, dict):
            return {str(k): "[REDACTED]" if _SENSITIVE.search(str(k)) else clean(v, depth + 1)
                    for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v, depth + 1) for v in value]
        if isinstance(value, str):
            return re.sub(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]",
                          _TEXT_SECRET.sub(r'\1"[REDACTED]"', value), flags=re.I)
        return value
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except (ValueError, TypeError):
            return clean(detail)
    result = clean(detail)
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)




def log(
    db: Session,
    user: User | int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    ip: str | None = None,
    detail: str | dict[str, Any] | None = None,
) -> AuditLog:
    """Record a security or operational event in the `audit_logs` table.

    Shared interface function handed off to TV2 (for pump commands, config
    updates, device provisioning/revocation) and used across TV3 modules.
    Does not commit the caller's transaction. Automatically scrubs sensitive keys (`password`, `token`, `secret`) from `detail`.

    Args:
        db: Active SQLAlchemy database session.
        user: Authenticated `User` ORM instance, user ID (`int`), or `None`
            (e.g. failed login for unknown account).
        action: Short uppercase action code (e.g. `'LOGIN_SUCCESS'`, `'SEND_COMMAND'`).
        target_type: Resource type affected (e.g. `'user'`, `'device'`, `'endpoint'`).
        target_id: Identifier of the target resource (converted to `str` if provided).
        ip: Client IPv4/IPv6 address string.
        detail: Optional human-readable string or JSON-serializable dict with non-sensitive context.

    Returns:
        AuditLog: Pending `AuditLog` ORM record; caller owns commit/rollback.

    Raises:
        SQLAlchemyError: If the database write fails.
    """
    if isinstance(user, User):
        resolved_user_id: int | None = user.id
    elif isinstance(user, int):
        resolved_user_id = user
    else:
        resolved_user_id = None

    entry = AuditLog(
        user_id=resolved_user_id,
        action=action,
        target_type=target_type or "",
        target_id=str(target_id) if target_id is not None else "",
        ip=(ip or "")[:45],
        detail=sanitize_detail(detail)[:512],
    )
    db.add(entry)
    return entry

def write_audit(s: Session, user_id: int | None, action: str, target_type: str,
                target_id: int | str, ip: str, detail: str = "") -> None:
    """TV2 API delegates to the TV3 service without a second transaction."""
    log(s, user_id, action, target_type, target_id, ip, detail)


_sanitize_detail = sanitize_detail
