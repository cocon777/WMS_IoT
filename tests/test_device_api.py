"""Lớp HTTP của vòng đời thiết bị, site hai node (luồng demo F2/F3) và đổi mật khẩu."""
import pytest

from app.broker_admin import get_broker_admin
from test_api import PW, auth, login, mk_user


@pytest.fixture
def api(client, broker):
    from app.main import app
    app.dependency_overrides[get_broker_admin] = lambda: broker
    yield client
    app.dependency_overrides.pop(get_broker_admin, None)


def admin(api, db):
    mk_user(db, "a@x.vn", "Admin")
    return auth(api, "a@x.vn")


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_device_lifecycle_through_the_api(api, db, broker):
    ha = admin(api, db)
    r = api.post("/api/devices", json={"device_code": "wms-pipe-01", "type": "pipe", "name": "Ống", "hw_version": "v1"},
                 headers=ha)
    assert r.status_code == 201 and r.json()["state"] == "Registered" and r.json()["type"] == "pipe"
    assert r.json()["site_id"] is None
    did = r.json()["id"]

    r = api.post(f"/api/devices/{did}/provision", headers=ha)
    body = r.json()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert body["mqtt_username"] == "wms-pipe-01" and len(body["mqtt_password"]) >= 20
    assert body["device"]["state"] == "Provisioned"
    assert broker.calls == [("create", "wms-pipe-01", body["mqtt_password"])]
    assert body["mqtt_password"] not in api.get(f"/api/devices/{did}", headers=ha).text     # chỉ hiện một lần
    assert api.post(f"/api/devices/{did}/provision", headers=ha).status_code == 409

    r = api.patch(f"/api/devices/{did}/state", json={"state": "Active"}, headers=ha)
    assert r.status_code == 200 and r.json()["state"] == "Active"
    r = api.patch(f"/api/devices/{did}/state", json={"state": "Decommissioned"}, headers=ha)
    assert r.status_code == 422                                     # thu hồi bắt buộc xác nhận
    r = api.patch(f"/api/devices/{did}/state", json={"state": "Decommissioned", "confirm": True}, headers=ha)
    assert r.status_code == 200 and r.json()["state"] == "Decommissioned"
    assert ("delete", "wms-pipe-01") in broker.calls                # tài khoản broker bị xóa (S3)
    assert api.patch(f"/api/devices/{did}/state", json={"state": "Active"}, headers=ha).status_code == 409


def test_only_admin_creates_and_provisions(api, db):
    ha = admin(api, db)
    mk_user(db, "o@x.vn", "Operator")
    did = api.post("/api/devices", json={"device_code": "wms-001", "type": "tank"}, headers=ha).json()["id"]
    ho = auth(api, "o@x.vn")
    assert api.post("/api/devices", json={"device_code": "wms-002", "type": "tank"}, headers=ho).status_code == 403
    assert api.post(f"/api/devices/{did}/provision", headers=ho).status_code == 403
    assert api.post("/api/devices", json={"device_code": "wms-001", "type": "tank"}, headers=ha).status_code == 409


@pytest.mark.parametrize("code", ["WMS-001", "wms/001", "wms+001", "wms#001", "wms%001", "ab", "-wms", "wms 001",
                                  "a" * 65, "wms-001\n", "wms-\u00e9"])
def test_device_code_must_be_safe_for_mqtt_topics(api, db, code):
    assert api.post("/api/devices", json={"device_code": code, "type": "tank"}, headers=admin(api, db)).status_code == 422


@pytest.mark.parametrize("body", [{"device_code": "wms-001"}, {"device_code": "wms-001", "type": "valve"},
                                  {"device_code": "wms-001", "type": ""}, {"device_code": "wms-001", "type": None}])
def test_device_type_is_required_and_must_be_tank_or_pipe(api, db, body):
    assert api.post("/api/devices", json=body, headers=admin(api, db)).status_code == 422


