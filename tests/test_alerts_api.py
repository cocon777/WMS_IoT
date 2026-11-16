from test_alerts import Timeline, all_alerts
from test_api import auth, mk_user
from test_commands import mk_dev, setup_operator


def low_alert(dev):
    Timeline(dev, 20).add(10, n=5)


def test_alert_scope_and_workflow(client, db, alert_env):
    d1, d2 = mk_dev(db, "wms-001", dtype="tank"), mk_dev(db, "wms-002", dtype="tank")
    ho = setup_operator(client, db, d1)
    ha = auth(client, "a@x.vn")
    mk_user(db, "o2@x.vn", "Operator")
    viewer = mk_user(db, "v@x.vn", "Viewer")
    client.put(f"/api/users/{viewer.id}/devices", json={"device_ids": [d1.id]}, headers=ha)
    low_alert(d1)
    low_alert(d2)

    page = client.get("/api/alerts", headers=ho).json()
    assert page["total"] == 1 and page["items"][0]["device_code"] == "wms-001"
    assert client.get("/api/alerts", headers=auth(client, "o2@x.vn")).json()["total"] == 0
    assert client.get("/api/alerts", headers=ha).json()["total"] == 2
    hv = auth(client, "v@x.vn")
    assert client.get("/api/alerts", headers=hv).json()["total"] == 1

    mine = page["items"][0]["id"]
    other = next(a.id for a in all_alerts(db) if a.device_id == d2.id)
    assert client.post(f"/api/alerts/{mine}/ack", headers=hv).status_code == 403       # Viewer không xử lý
    assert client.post(f"/api/alerts/{other}/ack", headers=ho).status_code == 404      # ngoài phạm vi (S1)

    r = client.post(f"/api/alerts/{mine}/ack", headers=ho)
    assert r.status_code == 200 and r.json()["state"] == "ack" and r.json()["acked_by"] == "o@x.vn"
    assert client.post(f"/api/alerts/{mine}/ack", headers=ho).status_code == 409       # đã ack
    r = client.post(f"/api/alerts/{mine}/close", headers=ho)
    assert r.status_code == 200 and r.json()["state"] == "closed"
    assert client.post(f"/api/alerts/{mine}/close", headers=ho).status_code == 409
    assert client.get("/api/alerts", params={"state": "closed"}, headers=ho).json()["total"] == 1
    assert client.get("/api/alerts", params={"state": "open"}, headers=ho).json()["total"] == 0
    assert any(e == "alert" and p["state"] == "closed" for e, p in alert_env.events)


def test_alert_type_filter_accepts_the_two_node_types_only(client, db, alert_env):
    d = mk_dev(db, "wms-001", dtype="tank")
    setup_operator(client, db, d)
    ha = auth(client, "a@x.vn")
    assert client.get("/api/alerts", params={"type": "PUMP_NO_RISE"}, headers=ha).status_code == 200
    assert client.get("/api/alerts", params={"type": "PUMP_NO_FLOW"}, headers=ha).status_code == 422      # đã đổi tên


def test_alert_rules_api_and_effect_on_engine_for_the_tank_node(client, db, alert_env):
    d = mk_dev(db, "wms-001", dtype="tank")
    ho = setup_operator(client, db, d)
    rules = client.get(f"/api/devices/{d.id}/alert-rules", headers=ho).json()
    assert [r["type"] for r in rules] == ["LOW_LEVEL", "HIGH_LEVEL", "LEAK_SUSPECT", "DEVICE_OFFLINE"]
    assert rules[0]["params"]["min_duration_s"] == 10

    Timeline(d, 600).add(60)            # nạp cache của engine trước khi sửa luật
    url = f"/api/devices/{d.id}/alert-rules"
    r = client.put(url, json={"rules": [{"type": "LOW_LEVEL", "severity": "critical",
                                         "params": {"min_duration_s": 20}}]}, headers=ho)
    assert r.status_code == 200 and r.json()[0]["severity"] == "critical" and r.json()[0]["params"]["min_duration_s"] == 20

    Timeline(d, 10).add(10, n=3)        # 10 giây liên tục < 20 giây mới của luật
    assert all_alerts(db, "LOW_LEVEL") == []

    for bad in ({"bogus": 1}, {"min_duration_s": -1}, {"cooldown_s": 99999999}):
        r = client.put(url, json={"rules": [{"type": "LOW_LEVEL", "params": bad}]}, headers=ho)
        assert r.status_code == 422
    r = client.put(url, json={"rules": [{"type": "LEAK_SUSPECT", "params": {"clear_s": 30}}]}, headers=ho)
    assert r.status_code == 422         # tham số của node ống, không áp dụng cho node bồn
    dup = {"rules": [{"type": "LOW_LEVEL"}, {"type": "LOW_LEVEL"}]}
    assert client.put(url, json=dup, headers=ho).status_code == 422


def test_the_pipe_node_has_its_own_rules(client, db, alert_env):
    p = mk_dev(db, "wms-pipe-01", dtype="pipe")
    ho = setup_operator(client, db, p)
    url = f"/api/devices/{p.id}/alert-rules"
    assert [r["type"] for r in client.get(url, headers=ho).json()] == ["LEAK_SUSPECT", "PUMP_NO_RISE", "DEVICE_OFFLINE"]
    r = client.put(url, json={"rules": [{"type": "LOW_LEVEL", "enabled": False}]}, headers=ho)
    assert r.status_code == 422 and "không áp dụng" in r.json()["detail"]
    r = client.put(url, json={"rules": [{"type": "PUMP_NO_RISE", "params": {"rise_window_s": 90, "min_rise_pct": 2}},
                                        {"type": "LEAK_SUSPECT", "params": {"usage_start_h": 6, "usage_end_h": 22}}]},
                   headers=ho)
    got = {x["type"]: x["params"] for x in r.json()}
    assert r.status_code == 200 and got["PUMP_NO_RISE"]["rise_window_s"] == 90 and got["LEAK_SUSPECT"]["usage_start_h"] == 6
    assert client.put(url, json={"rules": [{"type": "LEAK_SUSPECT", "params": {"usage_start_h": 25}}]},
                      headers=ho).status_code == 422
    assert client.put(url, json={"rules": [{"type": "PUMP_NO_FLOW"}]}, headers=ho).status_code == 422


def test_viewer_may_read_but_not_change_rules(client, db, alert_env):
    d = mk_dev(db, "wms-001", dtype="tank")
    setup_operator(client, db, d)
    viewer = mk_user(db, "v@x.vn", "Viewer")
    client.put(f"/api/users/{viewer.id}/devices", json={"device_ids": [d.id]}, headers=auth(client, "a@x.vn"))
    hv = auth(client, "v@x.vn")
    url = f"/api/devices/{d.id}/alert-rules"
    assert client.get(url, headers=hv).status_code == 200
    assert client.put(url, json={"rules": [{"type": "LOW_LEVEL", "enabled": False}]}, headers=hv).status_code == 403
