"""Password hashing, JWT creation/verification, and get_current_user dependency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, SessionLocal
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

# Precomputed dummy bcrypt hash to mitigate timing-based user enumeration
_DUMMY_BCRYPT_HASH = bcrypt.hashpw(b"dummy_Timing_Defense_Secret_99!", bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode(
    "utf-8"
)



def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt directly.

    Args:
        plain_password: Raw password provided by the user.

    Returns:
        str: Bcrypt hash string suitable for storing in `users.password_hash`.
    """
    return bcrypt.hashpw(
        plain_password.encode("utf-8"), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Args:
        plain_password: Raw password to check.
        password_hash: Stored bcrypt hash from database.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def verify_dummy_password(plain_password: str) -> None:
    """TV3 timing defense; also handle bcrypt's 72-byte input limit."""
    try:
        bcrypt.checkpw(plain_password.encode("utf-8"), _DUMMY_BCRYPT_HASH.encode("utf-8"))
    except ValueError:
        pass


def validate_password_strength(password: str) -> None:
    """Keep the existing account policy; never silently truncate bcrypt input."""
    if len(password) < settings.min_password_len or len(password.encode("utf-8")) > 72:
        raise HTTPException(422, "Mật khẩu không đáp ứng độ dài cho phép")


def create_access_token(
    user_id: int,
    role: str | None = None,
    expires_delta: timedelta | None = None,
    *,
    token_version: int | None = None,
) -> str:
    """Create a short-lived signed JWT containing `sub`, `role`, `exp`, `iat`, `jti`.

    Args:
        user_id: Database ID of the authenticated user.
        role: User role (`admin`, `operator`, `viewer`).
        expires_delta: Custom expiration duration; defaults to `JWT_EXPIRE_MINUTES`.

    Returns:
        str: Encoded JWT string signed with `JWT_SECRET`.
    """
    if token_version is None:
        with SessionLocal() as session:
            user = session.get(User, user_id)
            if user is None or user.status != "active":
                raise HTTPException(401, "User not found or disabled")
            token_version = user.token_version
            role = user.role
    now = datetime.now(timezone.utc)
    delta = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_ttl_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "iat": now,
        "exp": now + delta,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: Raw Bearer JWT string.

    Returns:
        dict[str, Any]: Verified JWT payload dictionary.

    Raises:
        HTTPException: 401 if token is malformed, expired, revoked, or missing claims.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "tv"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload


def revoke_token(token: str) -> None:
    """Persist revocation using the account version, including across restart."""
    payload = decode_access_token(token)
    with SessionLocal() as session:
        user = session.get(User, int(payload["sub"]))
        if user is None or user.token_version != payload.get("tv"):
            raise HTTPException(401, "Token has been revoked")
        user.token_version += 1
        session.commit()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency returning the authenticated active User from Bearer JWT.

    Args:
        credentials: HTTP Authorization Bearer credentials extracted by FastAPI.
        db: Active SQLAlchemy database session.

    Returns:
        User: Authenticated SQLAlchemy User instance whose status is 'active'.

    Raises:
        HTTPException: 401 if Authorization header is missing, token signature/expiry
            is invalid, user no longer exists, or user account status is not 'active'.
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active" or user.token_version != payload.get("tv"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is locked or disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def create_token(user_id: int, token_version: int) -> tuple[str, int]:
    """TV2 compatibility: keep its (JWT, seconds) return contract."""
    return create_access_token(user_id, token_version=token_version), settings.jwt_ttl_minutes * 60


def decode_token(token: str) -> dict[str, Any]:
    """TV2 pure decoder: websocket guards handle JWT errors themselves."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
                      options={"require": ["exp", "sub"]})
dummy_verify = verify_dummy_password
