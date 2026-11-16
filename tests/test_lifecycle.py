import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import ingest, lifecycle
from app.broker_admin import BrokerError
from app.models import AuditLog, Device, DeviceCredential, Telemetry, User

KW = dict(actor_id=1, ip="127.0.0.1")


@pytest.fixture(autouse=True)
def audit_actor(db):
    # Lifecycle audit rows reference a real user. Keep foreign-key enforcement enabled.
    db.add(User(id=1, email="lifecycle@example.test", password_hash="unused", full_name="Test actor",
                role="Admin", status="active"))
    db.commit()


def new_device(db, code="wms-001"):
    return lifecycle.create_device(db, device_code=code, name="t", hw_version="v1", device_type="pipe", **KW)


def provisioned(db, broker):
    dev = new_device(db)
    lifecycle.provision(db, broker, dev.id, **KW)
    return dev


def test_duplicate_code_conflict(db):
    new_device(db)
    with pytest.raises(lifecycle.Conflict):
        new_device(db)


def test_provision_stores_only_hash_and_calls_broker(db, broker):
    dev = new_device(db)
    dev, secret = lifecycle.provision(db, broker, dev.id, **KW)
    cred = db.scalars(select(DeviceCredential)).one()
    assert dev.state == "Provisioned"
    assert cred.secret_hash == lifecycle.hash_secret(secret) != secret
    assert broker.calls == [("create", "wms-001", secret)]
    assert secret not in " ".join(a.detail for a in db.scalars(select(AuditLog)))


def test_provision_twice_rejected(db, broker):
    dev = provisioned(db, broker)
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.provision(db, broker, dev.id, **KW)


def test_provision_broker_failure_changes_nothing(db, broker):
    dev = new_device(db)
    broker.fail = True
    with pytest.raises(BrokerError):
        lifecycle.provision(db, broker, dev.id, **KW)
    db.expire_all()
    assert db.get(Device, dev.id).state == "Registered"
    assert db.scalars(select(DeviceCredential)).first() is None


@pytest.mark.parametrize("cur,target,ok", [
    ("Registered", "Active", False), ("Provisioned", "Active", True),
    ("Active", "Maintenance", True), ("Fault", "Active", False),
    ("Maintenance", "Active", True), ("Decommissioned", "Active", False),
])
def test_transition_table(cur, target, ok):
    assert lifecycle.can_transition(cur, target) is ok


def test_system_states_cannot_be_set_manually(db, broker):
    dev = provisioned(db, broker)
    lifecycle.change_state(db, broker, dev.id, "Active", **KW)
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.change_state(db, broker, dev.id, "Offline", **KW)


def test_maintenance_disables_then_enables_client(db, broker):
    dev = provisioned(db, broker)
    lifecycle.change_state(db, broker, dev.id, "Active", **KW)
    lifecycle.change_state(db, broker, dev.id, "Maintenance", **KW)
    lifecycle.change_state(db, broker, dev.id, "Active", **KW)
    assert ("enabled", "wms-001", False) in broker.calls and ("enabled", "wms-001", True) in broker.calls


def test_decommission_revokes_and_is_terminal(db, broker):
    dev = provisioned(db, broker)
    lifecycle.change_state(db, broker, dev.id, "Active", **KW)
    lifecycle.change_state(db, broker, dev.id, "Decommissioned", **KW)
    assert ("delete", "wms-001") in broker.calls
    assert db.scalars(select(DeviceCredential)).one().revoked_at is not None
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.change_state(db, broker, dev.id, "Active", **KW)


def test_decommission_broker_failure_keeps_state(db, broker):
    dev = provisioned(db, broker)
    lifecycle.change_state(db, broker, dev.id, "Active", **KW)
    broker.fail = True
    with pytest.raises(BrokerError):
        lifecycle.change_state(db, broker, dev.id, "Decommissioned", **KW)
    db.expire_all()
    assert db.get(Device, dev.id).state == "Active"


def test_S3_backend_layer_ignores_data_after_decommission(db, broker):
    dev = provisioned(db, broker)
    lifecycle.change_state(db, broker, dev.id, "Active", **KW)
    lifecycle.change_state(db, broker, dev.id, "Decommissioned", **KW)
    payload = {"device_id": "wms-001", "boot_id": "a3f9", "seq": 1,
               "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "flow_lpm": 3.2, "flow_total_l": 1.0, "pump_on": False}
    ingest.handle_message("wms/wms-001/telemetry", json.dumps(payload).encode())
    db.expire_all()
    assert db.scalars(select(Telemetry)).first() is None
