"""Isolated headless browser check against real FastAPI/SQLite, fake MQTT publisher only.

Does not connect to devices, send real pump commands, or use any user's database.
Run with .venv/Scripts/python tools/smoke_frontend.py after installing playwright.
"""
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
tmp = tempfile.TemporaryDirectory(prefix="wms-ui-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tmp.name) / "smoke.db")
os.environ["JWT_SECRET"] = secrets.token_hex(32)
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["BROKER_ADMIN"] = "none"
os.environ["WS_ALLOWED_ORIGINS"] = ""  # isolated HTTP browser test, independent of demo HTTPS .env
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app
from app.db import Base, engine, SessionLocal
from app import accounts, ingest, commands, alerts
from app.models import Device, Site, UserDevice, DeviceConfig
from app.routers.commands import get_publisher
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright
import uvicorn


def main():
    password = secrets.token_urlsafe(18)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        admin = accounts.create_user(s, email="smoke-admin@example.test", password=password, full_name="Smoke Admin",
                                     role="Admin", actor_id=None, ip="test")
        viewer = accounts.create_user(s, email="smoke-viewer@example.test", password=password, full_name="Smoke Viewer",
                                      role="Viewer", actor_id=None, ip="test")
        site = Site(name="Smoke site", description="Isolated test")
        s.add(site)
        s.flush()
        tank = Device(device_code="wms-tank-smoke", name="Tank smoke", type="tank", site_id=site.id, state="Active", online=True)
        pipe = Device(device_code="wms-pipe-smoke", name="Pipe smoke", type="pipe", site_id=site.id, state="Active", online=True)
        s.add_all([tank, pipe])
        s.flush()
        for dev in (tank, pipe):
            s.add(UserDevice(user_id=viewer.id, device_id=dev.id))
            profile = json.loads((ROOT / 'deployment/demo' / f'{dev.type}-config.json').read_text())
            for key, value in profile.items():
                s.add(DeviceConfig(device_id=dev.id, key=key, value=json.dumps(value), version=1))
        s.commit()

    from datetime import datetime, timezone, timedelta
    def sample(code, seq, **fields):
        payload = {"device_id": code, "boot_id": "ui-smoke", "seq": seq,
                   "ts": datetime.now(timezone.utc).isoformat(), "rssi": -60, **fields}
        ingest.handle_message(f"wms/{code}/telemetry", json.dumps(payload).encode())

    sent = []
    class Publisher:
        def publish(self, topic, payload, qos=1, retain=False):
            data = json.loads(payload)
            if topic.endswith("/cmd"):
                sent.append(data)
                threading.Timer(.05, lambda: commands.handle_ack(topic.split("/")[1], {
                    "cmd_id": data["cmd_id"], "result": "ok", "reason": None})).start()

    fake_publisher = Publisher()
    app.dependency_overrides[get_publisher] = lambda: fake_publisher
    app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend-smoke")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Smoke server startup timeout")
        time.sleep(.05)
    errors = []
    layouts = []
    try:
        alerts.set_publisher(fake_publisher)
        sample("wms-tank-smoke", 1, distance_cm=10, level_pct=50)
        sample("wms-pipe-smoke", 1, flow_lpm=0, flow_total_l=1, pump_on=False)
        with sync_playwright() as p:
            browser = p.chromium.launch(**({"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}), headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:8765")
            def login(email):
                page.locator("#email").fill(email)
                page.locator("#password").fill(password)
                page.locator("#login button").click()
                page.locator("article").nth(1).wait_for()
                page.wait_for_function("document.getElementById('connection').textContent.includes('đã kết nối')")
            login("smoke-admin@example.test")
            assert not page.locator("#login").is_visible()
            assert "50.0 %" in page.locator("#devices").inner_text()
            assert page.locator('#kpi-level-val').inner_text() == '50.0'
            assert page.locator('#kpi-flow-badge').inner_text() == 'YF-S401'
            # Manual refresh must acknowledge a server read, report failures, and recover.
            def refresh_and_wait(state='success'):
                page.locator('#refresh').click()
                page.wait_for_function("state => {const n=document.getElementById('refresh-feedback');return !n.hidden&&n.dataset.state===state;}", arg=state)
                assert page.locator('#refresh').is_enabled()
            refresh_and_wait()
            assert 'Đã làm mới từ máy chủ' in page.locator('#refresh-feedback').inner_text()
            assert page.locator('#refresh').get_attribute('data-last-success')
            page.route('**/api/devices', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Test unavailable"}'))
            refresh_and_wait('error')
            assert 'Làm mới thất bại' in page.locator('#refresh-feedback').inner_text()
            page.unroute('**/api/devices')
            refresh_and_wait()
            sample("wms-tank-smoke", 2, distance_cm=8, level_pct=70)
            page.wait_for_function("document.getElementById('devices').textContent.includes('70.0 %')")
            page.wait_for_function("document.getElementById('kpi-level-val').textContent==='70.0'")
            # Buffered historical samples must not replace a newer live reading.
            sample("wms-tank-smoke", 99, ts=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat(), distance_cm=16.9, level_pct=1)
            page.wait_for_timeout(500)
            assert page.locator('#kpi-level-val').inner_text() == '70.0'

            page.get_by_role("button", name="Bật 3 giây").click()
            page.wait_for_function("document.getElementById('command').textContent.includes(': ok')")
            sample("wms-tank-smoke", 3, distance_cm=8.6, level_pct=70)
            page.get_by_role("button", name="Bơm tới đầy", exact=True).click()
            page.wait_for_function("document.getElementById('command').textContent.includes(': ok')")
            assert any(item.get('duration_s') == 60 for item in sent)
            sample("wms-pipe-smoke", 2, flow_lpm=1.08, flow_total_l=1.1, pump_on=True)
            sample("wms-tank-smoke", 4, distance_cm=7, level_pct=100)
            deadline = time.monotonic() + 5
            while not any(item['value'] == 'off' for item in sent):
                if time.monotonic() > deadline:
                    raise AssertionError('Full-level OFF was not published')
                time.sleep(.02)
            sample("wms-pipe-smoke", 3, flow_lpm=0, flow_total_l=1.4, pump_on=False)
            page.wait_for_function("document.getElementById('devices').textContent.includes('100.0 %')")
            assert page.get_by_role('button', name='Bơm tới đầy', exact=True).is_disabled()
            page.get_by_role('switch', name='Chế độ tự động').click()
            page.wait_for_function("document.getElementById('auto-toggle').getAttribute('aria-checked')==='true'")
            page.get_by_role('switch', name='Chế độ tự động').click()
            page.wait_for_function("document.getElementById('auto-toggle').getAttribute('aria-checked')==='false'")
            page.wait_for_function("!document.getElementById('auto-toggle').disabled")
            assert page.locator('#navigation button').count() == 6
            assert page.locator('#digital-twin-container').get_by_text('HC-SR04').count() == 0
            assert page.locator('#kpi-alert-count').is_visible()
            assert page.evaluate("document.getElementById('main-content').scrollHeight <= document.getElementById('main-content').clientHeight+2")
            page.screenshot(path=str(ROOT / "tests/results/frontend-admin.png"), full_page=True)
            # Management pages use real API/DB mutations; only MQTT transport is replaced.
            def capture(name):
                layouts.append({'view':name,**page.evaluate("({viewport:[innerWidth,innerHeight],mainClient:document.getElementById('main-content').clientHeight,mainScroll:document.getElementById('main-content').scrollHeight,bodyWidth:document.documentElement.scrollWidth})")})
                page.screenshot(path=str(ROOT / f'tests/results/compact-{name}.png'), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator('[data-view=equipment]').click()
            page.get_by_role('tab', name='Cụm Site', exact=True).click()
            # An out-of-band change is not visible until the current page is refreshed.
            with SessionLocal() as external:
                extra_site = Site(name='External refresh check', description='Temporary fixture')
                external.add(extra_site)
                external.commit()
                extra_id = extra_site.id
            assert page.locator('.site-title').filter(has_text='External refresh check').count() == 0
            refresh_and_wait()
            page.locator('.site-title').filter(has_text='External refresh check').wait_for()
            with SessionLocal() as external:
                external.delete(external.get(Site, extra_id))
                external.commit()
            refresh_and_wait()
            page.get_by_role('button', name='Tạo khu vực', exact=True).click()
            page.locator('#editor input[name=name]').fill('UI test site')
            page.locator('#editor input[name=description]').fill('<script>inert</script>')
            page.locator('#editor button[type=submit]').click()
            page.locator('.site-title').filter(has_text='UI test site').wait_for()
            page.locator('[data-view=dashboard]').click()
            page.locator('#site-select').select_option(label='UI test site')
            assert page.locator('#devices article').count() == 0
            assert page.locator('#kpi-level-val').inner_text() == '--'
            assert page.locator('#kpi-pump-text').inner_text() == 'Chưa có dữ liệu'
            page.locator('#site-select').select_option(value='')
            capture('dashboard')
            page.locator('[data-view=equipment]').click()
            page.get_by_role('tab', name='Danh sách node', exact=True).click()
            page.get_by_role('button', name='Đăng ký thiết bị', exact=True).click()
            page.locator('#editor input[name=device_code]').fill('ui-created-tank')
            page.locator('#editor input[name=name]').fill('UI created tank')
            page.locator('#editor button[type=submit]').click()
            page.get_by_role('cell', name='ui-created-tank', exact=False).wait_for()
            capture('devices')
            page.locator('#management select[name=type]').select_option('pipe')
            assert page.locator('#management tbody tr').count() == 1
            page.locator('#management select[name=type]').select_option('')
            page.locator('#management .table-search').fill('ui-created-tank')
            assert page.locator('#management tbody tr').count() == 1
            page.locator('#management .table-search').fill('')
            page.get_by_role('button', name='Chi tiết', exact=True).first.click()
            page.get_by_role('button', name='Xem lịch sử', exact=True).wait_for()
            page.locator('#editor-close').click()
            page.evaluate("async()=>{for(let i=0;i<8;i++)await api('/api/devices',{method:'POST',body:JSON.stringify({device_code:'pagination-node-'+i,type:'tank',name:'Pagination '+i})});await refresh();await showView('equipment');}")
            page.locator('.table-pager').get_by_role('button', name='Sau', exact=True).click()
            assert 'Trang 2/' in page.locator('.table-pager').inner_text()
            page.locator('.table-search').fill('ui-created-tank')
            page.get_by_role('cell', name='ui-created-tank', exact=False).wait_for()
            page.locator('.table-search').fill('')
            page.get_by_role('tab', name='Cấu hình', exact=True).click()
            page.locator('#management input[name=sample_interval_s]').fill('2')
            page.get_by_role('button', name='Lưu và gửi cấu hình').click()
            page.wait_for_function("document.getElementById('management').textContent.includes('Server v4')")
            page.get_by_role('tab', name='Quy tắc cảnh báo').click()
            page.get_by_role('button', name='Sửa quy tắc').first.click()
            page.locator('#editor button[type=submit]').click()
            page.locator('#editor').wait_for(state='hidden')
            capture('rules')
            page.get_by_role('tab', name='Thông số vận hành').click()
            capture('configuration')
            page.get_by_role('tab', name='Cụm Site', exact=True).click()
            capture('sites')
            page.locator('[data-view=history]').click()
            page.locator('#management svg.chart').first.wait_for()
            capture('history')
            with page.expect_download() as download:
                page.get_by_role('button', name='Xuất CSV').click()
            assert download.value.suggested_filename.endswith('.csv')
            page.screenshot(path=str(ROOT / 'tests/results/frontend-history.png'), full_page=True)
            page.locator('[data-view=warnings]').click()
            capture('alerts')
            page.get_by_role('button', name='Xác nhận', exact=True).first.click()
            page.locator('[data-view=people]').click()
            page.get_by_role('button', name='Tạo người dùng', exact=True).click()
            page.locator('#editor input[name=email]').fill('ui-created@example.test')
            page.locator('#editor input[name=password]').fill(password)
            page.locator('#editor button[type=submit]').click()
            page.locator('.user-cell small').filter(has_text='ui-created@example.test').wait_for()
            row = page.get_by_role('row').filter(has_text='ui-created@example.test')
            capture('users')
            row.get_by_role('button', name='Gán thiết bị').click()
            page.locator('#editor input[type=checkbox]').first.check()
            page.locator('#editor button[type=submit]').click()
            page.locator('#editor').wait_for(state='hidden')
            page.evaluate("async()=>{for(let i=0;i<5;i++)await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'ui-created@example.test',password:'wrong-test-password'})});await showView('people');}")
            row = page.get_by_role('row').filter(has_text='ui-created@example.test')
            assert 'Tạm khóa đăng nhập' in row.inner_text()
            capture('users-locked')
            row.get_by_role('button', name='Sửa tài khoản').click()
            page.locator('#editor select[name=unlock]').select_option('true')
            page.locator('#editor button[type=submit]').click()
            page.locator('#editor').wait_for(state='hidden')
            assert 'Tạm khóa đăng nhập' not in page.locator('#management').inner_text()
            page.locator('[data-view=audit]').click()
            page.locator('#management input[name=action]').fill('user.create')
            page.get_by_role('button', name='Lọc nhật ký', exact=True).click()
            page.get_by_role('cell', name='user.create', exact=True).first.wait_for()
            capture('audit')
            page.locator('#account-toggle').click()
            page.get_by_role('button', name='Hồ sơ cá nhân', exact=True).click()
            page.get_by_role('button', name='Đổi họ tên', exact=True).click()
            page.locator('#editor input[name=full_name]').fill('Updated admin')
            page.locator('#editor button[type=submit]').click()
            page.locator('#editor').wait_for(state='hidden')
            assert page.locator('#error').inner_text() == ''
            page.locator('#account-toggle').click()
            page.locator('#account-menu').get_by_role('button', name='Đổi mật khẩu', exact=True).click()
            page.locator('#editor input[name=current_password]').fill(password)
            page.locator('#editor input[name=new_password]').fill(password+'-new')
            page.locator('#editor button[type=submit]').click()
            page.locator('#editor').wait_for(state='hidden')
            page.wait_for_function("document.getElementById('connection').textContent.includes('đã kết nối')")
            page.locator("#account-toggle").click()
            page.locator("#logout").click()
            page.locator("#login").wait_for(state="visible")
            login("smoke-viewer@example.test")
            assert page.get_by_role("button", name="Bật 3 giây").count() == 0
            assert page.get_by_role('button', name='Bơm tới đầy', exact=True).count() == 0
            assert page.get_by_role('switch', name='Chế độ tự động').count() == 0
            assert not page.locator("#command-panel").is_visible()
            assert page.locator("#command").inner_text() == "Chưa gửi lệnh"
            assert page.locator("#error").inner_text() == ""
            assert page.locator('[data-view=people]').count() == 0
            assert page.locator('[data-view=configuration]').count() == 0
            page.locator('[data-view=history]').click()
            page.locator('#management svg.chart').first.wait_for()
            assert page.get_by_role('button', name='Xuất CSV').count() == 0
            page.locator('[data-view=dashboard]').click()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(ROOT / "tests/results/frontend-viewer-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            browser.close()
        assert errors == [], errors
        assert all(x["mainScroll"] <= x["mainClient"]+2 for x in layouts), layouts
        result = {"status": "passed", "checks": ["login Admin and login form hidden", "real API snapshot", "real WebSocket update", "command sent/ACK with fake MQTT", "fill command60s and full100% OFF", "AUTO toggle and return to manual with OFF", "full level blocks ON buttons",
                                                      "TV3 KPI from real WS; YF-S401; selecting empty site has no cross-site data", "real management CRUD: sites/devices/users/scopes/profile", "config version + alert rule edit", "history chart + authenticated CSV download", "alert ACK + audit", "logout clears previous command", "Viewer navigation/CSV/command restrictions", "mobile no horizontal overflow", "no JS runtime errors", "manual refresh success/error/recovery feedback and active management page reload"],
                  "layout": layouts, "limits": "Temporary SQLite and fake MQTT publisher; no physical devices, Docker or MySQL tested."}
        (ROOT / "tests/results/frontend-smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        engine.dispose()
        tmp.cleanup()


if __name__ == "__main__":
    main()
