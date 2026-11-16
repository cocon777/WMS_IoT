import json
import os
import pathlib
import sys
import tempfile

# Phải đặt trước khi import app.* (engine và settings được tạo lúc import)
_tmp = pathlib.Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["BCRYPT_ROUNDS"] = "4"       # nhanh khi test
os.environ["BROKER_ADMIN"] = "none"
os.environ["WS_ALLOWED_ORIGINS"] = ""  # isolate tests from the host's HTTPS-only Compose .env
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_login_rate_limit():
    from app.login_guard import reset_rate_limiter
    reset_rate_limiter()
    yield
    reset_rate_limiter()

from app.broker_admin import BrokerAdmin, BrokerError  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.errors import PublishError  # noqa: E402


class FakeBroker(BrokerAdmin):
    def __init__(self):
        self.calls, self.fail = [], False

    def _do(self, *call):
        if self.fail:
            raise BrokerError("broker down")
        self.calls.append(call)

    def create_client(self, username, password): self._do("create", username, password)
    def set_enabled(self, username, enabled): self._do("enabled", username, enabled)
    def delete_client(self, username): self._do("delete", username)


@pytest.fixture
def broker():
    return FakeBroker()


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)      # không dùng "with": không chạy lifespan (không bật MQTT)


class FakePublisher:
    def __init__(self):
        self.published, self.retain_flags, self.fail = [], [], False

    def publish(self, topic, payload, qos=1, retain=False):
        if self.fail:
            raise PublishError("broker down")
        self.published.append((topic, json.loads(payload), qos))
        self.retain_flags.append(retain)


@pytest.fixture
def publisher(client):
    from app.main import app
    from app.routers.commands import get_publisher
    fake = FakePublisher()
    app.dependency_overrides[get_publisher] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_publisher, None)


@pytest.fixture
def alert_env(db, monkeypatch):
    """Alert engine chạy đồng bộ: hành động (publish) chạy ngay, sự kiện được gom vào danh sách."""
    from types import SimpleNamespace

    from app import alerts, events
    fake, captured = FakePublisher(), []
    alerts.reset_state()
    alerts.set_publisher(fake)
    monkeypatch.setattr(alerts, "_submit", lambda fn: fn())
    events.set_event_callback(lambda e, p: captured.append((e, p)))
    yield SimpleNamespace(publisher=fake, events=captured)
    events.set_event_callback(lambda e, p: None)
    alerts.set_publisher(None)
    alerts.reset_state()
