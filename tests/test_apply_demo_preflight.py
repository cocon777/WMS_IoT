"""Profile tool must not half-apply limits before discovering an unsafe/old stack."""
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('pump_on,modern_backend,message', [
    (True, True, 'Stop the pump'),
    (False, False, 'Rebuild/restart backend'),
])
def test_profile_preflight_changes_neither_node(monkeypatch, pump_on, modern_backend, message):
    writes = []
    def response(value):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: value)
    class Client:
        def __init__(self, *args, **kwargs): self.headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, path, **kwargs):
            if path == '/api/auth/login': return response({'access_token':'fixture-token'})
            assert path == '/api/auth/logout'
            return response({})
        def get(self, path):
            if path == '/api/devices': return response([
                {'id':1, 'type':'tank', 'device_code':'wms-tank-01'},
                {'id':2, 'type':'pipe', 'device_code':'wms-pipe-01'},
            ])
            if path.endswith('alert-rules'):
                return response([{'type':'LEAK_SUSPECT','params':{'window_s':0} if modern_backend else {}}])
            if path.endswith('telemetry/latest'): return response({'pump_on':pump_on and '/2/' in path})
            raise AssertionError(path)
        def put(self, path, **kwargs): writes.append(path); raise AssertionError('Unexpected mutation')
    monkeypatch.setattr('httpx.Client', Client)
    monkeypatch.setattr('ssl.create_default_context', lambda **kwargs: object())
    monkeypatch.setattr('getpass.getpass', lambda *args: 'fixture-password')
    monkeypatch.setattr('sys.argv', ['apply_demo.py','--email','fixture@example.test'])
    with pytest.raises(SystemExit, match=message):
        runpy.run_path(str(Path(__file__).parents[1]/'tools/apply_demo.py'), run_name='__main__')
    assert writes == []
