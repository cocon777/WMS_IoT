function renderDashboardTemplate() {
    return `
        <div class="space-y-6 view-enter pb-12">
            <!-- 1. Top Section: Site Picker & Quick Action Overview -->
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
                <div>
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                        <h2 class="text-lg font-bold text-slate-800" id="dash-site-title">Đang tải trạm cấp nước...</h2>
                    </div>
                    <p class="text-xs text-slate-400 mt-0.5" id="dash-site-desc">Hệ thống giám sát và điều khiển liên node tự động</p>
                </div>

                <div class="flex flex-wrap items-center gap-3">
                    <!-- Quick Pump Trigger Button for Operators/Admins -->
                    <div id="quick-pump-box" class="flex items-center gap-2"></div>
                    <!-- View details link -->
                    <a href="#/devices" class="px-3.5 py-2 text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition flex items-center gap-1.5">
                        <svg class="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path></svg>
                        <span>Quản Lý Thiết Bị</span>
                    </a>
                </div>
            </div>

            <!-- 2. Hàng 4 Thẻ KPI Chỉ Số Chính -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="kpi-cards-grid">
                <!-- Card 1: Mực nước -->
                <div class="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs hover-card">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-bold uppercase tracking-wider">
                        <span>Mực Nước Bồn</span>
                        <span id="kpi-level-badge" class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-sky-50 text-sky-700">CHỜ DỮ LIỆU</span>
                    </div>
                    <div class="mt-3 flex items-baseline gap-1.5">
                        <span id="kpi-level-val" class="text-3xl font-extrabold text-slate-800 font-mono-val">--</span>
                        <span class="text-sm font-bold text-slate-400">%</span>
                    </div>
                    <p class="text-xs text-slate-400 mt-2 flex items-center justify-between">
                        <span>Khoảng cách đo:</span>
                        <span id="kpi-distance-val" class="font-bold text-slate-700 font-mono-val">-- cm</span>
                    </p>
                </div>

                <!-- Card 2: Lưu lượng dòng chảy -->
                <div class="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs hover-card">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-bold uppercase tracking-wider">
                        <span>Lưu Lượng Cấp</span>
                        <span id="kpi-flow-badge" class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-50 text-emerald-700">YF-S401</span>
                    </div>
                    <div class="mt-3 flex items-baseline gap-1.5">
                        <span id="kpi-flow-val" class="text-3xl font-extrabold text-emerald-600 font-mono-val">--</span>
                        <span class="text-sm font-bold text-slate-400">L/phút</span>
                    </div>
                    <p class="text-xs text-slate-400 mt-2 flex items-center justify-between">
                        <span>Tổng tích lũy:</span>
                        <span id="kpi-total-flow-val" class="font-bold text-slate-700 font-mono-val">-- Lít</span>
                    </p>
                </div>

                <!-- Card 3: Máy Bơm DC -->
                <div class="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs hover-card">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-bold uppercase tracking-wider">
                        <span>Trạng Thái Bơm</span>
                        <span id="kpi-pump-badge" class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-slate-100 text-slate-600">CHỜ DỮ LIỆU</span>
                    </div>
                    <div class="mt-3 flex items-baseline gap-2">
                        <span id="kpi-pump-text" class="text-2xl font-extrabold text-slate-800">Chưa có dữ liệu</span>
                    </div>
                    <p class="text-xs text-slate-400 mt-2 flex items-center justify-between">
                        <span>Chế độ:</span>
                        <span class="font-bold text-slate-700" id="kpi-pump-mode">Chờ cấu hình</span>
                    </p>
                </div>

                <!-- Card 4: Sóng Wi-Fi & Sự cố -->
                <div class="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs hover-card">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-bold uppercase tracking-wider">
                        <span>Độ Ổn Định Sóng</span>
                        <span id="kpi-fault-badge" class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-50 text-emerald-700">CHỜ DỮ LIỆU</span>
                    </div>
                    <div class="mt-3 flex items-baseline gap-1.5">
                        <span id="kpi-rssi-val" class="text-3xl font-extrabold text-slate-800 font-mono-val">--</span>
                        <span class="text-sm font-bold text-slate-400">dBm</span>
                    </div>
                    <p class="text-xs text-slate-400 mt-2 flex items-center justify-between">
                        <span>Sự cố phần cứng:</span>
                        <span id="kpi-fault-val" class="font-bold text-slate-700">Không có</span>
                    </p>
                </div>
            </div>

            <!-- 3. SCADA Digital Twin Widget -->
            <div id="digital-twin-container">
                <div class="w-full bg-white rounded-2xl border border-slate-200/80 p-12 text-center text-slate-400">
                    Đang dựng mô hình SCADA Digital Twin...
                </div>
            </div>

            <!-- 4. Biểu đồ Giám Sát Viễn Trắc Thời Gian Thực -->
            <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4 pb-4 border-b border-slate-100">
                    <div>
                        <h3 class="font-bold text-slate-800 text-base">Đồ Thị Mực Nước (%) & Lưu Lượng (L/phút)</h3>
                        <p class="text-xs text-slate-400 mt-0.5">Dữ liệu telemetry cập nhật tự động trực tiếp từ cặp 2 node ESP32</p>
                    </div>

                    <!-- Range Selector Buttons -->
                    <div class="flex items-center bg-slate-100 p-1 rounded-xl text-xs font-bold text-slate-600">
                        <button id="btn-range-1h" class="px-3 py-1.5 rounded-lg bg-white text-sky-600 shadow-xs transition">1 Giờ</button>
                        <button id="btn-range-24h" class="px-3 py-1.5 rounded-lg hover:text-slate-900 transition">24 Giờ</button>
                        <button id="btn-range-7d" class="px-3 py-1.5 rounded-lg hover:text-slate-900 transition">7 Ngày</button>
                    </div>
                </div>

                <!-- Canvas -->
                <div class="relative h-72 sm:h-80 w-full">
                    <div id="dashboard-history" class="h-full"><p class="text-slate-400 text-sm">Chọn thiết bị và khoảng thời gian ở trang Lịch sử.</p></div>
                </div>
            </div>
        </div>
    `;
}

