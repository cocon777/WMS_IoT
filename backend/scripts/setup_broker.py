"""Bootstrap separate data-plane and administration accounts on the real dynsec broker."""
from app.broker_admin import DynSecAdmin


def main():
    from app.config import settings
    if settings.broker_admin != "dynsec":
        return
    if not settings.mqtt_admin_username or settings.mqtt_admin_username == settings.mqtt_username:
        raise RuntimeError("Set distinct MQTT_ADMIN_USERNAME and MQTT_USERNAME before deployment")
    admin = DynSecAdmin()
    admin.start()
    try:
        admin._send({"command": "setDefaultACLAccess", "acls": [
            {"acltype": "publishClientSend", "allow": False},
            {"acltype": "publishClientReceive", "allow": False},
            {"acltype": "subscribe", "allow": False},
            {"acltype": "unsubscribe", "allow": True}]})
        admin._send_ignoring({"command": "createRole", "rolename": "wms-backend"}, "already exists")
        for acltype in ("publishClientSend", "publishClientReceive", "subscribePattern"):
            admin._send_ignoring({"command": "addRoleACL", "rolename": "wms-backend", "acltype": acltype,
                                 "topic": "wms/#", "allow": True, "priority": 0}, "already exists")
        admin._send_ignoring({"command": "createClient", "username": settings.mqtt_username,
                             "password": settings.mqtt_password}, "already exists")
        # Keep persisted credentials unchanged on restart. Rotate explicitly if .env changes.
        admin._assign_role(settings.mqtt_username, "wms-backend")
        print("Broker application ACL configured")
    finally:
        admin.stop()


if __name__ == "__main__":
    main()
