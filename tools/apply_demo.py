"""Apply agreed profiles over HTTPS to existing physical nodes, with version checks."""
import argparse
from getpass import getpass
import json
from pathlib import Path
import ssl
import httpx

root = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(); ap.add_argument('--url', default='https://localhost:8443'); ap.add_argument('--email', required=True)
args = ap.parse_args()
with httpx.Client(base_url=args.url, verify=ssl.create_default_context(cafile=str(root/'deployment/certs/ca.crt')), timeout=15, trust_env=False) as c:
    login = c.post('/api/auth/login', json={'email': args.email, 'password': getpass('Application password: ')})
    login.raise_for_status(); c.headers['Authorization'] = 'Bearer '+login.json()['access_token']
    try:
        response=c.get('/api/devices'); response.raise_for_status(); devices=response.json()
        # Preflight BOTH nodes before changing either profile.
        for code in ('wms-tank-01', 'wms-pipe-01'):
            dev=next((d for d in devices if d['device_code']==code), None)
            if not dev: raise SystemExit(f'Missing {code}; run init_hardware first.')
            latest=c.get(f"/api/devices/{dev['id']}/telemetry/latest"); latest.raise_for_status()
            if latest.json() and latest.json().get('pump_on'): raise SystemExit('Stop the pump before applying profiles; nothing changed.')
            if dev['type']=='tank':
                supported=c.get(f"/api/devices/{dev['id']}/alert-rules"); supported.raise_for_status()
                if not any(r['type']=='LEAK_SUSPECT' and 'window_s' in r['params'] for r in supported.json()):
                    raise SystemExit('Rebuild/restart backend for the seconds-based leak rule before applying profiles; nothing changed.')
        for code, role in [('wms-tank-01','tank'), ('wms-pipe-01','pipe')]:
            dev=next((d for d in devices if d['device_code']==code), None)
            if not dev: raise SystemExit(f'Missing {code}; run init_hardware first.')
            latest=c.get(f"/api/devices/{dev['id']}/telemetry/latest"); latest.raise_for_status()
            if latest.json() and latest.json().get('pump_on'): raise SystemExit('Stop the pump before applying profiles.')
            path=f"/api/devices/{dev['id']}"
            cfg=c.get(path+'/config'); cfg.raise_for_status()
            profile=json.loads((root/'deployment/demo'/f'{role}-config.json').read_text())
            result=c.put(path+'/config',json={**profile,'version':cfg.json()['version']});result.raise_for_status()
            rules=json.loads((root/'deployment/demo'/f'{role}-alert-rules.json').read_text())
            result_rules=c.put(path+'/alert-rules',json=rules);result_rules.raise_for_status()
            result=c.post(path+'/config/publish');result.raise_for_status()
            print(code, 'server version', result.json()['version'], 'delivery', result.json()['delivery'], 'node', result.json()['sync_status'])
            if result.json()['delivery']=='failed':raise SystemExit('Saved profile but broker delivery failed; retry config/publish after broker recovery.')
    finally:
        c.post('/api/auth/logout')
