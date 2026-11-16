"""User and UserDevice ORM models owned by TV3 (integrated with TV2)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow





class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16))                 # Admin | Operator | Viewer
    status: Mapped[str] = mapped_column(String(16), default="active")   # active | disabled
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)      # tăng lên = hủy mọi JWT đã cấp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > utcnow())


class UserDevice(Base):
    """Phạm vi truy cập của Operator/Viewer (Admin thấy tất cả)."""
    __tablename__ = "user_devices"
    __table_args__ = (PrimaryKeyConstraint("user_id", "device_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
