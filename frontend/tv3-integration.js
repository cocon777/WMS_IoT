'use strict';
// Visual source: TV3 WMS 2.0. Data/controls use the integrated TV2 APIs and TV1 profile.
const escapeTV3 = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let tv3Sites = [], dashboardHours = 1, dashboardRequest = 0, dashboardSignature = '';
const navPaths = {
  dashboard:'M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10', equipment:'M7 3h10v18H7zM3 8h4m10 0h4M3 16h4m10 0h4',
  history:'M3 12a9 9 0 1 0 3-7M3 3v5h5m4-2v6l4 2', configuration:'M4 7h16M4 17h16M8 4v6m8 4v6',
  warnings:'M12 3L2 21h20L12 3zm0 6v5m0 3v1',people:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m14-18a4 4 0 0 1 0 8M9 3a4 4 0 1 0 0 8',
  locations:'M12 22s8-8 8-14a8 8 0 1 0-16 0c0 6 8 14 8 14zm0-17v6',audit:'M5 3h14v18H5zM8 8h8m-8 4h8m-8 4h5',account:'M20 21a8 8 0 0 0-16 0M12 3a4 4 0 1 0 0 8a4 4 0 1 0 0-8'
};
const originalSetupManagement = setupManagement;
setupManagement = function () {
  originalSetupManagement();
  for (const b of $('navigation').children) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('aria-hidden','true');
    const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',navPaths[b.dataset.view]);path.setAttribute('stroke-linecap','round');path.setAttribute('stroke-linejoin','round');svg.append(path);b.prepend(svg);
    b.addEventListener('click',()=>window.history.replaceState(null,'','#/'+b.dataset.view));
  }
  refreshDashboardHistory().catch(report);
};
async function loadTV3Sites() {
  tv3Sites = await api('/api/sites');
  const select = $('site-select'); select.replaceChildren();
  const all = document.createElement('option'); all.value='';all.textContent='Tất cả khu vực';select.append(all);
  for(const site of tv3Sites){const option=document.createElement('option');option.value=site.id;option.textContent=site.name;select.append(option);}
  select.value=selectedSite;
}
$('site-select').onchange = () => {selectedSite=$('site-select').value;render();refreshDashboardHistory().catch(report);};
function pairTV3() {
  const scoped=devices.filter(d=>!selectedSite||String(d.site_id)===selectedSite);
  const tank=scoped.find(d=>d.type==='tank');
  // Never pair a pipe from a different site as a fallback.
  return {tank,pipe:scoped.find(d=>d.type==='pipe'&&tank?.site_id!=null&&d.site_id===tank.site_id)};
}
function renderTV3Dashboard() {
  const {tank,pipe}=pairTV3(),t=tank&&latest.get(tank.id),p=pipe&&latest.get(pipe.id),cfg=tank&&configs.get(tank.id)?.config;
  const set=(id,text)=>{if($(id))$(id).textContent=text;},num=(value,digits=1)=>Number.isFinite(value)?value.toFixed(digits):'--';
  const fresh=s=>s&&Number.isFinite(sampleTime(s.ts))&&Date.now()-sampleTime(s.ts)<=5000;
  set('dash-site-title',tv3Sites.find(s=>String(s.id)===(selectedSite||String(tank?.site_id)))?.name||'Trung Tâm Cấp Nước');
  set('dash-site-desc',`${tank?.device_code||'Chưa có node bồn'} / ${pipe?.device_code||'Chưa ghép node ống cùng khu vực'}`);
  set('kpi-level-val',num(t?.level_pct));set('kpi-distance-val',num(t?.distance_cm)+' cm');
  set('kpi-level-badge',!t?'CHỜ DỮ LIỆU':!fresh(t)?'DỮ LIỆU CŨ':t.level_pct>= (cfg?.high_pct??100)?'ĐẦY':t.level_pct<(cfg?.low_pct??30)?'MỨC THẤP':'BÌNH THƯỜNG');
  set('kpi-flow-val',num(p?.flow_lpm,3));set('kpi-total-flow-val',num(p?.flow_total_l,3)+' L');set('kpi-flow-badge','YF-S401');
  set('kpi-pump-badge',p==null?'CHỜ DỮ LIỆU':!fresh(p)?'DỮ LIỆU CŨ':p.pump_on?'ON':'OFF');set('kpi-pump-text',!p?'Chưa có dữ liệu':!fresh(p)?'Trạng thái cũ':p.pump_on?'Đang Bật':'Đang Tắt');
  set('kpi-pump-mode',cfg?cfg.auto_mode?'Tự Động (AUTO)':'Thủ Công (TAY)':'Chờ cấu hình');
  set('kpi-rssi-val',num(p?.rssi??t?.rssi,0));set('kpi-fault-badge',!t&&!p?'CHỜ DỮ LIỆU':fresh(t)&&fresh(p)?'ĐÃ CẬP NHẬT':'CẦN KIỂM TRA');
  set('kpi-fault-val',tank?.state==='Fault'||pipe?.state==='Fault'?'Có node Fault':!t||!p?'Chưa xác nhận':'Chưa báo lỗi');
  set('quick-pump-box',fresh(t)&&fresh(p)?'Dữ liệu mới · Điều khiển bên dưới':'Chờ node / dữ liệu mới để vận hành');
  const signature=JSON.stringify([tank,pipe,t,p,cfg]);
  if(signature!==dashboardSignature){dashboardSignature=signature;
    const safe=d=>d?{...d,device_code:escapeTV3(d.device_code)}:null;
    $('digital-twin-container').innerHTML=renderDigitalTwinSvg({tankDev:safe(tank),pipeDev:safe(pipe),tankTelemetry:t||{},pipeTelemetry:p||{},config:cfg||{low_pct:30,high_pct:100,tank_height_cm:10}});
    if(!fresh(t)||!fresh(p)){
      $('digital-twin-container').querySelectorAll('.pipe-flowing,.pump-spinning,.wave-animation').forEach(n=>n.style.animationPlayState='paused');
    }
  }
}
async function refreshDashboardHistory() {
  if(!token)return;const request=++dashboardRequest,{tank,pipe}=pairTV3(),root=$('dashboard-history');
  root.parentElement.style.height='auto';root.style.display='grid';root.style.gridTemplateColumns='repeat(auto-fit,minmax(min(100%,280px),1fr))';root.style.gap='16px';
  const end=new Date(),start=new Date(end-dashboardHours*3600000),query=new URLSearchParams({from:start.toISOString(),to:end.toISOString(),interval:dashboardHours===1?'1m':dashboardHours===24?'5m':'1h'});
  const series=await Promise.all([tank,pipe].map(d=>d?api(`/api/devices/${d.id}/telemetry?${query}`):null));if(request!==dashboardRequest||!token)return;root.replaceChildren();
  series.forEach((s,index)=>{const panel=document.createElement('div'),h=document.createElement('p');h.className='text-xs text-slate-400 font-bold';h.textContent=index===0?'Mực nước (%)':'Lưu lượng (L/phút)';panel.append(h);
    if(s?.points.length)drawChart(panel,s,index===0?'level_pct':'flow_lpm');else{const empty=document.createElement('p');empty.className='empty';empty.textContent='Chưa có dữ liệu trong khoảng này.';panel.append(empty);}root.append(panel);
  });
}
for(const [range,hours]of[['1h',1],['24h',24],['7d',168]])$('btn-range-'+range).onclick=()=>{dashboardHours=hours;for(const key of['1h','24h','7d'])$('btn-range-'+key).classList.toggle('bg-white',key===range);refreshDashboardHistory().catch(report);};
setInterval(()=>{if(token&&!$('dashboard').hidden)refreshDashboardHistory().catch(report);},30000);
document.addEventListener('click',event=>{const link=event.target.closest('a[href^="#"]');if(!link||!token)return;const route=link.getAttribute('href').replace(/^#\/?/,'');const map={devices:'equipment',dashboard:'dashboard'};const b=$('navigation').querySelector(`[data-view="${map[route]||route}"]`);if(b){event.preventDefault();b.click();}});
