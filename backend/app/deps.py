"""TV2 Actor interface backed by the TV3 auth/RBAC package."""
from dataclasses import dataclass
from fastapi import Depends, Request
from .db import get_db
from .models import User
from .security.auth import get_current_user
from .security.rbac import require_role


@dataclass
class Actor:
    id: int
    role: str
    ip: str


def current_actor(request: Request, user: User = Depends(get_current_user)) -> Actor:
    return Actor(user.id, user.role, request.client.host if request.client else "")


def require_roles(*roles: str):
    def dependency(request: Request, user: User = Depends(require_role(*roles))) -> Actor:
        return Actor(user.id, user.role, request.client.host if request.client else "")
    return dependency


any_user = require_roles("Admin", "Operator", "Viewer")