def test_a_site_groups_one_tank_node_and_one_pipe_node(api, db):
    ha = admin(api, db)
    r = api.post("/api/sites", json={"name": "Nhà A", "description": "demo"}, headers=ha)
    assert r.status_code == 201 and r.json()["devices"] == []
    sid = r.json()["id"]
    assert api.post("/api/sites", json={"name": "Nhà A"}, headers=ha).status_code == 409        # trùng tên
    assert api.post("/api/sites", json={"name": ""}, headers=ha).status_code == 422

    tank = api.post("/api/devices", json={"device_code": "wms-tank-01", "type": "tank", "site_id": sid}, headers=ha)
    pipe = api.post("/api/devices", json={"device_code": "wms-pipe-01", "type": "pipe", "site_id": sid}, headers=ha)
    assert tank.status_code == pipe.status_code == 201 and tank.json()["site_id"] == sid

    second_tank = api.post("/api/devices", json={"device_code": "wms-tank-02", "type": "tank", "site_id": sid}, headers=ha)
    assert second_tank.status_code == 409 and "node bồn" in second_tank.json()["detail"]
    assert api.post("/api/devices", json={"device_code": "wms-tank-03", "type": "tank", "site_id": 999},
                    headers=ha).status_code == 422                                              # site không tồn tại

    site = api.get("/api/sites", headers=ha).json()[0]
    assert sorted((d["device_code"], d["type"]) for d in site["devices"]) == [("wms-pipe-01", "pipe"), ("wms-tank-01", "tank")]
    assert [d["device_code"] for d in api.get("/api/devices", params={"type": "pipe"}, headers=ha).json()] == ["wms-pipe-01"]
    assert len(api.get("/api/devices", params={"site_id": sid}, headers=ha).json()) == 2

    # đưa node bồn ra khỏi site thì site nhận được node bồn khác
    r = api.put(f"/api/devices/{tank.json()['id']}/site", json={"site_id": None}, headers=ha)
    assert r.status_code == 200 and r.json()["site_id"] is None
    assert api.post("/api/devices", json={"device_code": "wms-tank-02", "type": "tank", "site_id": sid},
                    headers=ha).status_code == 201
    assert api.put(f"/api/devices/{tank.json()['id']}/site", json={"site_id": sid}, headers=ha).status_code == 409
    assert api.put(f"/api/devices/{pipe.json()['id']}/site", json={"site_id": 999}, headers=ha).status_code == 422
    assert api.put("/api/devices/9999/site", json={"site_id": sid}, headers=ha).status_code == 404


def test_site_changes_need_admin_and_operators_only_see_their_own_nodes(api, db):
    ha = admin(api, db)
    sid = api.post("/api/sites", json={"name": "Nhà A"}, headers=ha).json()["id"]
    tank = api.post("/api/devices", json={"device_code": "wms-tank-01", "type": "tank", "site_id": sid}, headers=ha).json()
    api.post("/api/devices", json={"device_code": "wms-pipe-01", "type": "pipe", "site_id": sid}, headers=ha)
    op, viewer = mk_user(db, "o@x.vn", "Operator"), mk_user(db, "v@x.vn", "Viewer")
    api.put(f"/api/users/{op.id}/devices", json={"device_ids": [tank["id"]]}, headers=ha)
    ho, hv = auth(api, "o@x.vn"), auth(api, "v@x.vn")

    assert api.post("/api/sites", json={"name": "Nhà B"}, headers=ho).status_code == 403
    assert api.put(f"/api/devices/{tank['id']}/site", json={"site_id": None}, headers=ho).status_code == 403
    mine = api.get("/api/sites", headers=ho).json()
    assert len(mine) == 1 and [d["device_code"] for d in mine[0]["devices"]] == ["wms-tank-01"]
    assert api.get("/api/sites", headers=hv).json() == []                 # Viewer chưa được gán node nào


def test_change_password_flow(client, db):
    mk_user(db, "a@x.vn", "Admin")
    h = auth(client, "a@x.vn")
    url, new_pw = "/api/auth/change-password", "NewPassw0rd!"
    assert client.post(url, json={"current_password": "sai-mat-khau", "new_password": new_pw}, headers=h).status_code == 422
    assert client.post(url, json={"current_password": PW, "new_password": "short"}, headers=h).status_code == 422
    assert client.post(url, json={"current_password": PW, "new_password": PW}, headers=h).status_code == 422
    assert client.post(url, json={"current_password": PW, "new_password": "x" * 80}, headers=h).status_code == 422   # > 72 byte
    r = client.post(url, json={"current_password": PW, "new_password": new_pw}, headers=h)
    assert r.status_code == 200
    fresh = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/me", headers=h).status_code == 401          # token cũ bị hủy
    assert client.get("/api/me", headers=fresh).status_code == 200
    assert login(client, "a@x.vn", PW).status_code == 401
    assert login(client, "a@x.vn", new_pw).status_code == 200
    assert client.post(url, json={"current_password": PW, "new_password": new_pw}).status_code == 401   # cần đăng nhập
