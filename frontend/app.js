'use strict';
let token = '', user = null, socket = null, reconnectTimer = null, devices = [], active = true;
let selectedSite = '';
const latest = new Map();
const configs = new Map();
const modeBusy = new Set();
const $ = id => document.getElementById(id);
async function api(path, options = {}) {
  const requestToken = token;
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) } });
  if (!response.ok) {
    if (response.status === 401 && token === requestToken) endSession();
    const body = await response.json().catch(() => ({}));
    const detail = body.detail || body.message || body.error;
    throw new Error(`${response.status}: ${Array.isArray(detail) ? detail.map(x => `${x.loc?.join('.')}: ${x.msg}`).join('; ') : typeof detail === 'string' ? detail : 'Yêu cầu không thành công'}`);
  }
  return response.status === 204 ? null : response.json();
}
function report(error) { $('error').textContent = String(error.message || error); }
function sampleTime(ts) { return Date.parse(/[zZ]$|[+-]\d{2}:\d{2}$/.test(ts) ? ts : ts + 'Z'); }
function rememberLatest(id,sample) {
  const previous=latest.get(id);
  if(!previous || sampleTime(sample.ts)>=sampleTime(previous.ts)) latest.set(id,sample);
}
function endSession() {
  selectedSite = '';
  active = false; token = ''; user = null; clearTimeout(reconnectTimer);
  if (socket) socket.close(); socket = null; latest.clear(); configs.clear(); modeBusy.clear(); devices = [];
  $('command').textContent = 'Chưa gửi lệnh'; $('alerts').replaceChildren(); $('devices').replaceChildren();
  $('workspace').hidden = true; $('login').hidden = false; $('password').value = '';
  $('login-screen').hidden = false;
  if (typeof resetManagement === 'function') resetManagement();
}
function render() {
  $('devices').replaceChildren();
  for (const device of devices) {
    if (selectedSite && String(device.site_id) !== selectedSite) continue;
    const card = document.createElement('article'), heading = document.createElement('h2');
    heading.textContent = `${device.name || device.device_code} · ${device.type}`; card.append(heading);
    const state = document.createElement('p');
    state.textContent = `${device.device_code} · ${device.state} · ${device.online ? 'online' : 'offline'}`;
    card.append(state);
    const sample = latest.get(device.id), info = document.createElement('pre');
    const age = sample ? Math.max(0, (Date.now() - sampleTime(sample.ts)) / 1000) : null;
    info.className = age === null || age > 5 ? 'stale' : 'live';
    info.textContent = sample ? (device.type === 'tank'
      ? `Mực nước: ${sample.level_pct?.toFixed(1)} %\nKhoảng cách: ${sample.distance_cm?.toFixed(1)} cm`
      : `Lưu lượng: ${sample.flow_lpm?.toFixed(3)} L/phút\nTổng từ lúc khởi động: ${sample.flow_total_l?.toFixed(3)} L\nRelay bơm: ${sample.pump_on ? 'BẬT' : 'TẮT'}`)
      + `\nTuổi mẫu: ${age.toFixed(0)} giây${age > 5 ? ' · Dữ liệu cũ' : ''}` : 'Chưa có dữ liệu';
    card.append(info);
    const cfg = configs.get(device.id)?.config;
    if (device.type === 'tank' && user?.role !== 'Viewer') {
      const mode = document.createElement('p');
      mode.textContent = cfg ? `Chế độ: ${cfg.auto_mode ? 'AUTO' : 'TAY'} · Thấp dưới ${cfg.low_pct}% · Đầy từ ${cfg.high_pct}%` : 'Đang đọc chế độ';
      card.append(mode);
      const button = document.createElement('button');
      button.textContent = cfg?.auto_mode ? 'Chuyển sang TAY và dừng' : 'Bật AUTO';
      button.disabled = !cfg || modeBusy.has(device.id) || !device.online || device.state !== 'Active';
      button.onclick = () => setAuto(device, !cfg.auto_mode).catch(report); card.append(button);
    }
    if (device.type === 'pipe' && user?.role !== 'Viewer') {
      const controls = document.createElement('div'); controls.className = 'controls';
      const tank = devices.find(d => d.type === 'tank' && d.site_id != null && d.site_id === device.site_id);
      const tankSample = tank && latest.get(tank.id), tankCfg = tank && configs.get(tank.id)?.config;
      const tankAge = tankSample ? (Date.now() - sampleTime(tankSample.ts)) / 1000 : Infinity;
      const levelReady = tank?.online && tank.state === 'Active' && tankCfg && tankAge >= -2 && tankAge <= 5 && tankSample.level_pct < tankCfg.high_pct;
      for (const [value, text, duration] of [['on', 'Bơm tới đầy', cfg ? Math.min(60, cfg.pump_max_run_s) : 0], ['on', 'Bật 3 giây', 3], ['off', 'Tắt bơm', null]]) {
        const button = document.createElement('button'); button.textContent = text;
        button.disabled = !device.online || !(value === 'off' ? ['Active', 'Fault'] : ['Active']).includes(device.state) || (value === 'on' && (!levelReady || !duration || sample?.pump_on));
        button.onclick = () => sendPump(device.id, value, duration).catch(report); controls.append(button);
      }
      card.append(controls);
      const hint = document.createElement('p');
      hint.textContent = cfg ? `Bơm tới đầy: dừng theo mức nước, tối đa ${Math.min(60, cfg.pump_max_run_s)} giây. ${levelReady ? '' : 'Cần bồn chưa đầy và dữ liệu mới để bật.'}` : 'Cần đọc cấu hình trước khi bật bơm.';
      card.append(hint);
    }
    $('devices').append(card);
  }
  if (typeof renderTV3Dashboard === 'function') renderTV3Dashboard();
}
async function sendPump(id, value, duration = 3) {
  $('command').textContent = 'Đang gửi';
  try {
    const command = await api(`/api/devices/${id}/commands`, { method: 'POST',
      body: JSON.stringify({ action: 'pump', value, ...(value === 'on' ? { duration_s: duration } : {}) }) });
    $('command').textContent = `${command.cmd_id}: ${command.status} · Chờ ACK`;
    // Recover a result even if its WebSocket event arrives before POST completes or is missed.
    for (let n = 0; n < 8 && token; n++) {
      const history = await api(`/api/devices/${id}/commands`);
      const result = history.find(item => item.cmd_id === command.cmd_id);
      if (result && result.status !== 'sent') { $('command').textContent = `${result.cmd_id}: ${result.status} ${result.reason || ''}`; return; }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    $('command').textContent = `${command.cmd_id}: chưa lấy được kết quả, xem lịch sử lệnh`;
  } catch (error) { $('command').textContent = 'Gửi lệnh thất bại'; throw error; }
}
async function setAuto(device, enabled) {
  const requestToken = token;
  modeBusy.add(device.id); render();
  try {
    const current = configs.get(device.id);
    const updated = await api(`/api/devices/${device.id}/config`, { method: 'PUT',
      body: JSON.stringify({ version: current.version, auto_mode: enabled }) });
    if (token !== requestToken) return;
    configs.set(device.id, updated);
    if (!enabled) {
      const pipe = devices.find(d => d.type === 'pipe' && d.site_id != null && d.site_id === device.site_id);
      if (pipe) await sendPump(pipe.id, 'off');
    }
    if (updated.delivery === 'failed') report(new Error('Đã lưu chế độ ở server; gửi cấu hình xuống node thất bại, cần đồng bộ lại.'));
  } finally { modeBusy.delete(device.id); if (token === requestToken) await refresh(); }
}
async function refresh() {
  devices = await api('/api/devices');
  if (typeof loadTV3Sites === 'function') await loadTV3Sites();
  await Promise.all(devices.map(async device => { const sample = await api(`/api/devices/${device.id}/telemetry/latest`);
    if (sample) rememberLatest(device.id, sample); else latest.delete(device.id); }));
  if (user?.role !== 'Viewer') await Promise.all(devices.map(async device => {
    configs.set(device.id, await api(`/api/devices/${device.id}/config`));
  }));
  render();
  const alerts = await api('/api/alerts?state=open'); $('alerts').replaceChildren();
  for (const alert of alerts.items) { const p = document.createElement('p');
    p.textContent = `${alert.type} · thiết bị ${alert.device_id} · ${alert.severity} · ${alert.state}`; $('alerts').append(p); }
}
function connect(attempt = 0) {
  if (!token || !active) return;
  const current = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`); socket = current;
  current.onopen = () => current.send(JSON.stringify({ type: 'auth', token }));
  current.onmessage = event => {
    const message = JSON.parse(event.data), data = message.data;
    if (message.event === 'ready') { $('connection').textContent = 'Realtime đã kết nối'; refresh().catch(report); }
    else if (message.event === 'telemetry') { rememberLatest(data.device_id, data); render(); }
    else if (message.event === 'device_state') { const device = devices.find(d => d.id === data.device_id); if (device) Object.assign(device, data); render(); }
    else if (message.event === 'command_result') $('command').textContent = `${data.cmd_id}: ${data.status} ${data.reason || ''}`;
    else if (['alert', 'config', 'config_applied'].includes(message.event)) refresh().catch(report);
  };
  current.onclose = event => {
    if (current !== socket || !active || !token) return;
    $('connection').textContent = 'Realtime mất kết nối';
    if (event.code === 4401) { endSession(); report(new Error('Phiên hết hạn. Đăng nhập lại.')); return; }
    reconnectTimer = setTimeout(() => connect(attempt + 1), Math.min(30000, 1000 * 2 ** Math.min(attempt, 5)) + Math.random() * 300);
  };
}
$('login').onsubmit = async event => {
  event.preventDefault(); $('error').textContent = '';
  try { const session = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: $('email').value, password: $('password').value }) });
    token = session.access_token; user = session.user; active = true; $('password').value = '';
    $('command-panel').hidden = user.role === 'Viewer';
    $('identity').textContent = `${user.email} · ${user.role}`; $('login').hidden = true; $('workspace').hidden = false;
    $('login-screen').hidden = true;
    await refresh(); if (typeof setupManagement === 'function') setupManagement(); connect();
  } catch (error) { report(error); }
};
$('logout').onclick = async () => { try { await api('/api/auth/logout', { method: 'POST' }); } catch (error) { report(error); } finally { endSession(); } };
$('refresh').onclick = () => refresh().catch(report);
setInterval(() => { if (user) render(); }, 1000);
