/**
 * WMS 2.0 SCADA Digital Twin SVG Component
 * Interactive visual representation of 2-Node pair: Tank Node + Pipe & Pump Node
 */

function renderDigitalTwinSvg({
    tankDev = null,
    pipeDev = null,
    tankTelemetry = {},
    pipeTelemetry = {},
    config = { low_pct: 37.5, high_pct: 100, tank_height_cm: 8 }
} = {}) {
    // 1. Tank calculations
    const levelPct = typeof tankTelemetry.level_pct === 'number' ? Math.max(0, Math.min(100, tankTelemetry.level_pct)) : 0;
    const distanceCm = typeof tankTelemetry.distance_cm === 'number' ? tankTelemetry.distance_cm.toFixed(1) : '--';
    const tankOnline = Boolean(tankDev?.online);
    const lowPct = config.low_pct ?? 37.5;
    const highPct = config.high_pct ?? 100;

    // SVG coordinate mappings for Tank: height = 200 (from Y=90 to Y=290)
    const tankTopY = 90;
    const tankBottomY = 290;
    const tankHeight = 200;
    const waterHeight = (levelPct / 100) * tankHeight;
    const waterY = tankBottomY - waterHeight;

    const lowLineY = tankBottomY - (lowPct / 100) * tankHeight;
    const highLineY = tankBottomY - (highPct / 100) * tankHeight;

    // 2. Pipe & Pump calculations
    const flowLpm = typeof pipeTelemetry.flow_lpm === 'number' ? pipeTelemetry.flow_lpm.toFixed(1) : '--';
    const flowTotalL = typeof pipeTelemetry.flow_total_l === 'number' ? pipeTelemetry.flow_total_l.toFixed(1) : '--';
    const isPumpOn = Boolean(pipeTelemetry.pump_on);
    const isFlowing = parseFloat(flowLpm) > 0.05;
    const pipeOnline = Boolean(pipeDev?.online);

    // Color decisions
    let waterColorGrad = 'url(#grad-water-normal)';
    let levelBadgeBg = 'bg-sky-100 text-sky-700';
    if (levelPct < lowPct) {
        waterColorGrad = 'url(#grad-water-low)';
        levelBadgeBg = 'bg-rose-100 text-rose-700';
    } else if (levelPct >= highPct) {
        waterColorGrad = 'url(#grad-water-high)';
        levelBadgeBg = 'bg-amber-100 text-amber-700';
    }

    return `
        <div class="relative w-full bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 overflow-hidden">
            <!-- Header bar of widget -->
            <div class="flex flex-wrap items-center justify-between gap-3 mb-3 pb-3 border-b border-slate-100">
                <div class="flex items-center gap-2">
                    <span class="p-1.5 rounded-lg bg-sky-50 text-sky-600">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path></svg>
                    </span>
                    <div>
                        <h3 class="font-bold text-slate-800 text-sm">Giám Sát Trực Quan SCADA 2-Node</h3>
                        <p class="text-[11px] text-slate-400">Node Bồn (${tankDev?.device_code || 'wms-tank-01'}) ➔ Node Đường Ống & Bơm (${pipeDev?.device_code || 'wms-pipe-01'})</p>
                    </div>
                </div>

                <div class="flex items-center gap-2">
                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ${isPumpOn ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-100 text-slate-600'}">
                        <span class="w-2 h-2 rounded-full ${isPumpOn ? 'bg-emerald-500 animate-ping' : 'bg-slate-400'}"></span>
                        BƠM: ${pipeTelemetry.pump_on == null ? 'CHƯA CÓ DỮ LIỆU' : isPumpOn ? 'ĐANG BẬT (RUNNING)' : 'ĐANG TẮT (STANDBY)'}
                    </span>
                </div>
            </div>

            <!-- SVG SCADA Schematic -->
            <div class="w-full flex justify-center py-2">
                <svg viewBox="0 0 840 340" class="w-full max-w-4xl h-auto select-none font-sans" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <!-- Normal Water Gradient -->
                        <linearGradient id="grad-water-normal" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.9" />
                            <stop offset="100%" stop-color="#0284c7" stop-opacity="0.95" />
                        </linearGradient>
                        <!-- Low Water Gradient -->
                        <linearGradient id="grad-water-low" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#fb7185" stop-opacity="0.9" />
                            <stop offset="100%" stop-color="#e11d48" stop-opacity="0.95" />
                        </linearGradient>
                        <!-- High Water Gradient -->
                        <linearGradient id="grad-water-high" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#fbbf24" stop-opacity="0.9" />
                            <stop offset="100%" stop-color="#d97706" stop-opacity="0.95" />
                        </linearGradient>
                        <!-- Metallic Pipe Gradient -->
                        <linearGradient id="grad-pipe" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#e2e8f0" />
                            <stop offset="50%" stop-color="#94a3b8" />
                            <stop offset="100%" stop-color="#cbd5e1" />
                        </linearGradient>
                        <!-- Shadow Filter -->
                        <filter id="glow-water" x="-10%" y="-10%" width="120%" height="120%">
                            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#0284c7" flood-opacity="0.25" />
                        </filter>
                    </defs>

                    <!-- ================= 1. NODE BỒN NƯỚC (TANK) ================= -->
                    <g transform="translate(60, 10)">
                        <!-- Tank Background Frame -->
                        <rect x="0" y="80" width="220" height="220" rx="16" fill="#f8fafc" stroke="#cbd5e1" stroke-width="3" />
                        
                        <!-- Water Level Fill -->
                        <clipPath id="tank-clip">
                            <rect x="3" y="83" width="214" height="214" rx="14" />
                        </clipPath>
                        <g clip-path="url(#tank-clip)">
                            <!-- Animated Fluid Rect -->
                            <rect x="0" y="${waterY}" width="220" height="${waterHeight + 10}" fill="${waterColorGrad}" filter="url(#glow-water)" class="transition-all duration-700 ease-out" />
                            
                            <!-- Surface Wave Animation Line -->
                            ${levelPct > 0 ? `
                            <path d="M 0 ${waterY} Q 55 ${waterY - 4} 110 ${waterY} T 220 ${waterY} V 300 H 0 Z" fill="${waterColorGrad}" opacity="0.6" class="wave-animation" />
                            ` : ''}
                        </g>

                        <!-- Measurement Ruler Ticks on the left -->
                        <g stroke="#94a3b8" stroke-width="1.5" opacity="0.7">
                            <line x1="6" y1="90" x2="18" y2="90" /> <!-- 100% -->
                            <line x1="6" y1="140" x2="14" y2="140" /> <!-- 75% -->
                            <line x1="6" y1="190" x2="18" y2="190" /> <!-- 50% -->
                            <line x1="6" y1="240" x2="14" y2="240" /> <!-- 25% -->
                            <line x1="6" y1="290" x2="18" y2="290" /> <!-- 0% -->
                        </g>
                        <text x="24" y="94" font-size="10" font-weight="700" fill="#64748b">100%</text>
                        <text x="24" y="194" font-size="10" font-weight="700" fill="#64748b">50%</text>
                        <text x="24" y="294" font-size="10" font-weight="700" fill="#64748b">0%</text>

                        <!-- Threshold Dotted Lines -->
                        <!-- High Level line -->
                        <line x1="3" y1="${highLineY}" x2="217" y2="${highLineY}" stroke="#d97706" stroke-width="1.5" stroke-dasharray="4 3" />
                        <text x="135" y="${highLineY - 4}" font-size="9" font-weight="bold" fill="#b45309">Ngưỡng cao (${highPct}%)</text>
                        
                        <!-- Low Level line -->
                        <line x1="3" y1="${lowLineY}" x2="217" y2="${lowLineY}" stroke="#e11d48" stroke-width="1.5" stroke-dasharray="4 3" />
                        <text x="135" y="${lowLineY + 11}" font-size="9" font-weight="bold" fill="#be123c">Ngưỡng cạn (${lowPct}%)</text>

                        <!-- Center Telemetry Display inside Tank -->
                        <rect x="55" y="150" width="110" height="48" rx="10" fill="rgba(255,255,255,0.92)" stroke="#e2e8f0" stroke-width="1" />
                        <text x="110" y="174" text-anchor="middle" font-size="22" font-weight="800" fill="#0f172a" class="font-mono-val">${typeof tankTelemetry.level_pct === 'number' ? levelPct.toFixed(1) + '%' : '--'}</text>
                        <text x="110" y="190" text-anchor="middle" font-size="10" font-weight="600" fill="#64748b">${distanceCm} cm</text>

                        <!-- Sensor HC-SR04 on top of tank -->
                        <rect x="75" y="48" width="70" height="24" rx="6" fill="#1e293b" />
                        <circle cx="92" cy="60" r="7" fill="#64748b" stroke="#38bdf8" stroke-width="2" />
                        <circle cx="128" cy="60" r="7" fill="#64748b" stroke="#38bdf8" stroke-width="2" />
                        <line x1="110" y1="72" x2="110" y2="82" stroke="#38bdf8" stroke-width="2" stroke-dasharray="2 2" />
                        <text x="110" y="38" text-anchor="middle" font-size="11" font-weight="700" fill="#334155">HC-SR04 Cảm biến</text>
                    </g>

                    <!-- ================= 2. ĐƯỜNG ỐNG NỐI TỪ BỒN SANG BƠM ================= -->
                    <g transform="translate(60, 10)">
                        <!-- Main Pipe Path (From Tank bottom right x=220, y=260 to Pump Inlet x=460, y=260) -->
                        <path d="M 220 260 L 460 260" stroke="#cbd5e1" stroke-width="18" stroke-linecap="round" fill="none" />
                        <path d="M 220 260 L 460 260" stroke="#f1f5f9" stroke-width="12" fill="none" />
                        
                        <!-- Animated Water Stream inside Pipe if flowing -->
                        ${isFlowing ? `
                        <path d="M 220 260 L 460 260" stroke="#0ea5e9" stroke-width="8" stroke-linecap="round" fill="none" class="pipe-flowing" />
                        ` : ''}

                        <!-- Flow Sensor YF-S401 on Pipe -->
                        <g transform="translate(320, 240)">
                            <rect x="0" y="0" width="46" height="40" rx="8" fill="#0f172a" />
                            <circle cx="23" cy="20" r="10" fill="#1e293b" stroke="#38bdf8" stroke-width="2" />
                            <!-- Mini Flow Sensor Icon inside -->
                            <path d="M 23 15 L 23 25 M 18 20 L 28 20" stroke="#38bdf8" stroke-width="1.5" />
                            <text x="23" y="-8" text-anchor="middle" font-size="10" font-weight="700" fill="#334155">YF-S401 Lưu lượng</text>
                            <text x="23" y="52" text-anchor="middle" font-size="11" font-weight="800" fill="#0284c7" class="font-mono-val">${flowLpm} L/m</text>
                        </g>

                        <!-- ================= 3. MÁY BƠM DC & RƠ-LE (PUMP) ================= -->
                        <g transform="translate(460, 205)">
                            <!-- Pump Outer Casing -->
                            <rect x="0" y="30" width="110" height="70" rx="14" fill="#1e293b" stroke="#0f172a" stroke-width="2" />
                            <circle cx="55" cy="65" r="28" fill="#334155" stroke="${isPumpOn ? '#10b981' : '#64748b'}" stroke-width="3" />
                            
                            <!-- Rotating Impeller Blades -->
                            <g transform="translate(55, 65)" class="${isPumpOn ? 'pump-spinning' : ''}">
                                <circle cx="0" cy="0" r="6" fill="${isPumpOn ? '#10b981' : '#94a3b8'}" />
                                <path d="M 0 -20 L 0 20 M -20 0 L 20 0 M -14 -14 L 14 14 M -14 14 L 14 -14" stroke="${isPumpOn ? '#34d399' : '#cbd5e1'}" stroke-width="3" stroke-linecap="round" />
                            </g>

                            <!-- Pump Title & Specs -->
                            <text x="55" y="18" text-anchor="middle" font-size="11" font-weight="700" fill="#334155">Relay Bơm DC</text>
                            <text x="55" y="120" text-anchor="middle" font-size="11" font-weight="800" fill="${isPumpOn ? '#059669' : '#64748b'}">
                                ${pipeTelemetry.pump_on == null ? 'CHƯA CÓ DỮ LIỆU' : isPumpOn ? '● ĐANG BẬT' : '○ ĐANG TẮT'}
                            </text>
                        </g>

                        <!-- Pipe Outlet leaving Pump (Rightward) -->
                        <path d="M 570 260 L 710 260 L 710 180" stroke="#cbd5e1" stroke-width="18" stroke-linecap="round" stroke-linejoin="round" fill="none" />
                        <path d="M 570 260 L 710 260 L 710 180" stroke="#f1f5f9" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" fill="none" />
                        ${isFlowing ? `
                        <path d="M 570 260 L 710 260 L 710 180" stroke="#0ea5e9" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none" class="pipe-flowing" />
                        ` : ''}

                        <!-- Water Discharge nozzle icon -->
                        <g transform="translate(710, 180)">
                            <circle cx="0" cy="0" r="10" fill="#0284c7" />
                            <text x="0" y="-16" text-anchor="middle" font-size="10" font-weight="700" fill="#475569">Đường Cấp Vào Bồn</text>
                            <text x="0" y="32" text-anchor="middle" font-size="10" font-weight="600" fill="#0284c7" class="font-mono-val">Tổng: ${flowTotalL} L</text>
                        </g>
                    </g>
                </svg>
            </div>
        </div>
    `;
}
