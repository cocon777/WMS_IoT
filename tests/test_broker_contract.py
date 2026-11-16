from app.broker_admin import DynSecAdmin


def test_device_subscriptions_use_expandable_username_patterns():
    acls = DynSecAdmin.DEVICE_ACLS
    assert ("subscribePattern", "wms/%u/cmd") in acls
    assert ("subscribePattern", "wms/%u/config") in acls
    assert not any(kind.endswith("Literal") and "%u" in topic for kind, topic in acls)
