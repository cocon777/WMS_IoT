'use strict';
// All data comes from authenticated APIs. DOM textContent keeps device/user text inert.
let viewGeneration = 0;
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
function button(text, action) { const b = el('button', text); b.type = 'button'; b.onclick = async () => { b.disabled = true; $('error').textContent = ''; try { await action(); } catch (e) { report(e); } finally { b.disabled = false; } }; return b; }
function field(form, label, key, value = '', choices = null, type = 'text') {
  const l = el('label', label), input = el(choices ? 'select' : 'input'); input.name = key;
  if (choices) for (const [v, title] of choices) { const o = el('option', title); o.value = v; input.append(o); }
  else { input.type = type; if (type === 'number') input.step = 'any'; }
  input.value = value ?? ''; l.append(input); form.append(l); return input;
}
function table(parent, headings, rows) {
  const wrap = el('div', null, 'table-wrap'), t = el('table'), head = el('tr');
  for (const h of headings) head.append(el('th', h)); const thead = el('thead'); thead.append(head); t.append(thead);
  const body = el('tbody'); for (const row of rows) { const tr = el('tr'); for (const v of row) { const td = el('td'); td.append(v instanceof Node ? v : document.createTextNode(v == null ? '—' : String(v))); tr.append(td); } body.append(tr); }
  t.append(body); wrap.append(t); parent.append(wrap); if (!rows.length) parent.append(el('p', 'Chưa có dữ liệu.', 'empty'));
}
function actions(...items) { const a = el('div', null, 'actions'); a.append(...items); return a; }
function dialog(title, build) {
  $('editor-content').replaceChildren(el('h2', title)); const f = el('form'); $('editor-content').append(f); build(f); $('editor').showModal();
}
function submit(form, title, fn) { const b = el('button', title); b.type = 'submit'; form.append(b); form.onsubmit = async e => { e.preventDefault(); b.disabled = true; try { await fn(Object.fromEntries(new FormData(form))); $('editor').close(); } catch (err) { let msg = form.querySelector('[role=alert]'); if (!msg) { msg = el('p'); msg.setAttribute('role', 'alert'); form.append(msg); } msg.textContent = err.message; } finally { b.disabled = false; } }; }
$('editor-close').onclick = () => $('editor').close();
$('editor').onclose = () => $('editor-content').replaceChildren();
function resetManagement() { ++viewGeneration; $('management').replaceChildren(); $('navigation').replaceChildren(); if ($('editor').open) $('editor').close(); }
const views = [['dashboard','Tổng quan',null],['equipment','Thiết bị',equipment],['history','Lịch sử',telemetryHistoryView],['configuration','Cấu hình',configuration],['warnings','Cảnh báo',warnings],['people','Người dùng',people],['locations','Khu vực',locations],['audit','Nhật ký',audit],['account','Tài khoản',account]];
function setupManagement() {
  $('navigation').replaceChildren();
  for (const [key, title, load] of views) {
    if (['people','locations','audit'].includes(key) && user.role !== 'Admin') continue;
    if (key === 'configuration' && user.role === 'Viewer') continue;
    const b = button(title, async () => {
      const generation = ++viewGeneration; $('dashboard').hidden = key !== 'dashboard'; $('management').hidden = key === 'dashboard';
      for (const item of $('navigation').children) item.removeAttribute('aria-current'); b.setAttribute('aria-current','page');
      $('page-title').textContent = key === 'dashboard' ? 'Vận Hành Trung Tâm' : title;
      $('breadcrumb').textContent = title;
      $('management').replaceChildren();
      if (load) { const root = el('div', null, 'panel'); root.append(el('h2', title)); $('management').append(root); await load(root, () => generation === viewGeneration && !!token); }
    }); b.dataset.view = key; $('navigation').append(b);
  }
  $('navigation').firstChild.click();
}
function devicePicker(parent) { return field(parent,'Thiết bị','device',devices[0]?.id,devices.map(d=>[d.id,`${d.name || d.device_code} (${d.type})`])); }
function timeText(ts) { return ts ? new Date(sampleTime(ts)).toLocaleString('vi-VN') : '—'; }
async function equipment(root, valid) {
  const list = await api('/api/devices?limit=500'); if (!valid()) return;
  const reload = () => equipmentReload(); const equipmentReload = async () => { await refresh(); if (valid()) { root.replaceChildren(el('h2','Thiết bị')); await equipment(root,valid); } };
  if (user.role === 'Admin') root.append(button('Đăng ký thiết bị', async () => {
    const sites = await api('/api/sites');
    dialog('Đăng ký thiết bị', f => {
      field(f,'Mã thiết bị (chữ thường, số, dấu -)','device_code').required = true;
      field(f,'Tên','name'); field(f,'Loại node','type','tank',[['tank','Bồn / tank'],['pipe','Ống / pipe']]);
      field(f,'Khu vực','site_id','',[['','Chưa ghép'],...sites.map(s=>[s.id,s.name])]);
      submit(f,'Đăng ký',async data=>{ data.site_id = data.site_id ? Number(data.site_id) : null; await api('/api/devices',{method:'POST',body:JSON.stringify(data)}); await reload(); });
    });
  }));
  table(root,['Mã / tên','Loại','Khu vực','Trạng thái','Kết nối','Firmware','Thao tác'],list.map(d=>{
    const a = actions();
    if (user.role === 'Admin' && d.state === 'Registered') a.append(button('Cấp MQTT',async()=>{
      const p = await api(`/api/devices/${d.id}/provision`,{method:'POST'}); await reload();
      dialog('Thông tin MQTT chỉ hiện một lần', f=>{ f.append(el('p','Lưu vào secrets.h của đúng node trước khi đóng. Không gửi mật khẩu lên Git.')); f.append(el('p',`Username: ${p.mqtt_username}`,'secret'),el('p',`Password: ${p.mqtt_password}`,'secret')); });
    }));
    if (user.role !== 'Viewer' && d.state !== 'Decommissioned') a.append(button('Trạng thái',()=>dialog('Chuyển trạng thái',f=>{
      const opts = user.role === 'Admin' ? [['Active','Active'],['Maintenance','Maintenance'],['Decommissioned','Thu hồi vĩnh viễn']] : [['Maintenance','Maintenance']];
      field(f,'Trạng thái mới','state','Maintenance',opts); field(f,`Nếu thu hồi, nhập chính xác mã ${d.device_code}`,'confirmation');
      f.append(el('p','Dừng bơm và chuyển TAY trước khi bảo trì hoặc đổi cặp node.'));
      submit(f,'Áp dụng',async data=>{ if(data.state==='Decommissioned' && data.confirmation!==d.device_code) throw new Error('Mã xác nhận không khớp.'); await api(`/api/devices/${d.id}/state`,{method:'PATCH',body:JSON.stringify({state:data.state,confirm:data.state==='Decommissioned'})}); await reload(); });
    })));
    if (user.role === 'Admin' && d.state !== 'Decommissioned') a.append(button('Ghép khu vực',async()=>{ const sites=await api('/api/sites'); dialog('Ghép node cùng khu vực',f=>{
      field(f,'Khu vực','site_id',d.site_id,[['','Bỏ ghép'],...sites.map(s=>[s.id,s.name])]);
      f.append(el('p','Mỗi khu vực tối đa một tank và một pipe. Dừng bơm trước khi đổi.'));
      submit(f,'Lưu khu vực',async data=>{await api(`/api/devices/${d.id}/site`,{method:'PUT',body:JSON.stringify({site_id:data.site_id?Number(data.site_id):null})});await reload();});
    }); }));
    return [`${d.device_code}\n${d.name}`,d.type,d.site_id,d.state,d.online?'Online':'Offline',d.fw_version,a];
  }));
}
async function telemetryHistoryView(root, valid) {
  const filters=el('div',null,'filters'), pick=devicePicker(filters), range=field(filters,'Khoảng thời gian','hours','1',[['1','1 giờ'],['24','24 giờ'],['168','7 ngày']]); root.append(filters);
  const result=el('div'); root.append(result);
  let query='';
  async function load() { if (!pick.value) return; const end=new Date(),start=new Date(end-Number(range.value)*3600000); query=new URLSearchParams({from:start.toISOString(),to:end.toISOString(),interval:range.value==='1'?'1m':range.value==='24'?'5m':'1h'}).toString();
    const id=pick.value, series=await api(`/api/devices/${id}/telemetry?${query}`); if(!valid() || id!==pick.value)return; result.replaceChildren();
    const key=series.device_type==='tank'?'level_pct':'flow_lpm', unit=key==='level_pct'?'Mực nước (%)':'Lưu lượng (L/phút)'; result.append(el('h3',unit)); drawChart(result,series,key);
    result.append(el('p',`${series.points.length} điểm · gộp ${series.interval} · giờ hiển thị theo máy của bạn. Khoảng thiếu dữ liệu không được thay bằng 0.`, 'hint'));
    table(result,['Thời điểm',unit,'Tổng lưu lượng (L)','Bơm có bật trong khoảng','Số mẫu'],series.points.slice(-100).map(p=>[timeText(p.ts),p[key]?.toFixed(3),p.flow_total_l?.toFixed(3),p.pump_on==null?'—':p.pump_on?'Có':'Không',p.n]));
    result.append(el('p','Bảng hiển thị tối đa 100 điểm cuối; biểu đồ dùng toàn bộ điểm trả về. Tổng lưu lượng tính lại từ 0 khi node khởi động.','hint'));
    if(user.role==='Viewer')return;
    const cmds=await api(`/api/devices/${id}/commands?limit=100`); if(!valid() || id!==pick.value)return;
    result.append(el('h3','100 lệnh gần nhất')); table(result,['Lệnh','Giá trị','Trạng thái','Lý do / nguồn','Thời điểm'],cmds.map(c=>[c.cmd_id,c.value,c.status,`${c.reason||''} ${c.source||''}`,timeText(c.sent_at)]));
  }
  filters.append(button('Tải lịch sử',load));
  if(user.role!=='Viewer') filters.append(button('Xuất CSV',async()=>{
    if(!pick.value || !query)return; const response=await fetch(`/api/devices/${pick.value}/telemetry/export?${query}`,{headers:{Authorization:`Bearer ${token}`}});
    if(!response.ok)throw new Error(`Xuất CSV thất bại: ${response.status}`); const url=URL.createObjectURL(await response.blob()),a=el('a');a.href=url;a.download=`wms-${pick.value}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  })); await load();
}
function drawChart(parent,series,key) {
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 900 260');svg.classList.add('chart');svg.setAttribute('role','img');svg.setAttribute('aria-label',key==='level_pct'?'Biểu đồ mực nước':'Biểu đồ lưu lượng');
  const points=series.points.filter(p=>p[key]!=null),max=key==='level_pct'?100:Math.max(.1,...points.map(p=>p[key]))*1.1,start=sampleTime(series.start),span=sampleTime(series.end)-start;
  const make=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;svg.append(n);return n;};
  for(let i=0;i<5;i++){const y=220-i*50;make('line',{x1:55,x2:880,y1:y,y2:y,stroke:'#d9e5df'});make('text',{x:5,y:y+4},(max*i/4).toFixed(1));}
  const gap=({raw:5,'1m':60,'5m':300,'15m':900,'1h':3600}[series.interval]||60)*1500;
  let path='',previous=null;for(const p of series.points){if(p[key]==null){previous=null;continue;}const t=sampleTime(p.ts),x=55+(t-start)/span*825,y=220-p[key]/max*200;path+=`${previous===null||t-previous>gap?'M':'L'}${x.toFixed(1)},${y.toFixed(1)} `;previous=t;make('circle',{cx:x,cy:y,r:2,fill:'#147a65'});}make('path',{d:path,stroke:'#147a65','stroke-width':2,fill:'none'});make('text',{x:55,y:248},timeText(series.start));make('text',{x:880,y:248,'text-anchor':'end'},timeText(series.end));parent.append(svg);
}
async function configuration(root,valid) {
  const pick=devicePicker(root), body=el('div');root.append(button('Đọc cấu hình',load),body);await load();
  async function load(){if(!pick.value)return;const id=pick.value,cfg=await api(`/api/devices/${id}/config`);if(!valid()||id!==pick.value)return;body.replaceChildren(el('p',`Server v${cfg.version} · Node v${cfg.applied_version??'chưa báo'} · ${cfg.sync_status}`));
    const f=el('form'),inputs={};body.append(f);for(const[k,v]of Object.entries(cfg.config)){if(k==='auto_mode')continue;const lim=cfg.limits[k];inputs[k]=field(f,k,k,v,null,'number');if(lim?.min!=null)inputs[k].min=lim.min;if(lim?.max!=null)inputs[k].max=lim.max;if(lim?.type==='int')inputs[k].step='1';}
    f.append(el('p','AUTO/TAY đổi tại Tổng quan để chuyển TAY luôn đi kèm lệnh dừng. tank_height_cm là mức nước đầy H = 8 cm; mốc rỗng D0 = 16,5 cm nằm trong firmware.','hint'));
    const save=el('button','Lưu và gửi cấu hình');f.append(save);f.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{const data={version:cfg.version};for(const[k,input]of Object.entries(inputs))data[k]=Number(input.value);const updated=await api(`/api/devices/${id}/config`,{method:'PUT',body:JSON.stringify(data)});await refresh();await load();if(updated.delivery==='failed')throw new Error('Đã lưu; chưa gửi được xuống node. Dùng Gửi lại.');}catch(err){report(err);}finally{save.disabled=false;}};
    body.append(button('Gửi lại cấu hình',async()=>{const r=await api(`/api/devices/${id}/config/publish`,{method:'POST'});await load();if(r.delivery==='failed')throw new Error('Broker chưa nhận cấu hình.');}));
    const rules=await api(`/api/devices/${id}/alert-rules`);if(!valid()||id!==pick.value)return;body.append(el('h3','Quy tắc cảnh báo'));
    const list=Array.isArray(rules)?rules:rules.rules;table(body,['Loại','Bật','Mức','Tham số',''],list.map(r=>[r.type,r.enabled?'Có':'Không',r.severity,JSON.stringify(r.params),button('Sửa quy tắc',()=>dialog(r.type,f=>{
      field(f,'Bật quy tắc','enabled',String(r.enabled),[['true','Bật'],['false','Tắt']]);field(f,'Mức độ','severity',r.severity,[['warning','warning'],['critical','critical']]);const l=el('label','Tham số JSON'),area=el('textarea');area.name='params';area.rows=8;area.value=JSON.stringify(r.params,null,2);l.append(area);f.append(l);
      submit(f,'Lưu quy tắc',async data=>{await api(`/api/devices/${id}/alert-rules`,{method:'PUT',body:JSON.stringify({rules:[{type:r.type,enabled:data.enabled==='true',severity:data.severity,params:JSON.parse(data.params)}]})});await load();});
    }))]));
  }
}
async function warnings(root,valid){
  const filters=el('div',null,'filters'),state=field(filters,'Trạng thái','state','open',[['open','Đang mở'],['ack','Đã xác nhận'],['closed','Đã đóng'],['','Tất cả']]),pick=field(filters,'Thiết bị','device','',[['','Tất cả'],...devices.map(d=>[d.id,d.device_code])]);root.append(filters);const result=el('div');root.append(result);let offset=0;
  async function load(){const q=new URLSearchParams({limit:50,offset});if(state.value)q.set('state',state.value);if(pick.value)q.set('device_id',pick.value);const data=await api(`/api/alerts?${q}`);if(!valid())return;result.replaceChildren(el('p',`${data.total} cảnh báo · từ ${offset+1}`));table(result,['ID','Loại','Node','Mức','Trạng thái','Thời điểm',''],data.items.map(a=>{const act=actions();if(user.role!=='Viewer'&&a.state!=='closed'){if(a.state==='open')act.append(button('Xác nhận',async()=>{await api(`/api/alerts/${a.id}/ack`,{method:'POST'});await load();await refresh();}));act.append(button('Đóng cảnh báo',async()=>{await api(`/api/alerts/${a.id}/close`,{method:'POST'});await load();await refresh();}));}return[a.id,a.type,a.device_id,a.severity,a.state,timeText(a.opened_at),act];}));const prev=button('Trước',async()=>{offset=Math.max(0,offset-50);await load();}),next=button('Sau',async()=>{offset+=50;await load();});prev.disabled=offset===0;next.disabled=offset+50>=data.total;result.append(actions(prev,next));}
  filters.append(button('Lọc cảnh báo',async()=>{offset=0;await load();}));await load();
}
async function people(root,valid){const list=await api('/api/users');if(!valid())return;const reload=async()=>{if(valid()){root.replaceChildren(el('h2','Người dùng'));await people(root,valid);}};
  root.append(button('Tạo người dùng',()=>dialog('Tạo người dùng',f=>{field(f,'Email','email','',null,'email').required=true;field(f,'Họ tên','full_name');field(f,'Mật khẩu ban đầu','password','',null,'password').required=true;field(f,'Vai trò','role','Viewer',[['Viewer','Viewer'],['Operator','Operator'],['Admin','Admin']]);submit(f,'Tạo tài khoản',async data=>{await api('/api/users',{method:'POST',body:JSON.stringify(data)});await reload();});})));
  table(root,['Email','Họ tên','Vai trò','Trạng thái',''],list.map(u=>[u.email,u.full_name,u.role,u.status,actions(button('Sửa tài khoản',()=>dialog('Sửa tài khoản',f=>{field(f,'Họ tên','full_name',u.full_name);field(f,'Vai trò','role',u.role,[['Viewer','Viewer'],['Operator','Operator'],['Admin','Admin']]);field(f,'Trạng thái','status',u.status,[['active','Hoạt động'],['disabled','Vô hiệu hóa']]);field(f,'Mở khóa đăng nhập','unlock','false',[['false','Giữ nguyên'],['true','Mở khóa']]);submit(f,'Lưu tài khoản',async data=>{data.unlock=data.unlock==='true';await api(`/api/users/${u.id}`,{method:'PATCH',body:JSON.stringify(data)});await reload();});})),button('Gán thiết bị',async()=>{const scope=await api(`/api/users/${u.id}/devices`);dialog(`Phạm vi của ${u.email}`,f=>{f.append(el('p','Operator/Viewer chỉ thấy node được gán. Gán cả tank và pipe để theo dõi và điều khiển đầy đủ. Admin thấy tất cả.'));for(const d of devices){const l=el('label',d.device_code),c=el('input');c.type='checkbox';c.name='scope';c.value=d.id;c.checked=scope.device_ids.includes(d.id);l.append(c);f.append(l);}submit(f,'Lưu phạm vi',async()=>{await api(`/api/users/${u.id}/devices`,{method:'PUT',body:JSON.stringify({device_ids:[...f.querySelectorAll('input:checked')].map(i=>Number(i.value))})});});});}))]));
}
async function locations(root,valid){const sites=await api('/api/sites');if(!valid())return;root.append(button('Tạo khu vực',()=>dialog('Tạo khu vực',f=>{field(f,'Tên','name').required=true;field(f,'Mô tả','description');submit(f,'Tạo khu vực',async data=>{await api('/api/sites',{method:'POST',body:JSON.stringify(data)});if(valid()){root.replaceChildren(el('h2','Khu vực'));await locations(root,valid);}});})));table(root,['ID','Tên','Mô tả','Thiết bị'],sites.map(s=>[s.id,s.name,s.description,(s.devices||[]).map(d=>d.device_code).join(', ')]));}
async function audit(root,valid){let offset=0;const filters=el('div',null,'filters'),action=field(filters,'Hành động (để trống: tất cả)','action');root.append(filters);const result=el('div');root.append(result);async function load(){const q=new URLSearchParams({limit:50,offset});if(action.value)q.set('action',action.value);const data=await api(`/api/audit-logs?${q}`);if(!valid())return;result.replaceChildren(el('p',`${data.total} bản ghi`));table(result,['Thời điểm','Người dùng','Hành động','Đối tượng','Chi tiết'],data.items.map(a=>[timeText(a.created_at),a.user_id,a.action,`${a.target_type||''} ${a.target_id||''}`,JSON.stringify(a.detail??a.details??{})]));const prev=button('Trước',async()=>{offset=Math.max(0,offset-50);await load();}),next=button('Sau',async()=>{offset+=50;await load();});prev.disabled=offset===0;next.disabled=offset+50>=data.total;result.append(actions(prev,next));}filters.append(button('Lọc nhật ký',async()=>{offset=0;await load();}));await load();}
async function account(root,valid){const me=await api('/api/me');if(!valid())return;root.append(el('p',`${me.email} · ${me.role}`),button('Đổi họ tên',()=>dialog('Hồ sơ',f=>{field(f,'Họ tên','full_name',me.full_name);submit(f,'Lưu hồ sơ',async data=>{user=await api('/api/me',{method:'PATCH',body:JSON.stringify(data)});if(valid()){root.replaceChildren(el('h2','Tài khoản'));await account(root,valid);}});})),button('Đổi mật khẩu',()=>dialog('Đổi mật khẩu',f=>{field(f,'Mật khẩu hiện tại','current_password','',null,'password').required=true;field(f,'Mật khẩu mới','new_password','',null,'password').required=true;submit(f,'Đổi mật khẩu',async data=>{const session=await api('/api/auth/change-password',{method:'POST',body:JSON.stringify(data)});token=session.access_token;user=session.user;clearTimeout(reconnectTimer);const old=socket;socket=null;if(old)old.close();connect();});})));}
