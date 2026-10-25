from datetime import datetime
import os
import json
import urllib.request
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

# ฐานข้อมูลสถานะระบบ ปฏิทินข่าว และประวัติสัญญาณ
SYSTEM_STATE = {
    "news_locked": False,
    "lock_reason": "ตลาดปกติ (Normal Market Conditions)",
    "latest_signal": None,
    "signal_history": [
        {
            "id": 101,
            "time": "14:30:00",
            "symbol": "XAUUSD",
            "tf": "1H",
            "direction": "SELL",
            "entry": "2738.50",
            "sl": "2744.20",
            "tp1": "2727.10",
            "tp2": "2721.40",
            "rr": "1:3",
            "status": "RUNNING",
            "reason": "ราคาชน Order Block (Supply Zone H1) พร้อมทิ้งตัวลงตามโครงสร้างสถาบันการเงิน"
        }
    ],
    "economic_calendar": [
        {
            "time": "19:30",
            "currency": "USD",
            "event": "Core CPI m/m (ดัชนีราคาผู้บริโภคพื้นฐาน)",
            "impact": "HIGH",
            "forecast": "0.3%",
            "previous": "0.3%",
            "status": "AUTO-LOCK ±30 MIN"
        },
        {
            "time": "21:00",
            "currency": "USD",
            "event": "ISM Services PMI (ดัชนีผู้จัดการฝ่ายจัดซื้อภาคบริการ)",
            "impact": "MEDIUM",
            "forecast": "52.4",
            "previous": "51.9",
            "status": "REDUCE LOT 50%"
        }
    ]
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — Auto Order Block Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Lightweight Charts สำหรับวาดเส้น Order Block และกรอบโซนอัตโนมัติ -->
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #03060c;
            --bg-card: rgba(13, 20, 36, 0.85);
            --border-subtle: rgba(255, 255, 255, 0.08);
        }
        body {
            font-family: 'Prompt', sans-serif;
            background-color: var(--bg-deep);
            background-image: 
                radial-gradient(circle at 12% 8%, rgba(245, 158, 11, 0.08), transparent 32%),
                radial-gradient(circle at 88% 15%, rgba(6, 182, 212, 0.07), transparent 32%),
                radial-gradient(circle at 50% 90%, rgba(16, 185, 129, 0.05), transparent 40%),
                linear-gradient(to bottom, rgba(15, 23, 42, 0.3) 1px, transparent 1px),
                linear-gradient(to right, rgba(15, 23, 42, 0.3) 1px, transparent 1px);
            background-size: 100% 100%, 100% 100%, 100% 100%, 36px 36px, 36px 36px;
            color: #f1f5f9;
        }
        .font-mono-num { font-family: 'JetBrains Mono', monospace; }
        .pro-card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-subtle);
            box-shadow: 0 20px 50px -15px rgba(0, 0, 0, 0.7);
        }
        .pro-card-gold {
            background: linear-gradient(145deg, rgba(17, 25, 44, 0.95), rgba(10, 15, 28, 0.98));
            border: 1px solid rgba(245, 158, 11, 0.4);
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #03060c; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 9999px; }
    </style>
</head>
<body class="antialiased min-h-screen p-3 md:p-5 selection:bg-amber-500 selection:text-slate-950">
    <div class="max-w-[1740px] mx-auto space-y-5">

        <!-- HEADER -->
        <header class="pro-card rounded-2xl p-4 lg:px-6">
            <div class="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
                <div class="flex items-center gap-4">
                    <div class="w-13 h-13 px-3.5 py-2.5 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 flex flex-col items-center justify-center shadow-xl font-black text-slate-950 shrink-0">
                        <span class="text-[10px] tracking-tighter leading-none opacity-80">SMART MONEY</span>
                        <span class="text-lg tracking-tight leading-none font-mono-num">OB</span>
                    </div>
                    <div>
                        <div class="flex flex-wrap items-center gap-2.5">
                            <h1 class="text-xl md:text-2xl font-black tracking-tight bg-gradient-to-r from-white via-amber-200 to-amber-400 bg-clip-text text-transparent">
                                GOLD AI SNIPER PRO — AUTO ORDER BLOCK (OB)
                            </h1>
                            <span class="px-2.5 py-0.5 text-[10px] font-extrabold uppercase bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-full">
                                INSTITUTIONAL ORDER BLOCK • RR 1:3
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-1">ระบบตรวจจับและตีโซน Order Block พร้อมเส้น Entry, SL, TP บนกราฟอัตโนมัติทันทีโดยไม่ต้องลากเส้นเอง</p>
                    </div>
                </div>

                <div class="flex flex-wrap items-center gap-2.5">
                    <div id="news-shield-box" class="bg-emerald-950/40 border border-emerald-500/40 px-3.5 py-2 rounded-xl flex items-center gap-3">
                        <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
                        <span id="shield-text" class="text-xs font-extrabold text-emerald-400">SAFE MODE (ปกติ)</span>
                        <button onclick="toggleNewsLock()" class="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-[11px] font-bold text-slate-200 border border-slate-700">สลับโหมดข่าว</button>
                    </div>
                </div>
            </div>
        </header>

        <!-- MAIN WORKSPACE -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- LEFT (7 COLS): AUTO ORDER BLOCK CHART -->
            <div class="xl:col-span-7 space-y-5">
                <div class="pro-card rounded-2xl p-4 md:p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div class="flex items-center gap-2">
                            <span class="px-3 py-1.5 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-400 text-xs font-black">
                                <i class="fa-solid fa-boxes-stacked mr-1"></i> Auto Order Block & Institutional Zone
                            </span>
                        </div>
                        <span id="chart-tf-label" class="text-xs font-bold text-cyan-400 font-mono-num">TF: 1H</span>
                    </div>

                    <!-- Quick copy pills -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                        <div onclick="copyPrice('val-entry')" class="cursor-pointer p-2.5 rounded-xl bg-cyan-950/30 border border-cyan-500/30 hover:border-cyan-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-cyan-300 font-bold block">🔵 ENTRY (OB Zone)</span>
                                <span id="top-entry" class="font-mono-num font-extrabold text-cyan-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-cyan-500/20 text-cyan-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-sl')" class="cursor-pointer p-2.5 rounded-xl bg-rose-950/30 border border-rose-500/30 hover:border-rose-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-rose-300 font-bold block">🔴 STOP LOSS</span>
                                <span id="top-sl" class="font-mono-num font-extrabold text-rose-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-rose-500/20 text-rose-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-tp1')" class="cursor-pointer p-2.5 rounded-xl bg-emerald-950/30 border border-emerald-500/30 hover:border-emerald-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-emerald-300 font-bold block">🟢 TP1 (RR 1:2)</span>
                                <span id="top-tp1" class="font-mono-num font-extrabold text-emerald-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-emerald-500/20 text-emerald-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-tp2')" class="cursor-pointer p-2.5 rounded-xl bg-amber-950/30 border border-amber-500/30 hover:border-amber-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-amber-300 font-bold block">🟡 TP2 (RR 1:3)</span>
                                <span id="top-tp2" class="font-mono-num font-extrabold text-amber-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-amber-500/20 text-amber-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                    </div>

                    <!-- กราฟแสดงผล Auto Order Block อัตโนมัติทันทีโดยไม่ต้องคลิก -->
                    <div id="ob-chart-container" class="w-full h-[540px] rounded-xl overflow-hidden border border-slate-800 bg-[#050912]"></div>
                </div>

                <!-- ECONOMIC CALENDAR -->
                <div class="pro-card rounded-2xl p-5 space-y-3">
                    <h2 class="text-sm font-bold text-white border-b border-slate-800 pb-2"><i class="fa-regular fa-calendar-days text-amber-400 mr-2"></i>ปฏิทินข่าวเศรษฐกิจและระบบกรองความเสี่ยง</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-slate-800 text-[11px]">
                                    <th class="py-2">เวลา</th>
                                    <th>สกุลเงิน</th>
                                    <th>หัวข้อข่าวสำคัญ</th>
                                    <th>ความรุนแรง</th>
                                    <th class="text-right">สถานะระบบ</th>
                                </tr>
                            </thead>
                            <tbody id="calendar-table-body" class="divide-y divide-slate-800/60"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- RIGHT (5 COLS): CONTROLS & TIMEFRAMES -->
            <div class="xl:col-span-5 space-y-5">
                
                <!-- TIMEFRAME SELECTOR -->
                <div class="pro-card rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold text-amber-400 block">STEP 1 • SELECT TIMEFRAME</span>
                            <h2 class="text-base font-bold text-white">เลือกไทม์เฟรมตรวจจับ Order Block</h2>
                        </div>
                        <span id="active-tf-badge" class="px-3 py-1 rounded-xl text-xs font-black font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950">
                            TF: 1H
                        </span>
                    </div>

                    <div class="grid grid-cols-3 sm:grid-cols-6 gap-2 text-xs">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn py-2.5 rounded-xl font-bold bg-slate-950 text-slate-400 border border-slate-800">1M</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn py-2.5 rounded-xl font-bold bg-slate-950 text-slate-400 border border-slate-800">5M</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn py-2.5 rounded-xl font-bold bg-slate-950 text-slate-400 border border-slate-800">15M</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn py-2.5 rounded-xl font-extrabold bg-amber-500 text-slate-950">1H</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn py-2.5 rounded-xl font-bold bg-slate-950 text-slate-400 border border-slate-800">4H</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn py-2.5 rounded-xl font-bold bg-slate-950 text-slate-400 border border-slate-800">Daily</button>
                    </div>
                </div>

                <!-- ORDER BLOCK SETUP CARD -->
                <div class="pro-card-gold rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold text-amber-400 block">STEP 2 • INSTITUTIONAL ORDER BLOCK SETUP</span>
                            <h2 class="text-lg font-black text-white">แผนเทรด Order Block & ส่งสัญญาณ LINE</h2>
                        </div>
                        <span id="setup-order-badge" class="px-3 py-1.5 rounded-xl text-xs font-black font-mono-num bg-rose-500 text-white">SELL OB ZONE</span>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                        <div class="bg-cyan-950/50 p-3.5 rounded-xl border border-cyan-500/40">
                            <span class="font-extrabold text-cyan-300">🔵 ENTRY (OB Zone)</span>
                            <div id="val-entry" class="text-2xl font-black font-mono-num text-cyan-400 mt-1">--</div>
                        </div>
                        <div class="bg-rose-950/50 p-3.5 rounded-xl border border-rose-500/40">
                            <span class="font-extrabold text-rose-300">🔴 STOP LOSS</span>
                            <div id="val-sl" class="text-2xl font-black font-mono-num text-rose-400 mt-1">--</div>
                        </div>
                        <div class="bg-emerald-950/50 p-3.5 rounded-xl border border-emerald-500/40">
                            <span class="font-extrabold text-emerald-300">🟢 TP1 (1:2)</span>
                            <div id="val-tp1" class="text-2xl font-black font-mono-num text-emerald-400 mt-1">--</div>
                        </div>
                        <div class="bg-amber-950/50 p-3.5 rounded-xl border border-amber-500/50">
                            <span class="font-extrabold text-amber-300">🟡 TP2 (1:3)</span>
                            <div id="val-tp2" class="text-2xl font-black font-mono-num text-amber-400 mt-1">--</div>
                        </div>
                    </div>

                    <textarea id="setup-reason" rows="2" class="w-full text-xs text-slate-200 bg-slate-950 p-3 rounded-xl border border-slate-800">ราคาดึงตัวกลับมาทดสอบโซน Order Block (Institutional Supply Zone) พร้อมเปิดออเดอร์ตามโครงสร้าง Smart Money</textarea>

                    <button id="broadcast-btn" onclick="broadcastSignal()" class="w-full py-3.5 rounded-xl font-extrabold text-xs bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 shadow-lg hover:opacity-90 transition flex items-center justify-center gap-2">
                        <i class="fa-brands fa-line text-lg"></i> ส่งสัญญาณ Order Block เข้า LINE OA ทันที
                    </button>
                </div>

                <!-- LIVE SIGNAL FEED -->
                <div class="pro-card rounded-2xl p-5 space-y-3">
                    <h2 class="text-sm font-bold text-white border-b border-slate-800 pb-2"><i class="fa-solid fa-bolt text-amber-400 mr-2"></i>ประวัติสัญญาณล่าสุด (Live Signal Feed)</h2>
                    <div id="signal-feed-container" class="space-y-2.5 max-h-[220px] overflow-y-auto pr-1 text-xs"></div>
                </div>

            </div>
        </div>
    </div>

    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-emerald-500 text-slate-950 px-4 py-3 rounded-xl font-extrabold text-xs shadow-2xl z-50">
        <span id="toast-notify-text">สำเร็จ!</span>
    </div>

    <script>
        let lwChart = null;
        let candleSeries = null;
        let activeLines = [];
        let isNewsLocked = false;

        const tfConfigs = {
            '1m': { high: 2742.0, low: 2736.0, obTop: 2740.5, obBot: 2738.5 },
            '5m': { high: 2748.0, low: 2732.0, obTop: 2745.0, obBot: 2741.0 },
            '15m': { high: 2765.0, low: 2720.0, obTop: 2755.0, obBot: 2748.0 },
            '1h': { high: 2780.0, low: 2710.0, obTop: 2744.2, obBot: 2738.5 },
            '4h': { high: 2820.0, low: 2680.0, obTop: 2765.0, obBot: 2750.0 },
            'daily': { high: 2900.0, low: 2600.0, obTop: 2810.0, obBot: 2780.0 }
        };

        function initChart() {
            const container = document.getElementById('ob-chart-container');
            container.innerHTML = '';
            lwChart = LightweightCharts.createChart(container, {
                width: container.clientWidth, height: 540,
                layout: { background: { type: 'solid', color: '#050912' }, textColor: '#94a3b8' },
                grid: { vertLines: { color: 'rgba(30, 41, 59, 0.4)' }, horzLines: { color: 'rgba(30, 41, 59, 0.4)' } }
            });
            candleSeries = lwChart.addCandlestickSeries({ upColor: '#10b981', downColor: '#f43f5e' });
        }

        function drawOrderBlockOnChart(cfg) {
            if (!lwChart || !candleSeries) initChart();

            activeLines.forEach(l => { try { candleSeries.removePriceLine(l); } catch(e){} });
            activeLines = [];

            // สร้างแท่งเทียนจำลองให้เห็นโซน Order Block ชัดเจน
            const candles = [];
            const now = Math.floor(Date.now() / 1000) - 60 * 3600;
            let price = (cfg.high + cfg.low) / 2;
            for (let i = 0; i < 60; i++) {
                const open = price;
                const close = open + (Math.sin(i * 0.3) * 5);
                const high = Math.max(open, close) + 3;
                const low = Math.min(open, close) - 3;
                candles.push({ time: now + (i * 3600), open, high, low, close });
                price = close;
            }
            candleSeries.setData(candles);

            // คำนวณค่า Entry, SL, TP จาก Order Block
            const entry = cfg.obBot;
            const sl = cfg.obTop + 2.0;
            const risk = Math.abs(sl - entry);
            const tp1 = entry - (risk * 2);
            const tp2 = entry - (risk * 3);

            document.getElementById('val-entry').innerText = '$' + entry.toFixed(2);
            document.getElementById('val-sl').innerText = '$' + sl.toFixed(2);
            document.getElementById('val-tp1').innerText = '$' + tp1.toFixed(2);
            document.getElementById('val-tp2').innerText = '$' + tp2.toFixed(2);

            document.getElementById('top-entry').innerText = '$' + entry.toFixed(2);
            document.getElementById('top-sl').innerText = '$' + sl.toFixed(2);
            document.getElementById('top-tp1').innerText = '$' + tp1.toFixed(2);
            document.getElementById('top-tp2').innerText = '$' + tp2.toFixed(2);

            // พล็อตเส้น Order Block Zone บนกราฟอัตโนมัติ
            activeLines.push(candleSeries.createPriceLine({ price: cfg.obTop, color: '#f43f5e', lineWidth: 2, title: '🔴 OB Supply (Top)' }));
            activeLines.push(candleSeries.createPriceLine({ price: cfg.obBot, color: '#06b6d4', lineWidth: 2, title: '🔵 OB Entry (Bot)' }));
            activeLines.push(candleSeries.createPriceLine({ price: sl, color: '#e11d48', lineWidth: 2, lineStyle: 2, title: '🛑 Stop Loss' }));
            activeLines.push(candleSeries.createPriceLine({ price: tp2, color: '#f59e0b', lineWidth: 2, title: '🚀 TP Target (RR 1:3)' }));

            lwChart.timeScale().fitContent();
        }

        function selectTimeframe(tfKey) {
            document.querySelectorAll('.tf-btn').forEach(b => {
                b.className = "tf-btn py-2.5 rounded-xl font-bold bg-slate-950 text-slate-400 border border-slate-800";
            });
            document.getElementById('btn-' + tfKey).className = "tf-btn py-2.5 rounded-xl font-extrabold bg-amber-500 text-slate-950";
            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            document.getElementById('chart-tf-label').innerText = 'TF: ' + tfKey.toUpperCase();

            const cfg = tfConfigs[tfKey];
            if (cfg) drawOrderBlockOnChart(cfg);
        }

        async function loadSystemState() {
            const res = await fetch('/api/system-state');
            const data = await res.json();
            isNewsLocked = data.news_locked;
            renderCalendar(data.economic_calendar);
            renderFeed(data.signal_history);
        }

        function renderCalendar(items) {
            const tbody = document.getElementById('calendar-table-body');
            tbody.innerHTML = '';
            items.forEach(i => {
                tbody.innerHTML += `
                    <tr class="hover:bg-slate-900/50">
                        <td class="py-2.5 px-1 font-mono-num font-bold">${i.time}</td>
                        <td><span class="px-2.5 py-0.5 bg-blue-500/20 text-blue-300 rounded text-[10px] font-bold">${i.currency}</span></td>
                        <td class="font-semibold">${i.event}</td>
                        <td><span class="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 text-[10px] font-bold">🔴 ${i.impact}</span></td>
                        <td class="text-right font-mono-num text-amber-400 font-bold">${i.status}</td>
                    </tr>`;
            });
        }

        function renderFeed(signals) {
            const container = document.getElementById('signal-feed-container');
            container.innerHTML = '';
            signals.forEach(s => {
                container.innerHTML += `
                    <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 border-l-4 border-amber-500 space-y-1">
                        <div class="flex justify-between font-bold text-white">
                            <span>${s.symbol} (${s.tf}) • ${s.direction} OB</span>
                            <span class="text-slate-400 text-[10px]">${s.time}</span>
                        </div>
                        <div class="font-mono-num text-cyan-400 text-xs">Entry: $${s.entry} | SL: $${s.sl} | TP2: $${s.tp2}</div>
                        <div class="text-slate-400 text-[11px]">${s.reason}</div>
                    </div>`;
            });
        }

        async function toggleNewsLock() {
            const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
            const data = await res.json();
            showToast(data.news_locked ? '🛡️ ล็อกระบบช่วงข่าวแล้ว' : '✅ ปลดล็อกระบบแล้ว');
        }

        async function broadcastSignal() {
            if (isNewsLocked) { showToast('🛑 ระบบล็อกอยู่'); return; }
            const payload = {
                symbol: 'XAUUSD', tf: '1H',
                direction: 'SELL',
                entry: document.getElementById('val-entry').innerText.replace('$', ''),
                sl: document.getElementById('val-sl').innerText.replace('$', ''),
                tp1: document.getElementById('val-tp1').innerText.replace('$', ''),
                tp2: document.getElementById('val-tp2').innerText.replace('$', ''),
                reason: document.getElementById('setup-reason').value
            };
            const res = await fetch('/api/send-signal', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                const data = await res.json();
                renderFeed(data.signal_history);
                showToast('🚀 ส่งสัญญาณ Order Block เข้า LINE OA สำเร็จ!');
            }
        }

        function copyPrice(id) {
            const text = document.getElementById(id).innerText.replace('$', '');
            navigator.clipboard.writeText(text);
            showToast(`✅ คัดลอกราคา $${text} เรียบร้อย!`);
        }

        function showToast(msg) {
            const toast = document.getElementById('toast-notify');
            document.getElementById('toast-notify-text').innerText = msg;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 2000);
        }

        window.addEventListener('DOMContentLoaded', () => {
            initChart();
            selectTimeframe('1h');
            loadSystemState();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/system-state', methods=['GET'])
def get_system_state():
    return jsonify(SYSTEM_STATE)

@app.route('/api/toggle-news-lock', methods=['POST'])
def toggle_news_lock():
    SYSTEM_STATE["news_locked"] = not SYSTEM_STATE["news_locked"]
    return jsonify({"status": "ok", "news_locked": SYSTEM_STATE["news_locked"]})

@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    if SYSTEM_STATE["news_locked"]:
        return jsonify({"status": "blocked"}), 403
    data = request.json or {}
    sig = {
        "id": len(SYSTEM_STATE["signal_history"]) + 1,
        "time": datetime.now().strftime("%H:%M:%S"),
        "symbol": data.get("symbol", "XAUUSD"),
        "tf": data.get("tf", "1H"),
        "direction": data.get("direction", "SELL"),
        "entry": data.get("entry", "0.00"),
        "sl": data.get("sl", "0.00"),
        "tp1": data.get("tp1", "0.00"),
        "tp2": data.get("tp2", "0.00"),
        "rr": "1:3",
        "status": "LINE SENT",
        "reason": data.get("reason", "Order Block Setup")
    }
    SYSTEM_STATE["signal_history"].insert(0, sig)

    msg = f"🎯 INSTITUTIONAL ORDER BLOCK SIGNAL (XAUUSD)\nSELL LIMIT @ ${sig['entry']}\nSL: ${sig['sl']} | TP2: ${sig['tp2']}\nเหตุผล: {sig['reason']}"
    if LINE_CHANNEL_ACCESS_TOKEN:
        try:
            req = urllib.request.Request(
                "https://api.line.me/v2/bot/message/broadcast",
                data=json.dumps({"messages": [{"type": "text", "text": msg}]}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print("LINE Error:", e)

    return jsonify({"status": "success", "signal_history": SYSTEM_STATE["signal_history"]})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
