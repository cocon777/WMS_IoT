from types import SimpleNamespace
import threading
from app import main
from app.mqtt_client import MqttSubscriber
from app.broker_admin import DynSecAdmin


def test_readiness_requires_all_dependencies(db, monkeypatch):
    subscribed = SimpleNamespace(client=SimpleNamespace(is_connected=lambda: True), subscriptions_ready=True)
    admin = SimpleNamespace(_ready=threading.Event())
    monkeypatch.setattr(main, 'get_subscriber', lambda: subscribed)
    monkeypatch.setattr(main, 'get_broker_admin', lambda: admin)
    monkeypatch.setattr(main.settings, 'broker_admin', 'dynsec')
    assert main.ready().status_code == 503
    admin._ready.set()
    assert main.ready().status_code == 200
    subscribed.subscriptions_ready = False
    assert main.ready().status_code == 503


def test_rejected_subscription_and_disconnect_reset_readiness():
    subscriber = MqttSubscriber()
    good = SimpleNamespace(is_failure=False)
    bad = SimpleNamespace(is_failure=True)
    subscriber._on_subscribe(None, None, 1, [good, good, good], None)
    assert subscriber.subscriptions_ready
    subscriber._on_subscribe(None, None, 1, [good, bad], None)
    assert not subscriber.subscriptions_ready
    subscriber.subscriptions_ready = True
    subscriber._on_disconnect(None, None, None, None, None)
    assert not subscriber.subscriptions_ready
    admin = DynSecAdmin()
    admin._on_subscribe(None, None, 1, [good], None)
    assert admin._ready.is_set()
    admin._on_disconnect(None, None, None, None, None)
    assert not admin._ready.is_set()


def test_dynsec_role_uses_explicit_node_topics(monkeypatch):
    admin = DynSecAdmin()
    sent = []
    monkeypatch.setattr(admin, '_send', lambda command: sent.append(command))
    admin.create_client('wms-tank-test', 'not-a-real-password')
    acls = [c for c in sent if c['command'] == 'addRoleACL']
    assert len(acls) == 7
    assert all('%u' not in c['topic'] and c['topic'].startswith('wms/wms-tank-test/') for c in acls)
    assert [c['acltype'] for c in acls].count('subscribeLiteral') == 2
    assert sent[-1]['roles'] == [{'rolename': 'wms-device-wms-tank-test'}]
