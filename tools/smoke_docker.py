"""Real TLS/HTTPS/MySQL/dynsec integration with SOFTWARE nodes, isolated wms-verify only.

Requires four services of `docker compose -p wms-verify` on HTTPS18443/MQTT18884.
Creates only explicitly named verification users/devices. Never sends to wms-tank-01/pipe-01.
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import ssl
import subprocess
import threading
import time
from datetime import datetime, timezone
import httpx
import paho.mqtt.client as mqtt

ROOT=Path(__file__).resolve().parents[1]
DOCKER=shutil.which('docker') or r'D:\DockerDesktop\resources\bin\docker.exe'
CA=ROOT/'deployment/certs/ca.crt'
suffix=secrets.token_hex(3)
password=secrets.token_urlsafe(20)
email=f'verify-{suffix}@example.test'
env={**os.environ,'WMS_USER_PASSWORD':password,'HTTPS_PORT':'18443','MQTT_TLS_PORT':'18884','WS_ALLOWED_ORIGINS':'https://localhost:18443,https://127.0.0.1:18443'}
run=subprocess.run([DOCKER,'--context','desktop-linux','compose','-p','wms-verify','exec','-T','-e','WMS_USER_PASSWORD','backend','python','-m','scripts.create_user','--email',email,'--role','Admin'],cwd=ROOT,env=env,capture_output=True,encoding='utf-8')
if run.returncode: raise SystemExit('Test Admin creation failed: '+run.stderr)
checks=[]
def eventually(fn, timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=fn()
        if value:return value
        time.sleep(.1)
    raise AssertionError('Timed out waiting for expected integration result')

class Node:
    def __init__(self, code, password):
        self.code=code;self.commands=[];self.configs=[];self.subs={};self.connected=threading.Event();self.seq=0
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='verify-'+code)
        self.client.username_pw_set(code,password);self.client.tls_set(ca_certs=str(CA))
        def connected(c,u,f,reason,p):
            if not reason.is_failure:self.connected.set()
        self.client.on_connect=connected
        self.client.on_disconnect=lambda *args:self.connected.clear()
        self.client.on_subscribe=lambda c,u,mid,reasons,p:self.subs.update({mid:reasons})
        def receive(c,u,m):
            payload=json.loads(m.payload)
            if m.topic.endswith('/cmd'):
                self.commands.append(payload)
                c.publish(f'wms/{code}/ack',json.dumps({'cmd_id':payload['cmd_id'],'result':'ok'}),qos=1)
            elif m.topic.endswith('/config'):
                self.configs.append(payload)
                c.publish(f'wms/{code}/status',json.dumps({'status':'online','config_version':payload['version'],'fw_version':'software-verification'}),qos=1)
        self.client.on_message=receive;self.client.connect('localhost',18884,30);self.client.loop_start()
        assert self.connected.wait(5),'TLS MQTT connection failed'
        self.subscribe(f'wms/{code}/cmd',True);self.subscribe(f'wms/{code}/config',True)
    def subscribe(self, topic, allowed):
        rc,mid=self.client.subscribe(topic,qos=1);eventually(lambda:mid in self.subs)
        assert all(not r.is_failure for r in self.subs[mid]) == allowed,topic
    def publish(self, channel, payload):
        info=self.client.publish(f'wms/{self.code}/{channel}',json.dumps(payload),qos=1);info.wait_for_publish(3)
    def sample(self, **values):
        self.seq+=1;self.publish('telemetry',{'device_id':self.code,'boot_id':suffix,'seq':self.seq,'ts':datetime.now(timezone.utc).isoformat(),**values})
    def stop(self):self.client.disconnect();self.client.loop_stop()

nodes=[]
try:
    with httpx.Client(base_url='https://localhost:18443',verify=ssl.create_default_context(cafile=str(CA)),trust_env=False,timeout=15) as api:
        def call(method,path,**kw):
            res=api.request(method,path,**kw);res.raise_for_status();return None if res.status_code==204 else res.json()
        assert call('GET','/api/ready')['status']=='ready';checks.append('HTTPS certificate chain and hostname + DB/MQTT/dynsec readiness')
        session=call('POST','/api/auth/login',json={'email':email,'password':password});api.headers['Authorization']='Bearer '+session['access_token']
        site=call('POST','/api/sites',json={'name':'SOFTWARE verification '+suffix})
        registered=[]
        for role in ('tank','pipe'):
            code=f'verify-{role}-{suffix}'
            dev=call('POST','/api/devices',json={'device_code':code,'name':'SOFTWARE TEST '+role,'type':role,'site_id':site['id']})
            provision=call('POST',f"/api/devices/{dev['id']}/provision")
            node=Node(code,provision['mqtt_password']);nodes.append(node);registered.append(dev)
            node.publish('status',{'status':'online','fw_version':'software-verification'})
            eventually(lambda:call('GET',f"/api/devices/{dev['id']}")['state']=='Active')
            profile=json.loads((ROOT/'deployment/demo'/f'{role}-config.json').read_text())
            result=call('PUT',f"/api/devices/{dev['id']}/config",json=profile)
            assert result['delivery']=='published'
            eventually(lambda:node.configs)
            eventually(lambda:call('GET',f"/api/devices/{dev['id']}/config")['sync_status']=='applied')
            call('PUT',f"/api/devices/{dev['id']}/alert-rules",json=json.loads((ROOT/'deployment/demo'/f'{role}-alert-rules.json').read_text()))
        checks.append('Dynamic provisioning, authenticated TLS MQTT, heartbeat activation, retained config and applied version')
        tank,pipe=nodes;td,pd=registered
        tank.subscribe(f'wms/{pipe.code}/cmd',False)
        tank.subscribe('$CONTROL/dynamic-security/v1/response',False)
        checks.append('Device cross-node and dynsec subscriptions denied')
        tank.sample(distance_cm=14.2,level_pct=28);pipe.sample(flow_lpm=0,flow_total_l=0,pump_on=False)
        eventually(lambda:call('GET',f"/api/devices/{td['id']}/telemetry/latest"))
        command=call('POST',f"/api/devices/{pd['id']}/commands",json={'value':'on','duration_s':60})
        eventually(lambda:any(x['cmd_id']==command['cmd_id'] for x in pipe.commands))
        eventually(lambda:call('GET',f"/api/devices/{pd['id']}/commands/{command['cmd_id']}")['status']=='ok')
        pipe.sample(flow_lpm=1.08,flow_total_l=.02,pump_on=True);tank.sample(distance_cm=5,level_pct=100)
        eventually(lambda:any(c['value']=='off' for c in pipe.commands))
        checks.append('REST ON -> real broker -> software pipe ACK -> MySQL; tank100% -> server OFF')
        # AUTO: reset LOW episode above hysteresis, then keep fresh level/pipe telemetry for 12s.
        pipe.sample(flow_lpm=0,flow_total_l=.9,pump_on=False);tank.sample(distance_cm=11,level_pct=50)
        call('PUT',f"/api/devices/{td['id']}/config",json={'auto_mode':True})
        before=sum(c['value']=='on' for c in pipe.commands)
        for _ in range(12):
            tank.sample(distance_cm=14.2,level_pct=28);pipe.sample(flow_lpm=0,flow_total_l=.9,pump_on=False);time.sleep(1)
        eventually(lambda:sum(c['value']=='on' for c in pipe.commands)>before)
        pipe.sample(flow_lpm=1.08,flow_total_l=1,pump_on=True);tank.sample(distance_cm=5,level_pct=100)
        eventually(lambda:len([c for c in pipe.commands if c['value']=='off'])>=2)
        call('PUT',f"/api/devices/{td['id']}/config",json={'auto_mode':False})
        checks.append('AUTO LOW30% sustained10s -> ON once -> HIGH100% OFF through real broker')
        viewer=call('POST','/api/users',json={'email':f'viewer-{suffix}@example.test','password':password,'role':'Viewer'})
        call('PUT',f"/api/users/{viewer['id']}/devices",json={'device_ids':[td['id'],pd['id']]})
        token=call('POST','/api/auth/login',json={'email':viewer['email'],'password':password})['access_token']
        assert api.post(f"/api/devices/{pd['id']}/commands",headers={'Authorization':'Bearer '+token},json={'value':'on'}).status_code==403
        checks.append('Viewer control denied by server')
        call('PATCH',f"/api/devices/{pd['id']}/state",json={'state':'Maintenance'})
        eventually(lambda:not pipe.connected.is_set())
        call('PATCH',f"/api/devices/{pd['id']}/state",json={'state':'Decommissioned','confirm':True})
        call('PATCH',f"/api/devices/{td['id']}/state",json={'state':'Decommissioned','confirm':True})
        checks.append('Maintenance disconnect and permanent credential revocation')
        call('POST','/api/auth/logout')
    result={'status':'passed','checks':checks,'limits':'Real four Docker services, HTTPS/TLS/MySQL/dynsec; two SOFTWARE MQTT nodes, no ESP32/relay/water. Isolated wms-verify volumes.'}
    (ROOT/'tests/results/docker-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
finally:
    for node in nodes:node.stop()
