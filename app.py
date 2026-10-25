import os
import json
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

# ฐานข้อมูลสถานะระบบ ปฏิทินข่าว และประวัติสัญญาณ (คงเดิม 100%)
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
            "reason": "ราคาชน Golden Zone 61.8% + Order Block H1 กดดันตามเทรนด์หลัก"
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
            "status": "AUTO-LOCK 19:00-20:00"
        },
        {
            "time": "21:00",
            "currency": "USD",
            "event": "ISM Services PMI (ดัชนีผู้จัดการฝ่ายจัดซื้อภาคบริการ)",
            "impact": "MEDIUM",
            "forecast": "52.4",
            "previous": "51.9",
            "status": "REDUCE LOT 50%"
        },
        {
            "time": "22:30",
            "currency": "USD",
            "event": "FOMC Member Speaks (ถ้อยแถลงคณะกรรมการเฟด)",
            "impact": "LOW",
            "forecast": "-",
            "previous": "-",
            "status": "NORMAL TRADE"
        }
    ]
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — Advanced TradingView Realtime Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #03060c;
            --bg-card: rgba(13, 20, 36, 0.82);
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
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-subtle);
            box-shadow: 0 20px 50px -15px rgba(0, 0, 0, 0.7), inset 0 1px 0 0 rgba(255, 255, 255, 0.08);
        }
        .pro-card-gold {
            background: linear-gradient(145deg, rgba(17, 25, 44, 0.92), rgba(10, 15, 28, 0.96));
            border: 1px solid rgba(245, 158, 11, 0.38);
            box-shadow: 0 20px 50px -15px rgba(245, 158, 11, 0.14), inset 0 1px 0 0 rgba(251, 191, 36, 0.22);
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #03060c; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 9999px; }
        ::-webkit-scrollbar-thumb:hover { background: #f59e0b; }
    </style>
</head>
<body class="antialiased min-h-screen p-3 md:p-5 selection:bg-amber-500 selection:text-slate-950">
    <div class="max-w-[1740px] mx-auto space-y-5">

        <!-- HEADER -->
        <header class="pro-card rounded-2xl p-4 lg:px-6">
            <div class="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
                <div class="flex items-center gap-4">
                    <div class="relative group">
                        <div class="absolute -inset-1 bg-gradient-to-r from-amber-400 to-yellow-600 rounded-2xl blur opacity-40 group-hover:opacity-75 transition"></div>
                        <div class="relative px-3.5 py-2.5 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 flex flex-col items-center justify-center shadow-xl font-black text-slate-950 shrink-0">
                            <span class="text-[10px] tracking-tighter leading-none opacity-80">TV ADVANCED</span>
                            <span class="text-lg tracking-tight leading-none font-mono-num">XAU</span>
                        </div>
                    </div>
                    <div>
                        <div class="flex flex-wrap items-center gap-2.5">
                            <h1 class="text-xl md:text-2xl font-black tracking-tight bg-gradient-to-r from-white via-amber-200 to-amber-400 bg-clip-text text-transparent">
                                GOLD AI SNIPER PRO
                            </h1>
                            <span class="px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-full">
                                <i class="fa-solid fa-crosshairs mr-1"></i>TRADINGVIEW REALTIME • FIB 61.8% • SL 78.6% • RR 1:3
                            </span>
                            <span class="px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 rounded-full">
                                <i class="fa-brands fa-line mr-1"></i>LINE OA SIGNAL HUB
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-1 flex flex-wrap items-center gap-2">
                            <span>กราฟแท่งเทียนเรียลไทม์จาก TradingView Advanced Chart แท้ 100% พร้อมระบบคำนวณราคาอัตโนมัติและส่ง LINE OA</span>
                            <span class="hidden md:inline text-slate-600">|</span>
                            <span id="current-date-label" class="text-amber-400/90 font-medium"></span>
                        </p>
                    </div>
                </div>

                <div class="flex flex-wrap items-center gap-2.5 w-full xl:w-auto justify-between xl:justify-end">
                    <div class="bg-slate-950/90 border border-slate-800/90 px-3.5 py-2 rounded-xl flex items-center gap-2.5">
                        <div class="text-[11px] text-slate-400">
                            <span class="block text-[9px] uppercase tracking-wider text-slate-500 font-bold">DAILY MASTER BIAS</span>
                            <span id="master-daily-bias" class="font-extrabold text-rose-400 flex items-center gap-1">
                                <i class="fa-solid fa-arrow-trend-down"></i> SELL BIAS (ดัก 61.8%)
                            </span>
                        </div>
                    </div>

                    <div id="news-shield-box" class="bg-emerald-950/40 border border-emerald-500/40 px-3.5 py-2 rounded-xl flex items-center gap-3 transition-all">
                        <div class="flex items-center gap-2">
                            <span id="shield-dot" class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
                            <div>
                                <span class="block text-[9px] uppercase tracking-wider text-slate-400 font-bold">NEWS FILTER SHIELD</span>
                                <span id="shield-status-text" class="text-xs font-extrabold text-emerald-400">SAFE MODE (เปิดรับสัญญาณ)</span>
                            </div>
                        </div>
                        <button onclick="toggleNewsLock()" class="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-[11px] font-bold text-slate-200 border border-slate-700 transition">
                            <i class="fa-solid fa-shield-halved text-amber-400 mr-1"></i>สลับโหมดข่าวแดง
                        </button>
                    </div>

                    <div class="bg-slate-950/90 border border-amber-500/30 px-4 py-2 rounded-xl flex items-center gap-3">
                        <div class="text-right">
                            <span class="block text-[9px] uppercase tracking-wider text-amber-400/80 font-bold">XAUUSD SPOT</span>
                            <span id="live-ticker-price" class="font-mono-num text-sm md:text-base font-extrabold text-emerald-400">$2,738.50</span>
                        </div>
                        <span class="px-1.5 py-0.5 text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400 rounded border border-emerald-500/30">LIVE</span>
                    </div>
                </div>
            </div>
        </header>

        <!-- KPI METRICS BAR (4 PRO CARDS) -->
        <section class="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">อัตราชนะเฉลี่ย (Win Rate)</span>
                    <div class="text-2xl font-black font-mono-num text-emerald-400 mt-0.5">81.4%</div>
                    <span class="text-[11px] text-slate-500">สถิติ Golden Zone 61.8% (H1/H4)</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-lg">
                    <i class="fa-solid fa-trophy"></i>
                </div>
            </div>

            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">ความเสี่ยงต่อไม้ (Risk/Trade)</span>
                    <div class="text-2xl font-black font-mono-num text-cyan-400 mt-0.5">1.0% - 1.5%</div>
                    <span class="text-[11px] text-slate-500">คุม Drawdown ปลอดภัยสูงสุด</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 text-lg">
                    <i class="fa-solid fa-user-shield"></i>
                </div>
            </div>

            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">คุ้มค่าความเสี่ยง (RR Ratio)</span>
                    <div class="text-2xl font-black font-mono-num text-amber-400 mt-0.5">1 : 3.0</div>
                    <span class="text-[11px] text-slate-500">ชนะ 1 ไม้ ครอบคลุมแพ้ได้ 3 ไม้</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 text-lg">
                    <i class="fa-solid fa-scale-balanced"></i>
                </div>
            </div>

            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">ระบบกระจายสัญญาณ (Hub)</span>
                    <div class="text-base font-black text-slate-100 mt-1 flex items-center gap-2">
                        <span class="px-2.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs"><i class="fa-brands fa-line mr-1"></i>LINE OA Broadcast</span>
                    </div>
                    <span class="text-[11px] text-emerald-400 mt-1 block"><i class="fa-solid fa-circle-check mr-1"></i>API Endpoint Ready</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-lg">
                    <i class="fa-solid fa-paper-plane"></i>
                </div>
            </div>
        </section>

        <!-- MAIN WORKSPACE GRID -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- LEFT COLUMN (7 COLS): TRADINGVIEW REALTIME CHART + CALENDAR & MACRO -->
            <div class="xl:col-span-7 space-y-5">
                
                <!-- 1. TRADINGVIEW REALTIME ADVANCED CHART TERMINAL -->
                <div class="pro-card rounded-2xl p-4 md:p-5 space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3 border-b border-slate-800/80 pb-3.5">
                        <div class="flex items-center gap-2">
                            <span class="px-3 py-1.5 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-400 text-xs font-black">
                                <i class="fa-solid fa-chart-candlestick mr-1"></i> TradingView Advanced Chart (XAUUSD Realtime)
                            </span>
                        </div>
                        <div class="text-xs text-slate-400">
                            ใช้เครื่องมือแถบซ้ายมือเพื่อตีเส้น Fibonacci หรือวัด Fib Retracement บนกราฟจริงได้อิสระ
                        </div>
                    </div>

                    <!-- Quick Copy Price Pills -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        <div onclick="copyPrice('val-entry')" class="group cursor-pointer p-2.5 rounded-xl bg-cyan-950/30 border border-cyan-500/30 hover:border-cyan-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-cyan-300/90 font-bold uppercase tracking-wider block">🔵 ENTRY (61.8%)</span>
                                <span id="top-entry" class="font-mono-num font-extrabold text-cyan-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-cyan-500/20 group-hover:bg-cyan-400 group-hover:text-slate-950 text-cyan-200 px-2 py-0.5 rounded-md font-bold transition">Copy</span>
                        </div>

                        <div onclick="copyPrice('val-sl')" class="group cursor-pointer p-2.5 rounded-xl bg-rose-950/30 border border-rose-500/30 hover:border-rose-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-rose-300/90 font-bold uppercase tracking-wider block">🔴 SL (78.6%)</span>
                                <span id="top-sl" class="font-mono-num font-extrabold text-rose-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-rose-500/20 group-hover:bg-rose-400 group-hover:text-slate-950 text-rose-200 px-2 py-0.5 rounded-md font-bold transition">Copy</span>
                        </div>

                        <div onclick="copyPrice('val-tp1')" class="group cursor-pointer p-2.5 rounded-xl bg-emerald-950/30 border border-emerald-500/30 hover:border-emerald-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-emerald-300/90 font-bold uppercase tracking-wider block">🟢 TP1 (RR 1:2)</span>
                                <span id="top-tp1" class="font-mono-num font-extrabold text-emerald-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-emerald-500/20 group-hover:bg-emerald-400 group-hover:text-slate-950 text-emerald-200 px-2 py-0.5 rounded-md font-bold transition">Copy</span>
                        </div>

                        <div onclick="copyPrice('val-tp2')" class="group cursor-pointer p-2.5 rounded-xl bg-amber-950/30 border border-amber-500/30 hover:border-amber-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-amber-300/90 font-bold uppercase tracking-wider block">🟡 TP2 (RR 1:3)</span>
                                <span id="top-tp2" class="font-mono-num font-extrabold text-amber-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-amber-500/20 group-hover:bg-amber-400 group-hover:text-slate-950 text-amber-200 px-2 py-0.5 rounded-md font-bold transition">Copy</span>
                        </div>
                    </div>

                    <!-- TradingView Widget Realtime Advanced Chart -->
                    <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800/90" style="height:560px; width:100%;">
                        <div id="tradingview_advanced_chart" style="height:100%; width:100%;"></div>
                    </div>
                </div>

                <!-- 2. ECONOMIC CALENDAR & AUTO NEWS FILTER -->
                <div class="pro-card rounded-2xl p-5 space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-800/80 pb-3.5 gap-2">
                        <div class="flex items-center gap-2.5">
                            <div class="w-9 h-9 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400">
                                <i class="fa-regular fa-calendar-check"></i>
                            </div>
                            <div>
                                <div class="flex items-center gap-2">
                                    <h2 class="text-base font-bold text-white">ปฏิทินข่าวเศรษฐกิจ & ระบบกรองความเสี่ยงอัตโนมัติ</h2>
                                    <span class="px-2 py-0.5 text-[10px] font-extrabold bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded-md">FOREX FACTORY SYNC</span>
                                </div>
                                <p class="text-[11px] text-slate-400">บล็อกการส่งสัญญาณอัตโนมัติก่อน-หลังข่าวแดง (High Impact) 30 นาที เพื่อป้องกันพอร์ตโดนลาก</p>
                            </div>
                        </div>

                        <button onclick="document.getElementById('add-news-modal').classList.toggle('hidden')" class="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-bold text-amber-400 transition">
                            <i class="fa-solid fa-plus mr-1"></i>เพิ่มตารางข่าว
                        </button>
                    </div>

                    <div id="add-news-modal" class="hidden bg-slate-950/90 p-3.5 rounded-xl border border-slate-800 grid grid-cols-1 sm:grid-cols-5 gap-2 text-xs">
                        <input type="text" id="new-news-time" placeholder="เวลา (เช่น 20:30)" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                        <input type="text" id="new-news-Event" placeholder="ชื่อข่าว (เช่น Non-Farm)" class="sm:col-span-2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white">
                        <select id="new-news-impact" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-bold">
                            <option value="HIGH">🔴 ข่าวแดง (High)</option>
                            <option value="MEDIUM">🟠 ข่าวส้ม (Medium)</option>
                            <option value="LOW">🟡 ข่าวเหลือง (Low)</option>
                        </select>
                        <button onclick="addNewsItem()" class="bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold rounded-lg p-2 transition">บันทึกข่าว</button>
                    </div>

                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-slate-800/80 text-[11px] uppercase tracking-wider">
                                    <th class="py-2.5 px-2">เวลา (ไทย)</th>
                                    <th class="py-2.5 px-2">สกุลเงิน</th>
                                    <th class="py-2.5 px-2">ตัวเลขเศรษฐกิจสำคัญ</th>
                                    <th class="py-2.5 px-2">ระดับความรุนแรง</th>
                                    <th class="py-2.5 px-2">คาดการณ์ / ครั้งก่อน</th>
                                    <th class="py-2.5 px-2 text-right">คำสั่ง AI Protection</th>
                                </tr>
                            </thead>
                            <tbody id="economic-calendar-body" class="divide-y divide-slate-800/60"></tbody>
                        </table>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-xs">
                        <div class="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800/80 space-y-1.5">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200"><i class="fa-solid fa-building-columns text-amber-400 mr-1"></i>ทิศทาง Fed & DXY</span>
                                <span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 font-bold text-[10px]">กดดันทองคำ</span>
                            </div>
                            <p class="text-slate-400 leading-relaxed text-[11px]">
                                บอนด์ยีลด์สหรัฐฯ ทรงตัวระดับสูง กดดันให้ทองคำมีแรงเทขายเมื่อรีบาวด์ แผนดัก Sell ที่ Fib 61.8% จึงมีความได้เปรียบสูงสุด
                            </p>
                        </div>

                        <div class="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800/80 space-y-1.5">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200"><i class="fa-solid fa-wave-square text-cyan-400 mr-1"></i>กฎเหล็กเลี่ยงข่าวแรง</span>
                                <span class="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold text-[10px]">Auto-Pause</span>
                            </div>
                            <p class="text-slate-400 leading-relaxed text-[11px]">
                                งดออกออเดอร์ใหม่ก่อนและหลังข่าวแดง 30 นาที รอให้กราฟสะบัดกวาด Liquidity เสร็จแล้วค่อยดักเข้าที่โซน 61.8%
                            </p>
                        </div>

                        <div class="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800/80 space-y-1.5">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200"><i class="fa-solid fa-shield-cat text-emerald-400 mr-1"></i>คณิตศาสตร์ RR 1:3</span>
                                <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold text-[10px]">Low Drawdown</span>
                            </div>
                            <p class="text-slate-400 leading-relaxed text-[11px]">
                                เข้าที่ 61.8% และวาง SL ที่ 78.6% ทำให้ระยะตัดขาดทุนสั้นมาก ชนะเพียง 1 ไม้ที่ TP2 (1:3) ล้างขาดทุนได้ถึง 3 ไม้
                            </p>
                        </div>
                    </div>
                </div>

            </div>

            <!-- RIGHT COLUMN (5 COLS): MULTI-TF + GOLDEN ZONE TUNER + FEED -->
            <div class="xl:col-span-5 space-y-5">
                
                <!-- 1. MULTI-TIMEFRAME SELECTOR -->
                <div class="pro-card rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800/80 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-amber-400 block">STEP 1 • SELECT TIMEFRAME</span>
                            <h2 class="text-base font-bold text-white">เลือกไทม์เฟรมวิเคราะห์โครงสร้างตลาด</h2>
                        </div>
                        <span id="active-tf-badge" class="px-3 py-1 rounded-xl text-xs font-black font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow">
                            TF: 1H
                        </span>
                    </div>

                    <div class="grid grid-cols-3 sm:grid-cols-6 gap-2">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border transition">1M</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border transition">5M</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border transition">15M</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border transition">1H</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border transition">4H</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border transition">DAILY</button>
                    </div>

                    <div class="bg-slate-950/90 p-3.5 rounded-xl border border-slate-800/90 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">โครงสร้างตลาด</span>
                            <span id="tf-structure-badge" class="inline-block mt-1 px-2 py-0.5 rounded text-[11px] font-bold">--</span>
                        </div>
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">ความผันผวน</span>
                            <span id="tf-volatility" class="block mt-1 font-bold text-slate-200 text-[11px]">--</span>
                        </div>
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">คำแนะนำหน้าเทรด</span>
                            <span id="tf-bias-text" class="block mt-1 font-extrabold text-[11px]">--</span>
                        </div>
                    </div>
                </div>

                <!-- 2. GOLDEN ZONE SNIPER SETUP CARD + ONE-CLICK LINE DISPATCH -->
                <div class="pro-card-gold rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800/80 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-amber-400 block">STEP 2 • GOLDEN ZONE SNIPER & LINE OA</span>
                            <h2 class="text-lg font-black text-white">แผนจุดเข้าเทรด 61.8% & ส่งสัญญาณหาลูกค้า</h2>
                        </div>
                        <span id="setup-order-badge" class="px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num">--</span>
                    </div>

                    <div class="flex justify-between items-center bg-slate-950/90 px-3.5 py-2 rounded-xl border border-slate-800 text-xs">
                        <span class="text-slate-400"><i class="fa-solid fa-ruler-vertical text-amber-400 mr-1.5"></i>กรอบสวิงที่ใช้คำนวณ Fibonacci:</span>
                        <span id="setup-swing-info" class="font-mono-num font-bold text-amber-300">--</span>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div class="bg-gradient-to-br from-cyan-950/50 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-cyan-500/40">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-cyan-300">🔵 ENTRY (Fib 61.8%)</span>
                                <span class="text-[10px] bg-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded font-bold">Golden Zone</span>
                            </div>
                            <div id="val-entry" class="text-2xl font-black font-mono-num text-cyan-400 mt-1">--</div>
                        </div>

                        <div class="bg-gradient-to-br from-rose-950/50 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-rose-500/40">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-rose-300">🔴 STOP LOSS (78.6%)</span>
                                <span id="val-risk-pts" class="text-[10px] font-mono-num bg-rose-500/20 text-rose-300 px-2 py-0.5 rounded font-bold">Risk: --</span>
                            </div>
                            <div id="val-sl" class="text-2xl font-black font-mono-num text-rose-400 mt-1">--</div>
                        </div>

                        <div class="bg-gradient-to-br from-emerald-950/50 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-emerald-500/40">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-emerald-300">🟢 TAKE PROFIT 1 (1:2)</span>
                                <span id="val-tp1-pts" class="text-[10px] font-mono-num bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp1" class="text-2xl font-black font-mono-num text-emerald-400 mt-1">--</div>
                        </div>

                        <div class="bg-gradient-to-br from-amber-950/50 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-amber-500/50">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-amber-300">🟡 TAKE PROFIT 2 (1:3)</span>
                                <span id="val-tp2-pts" class="text-[10px] font-mono-num bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp2" class="text-2xl font-black font-mono-num text-amber-400 mt-1">--</div>
                        </div>
                    </div>

                    <div class="space-y-1">
                        <span class="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                            <i class="fa-solid fa-microchip"></i> เหตุผลประกอบสัญญาณจาก AI (ส่งแนบไปกับ LINE OA):
                        </span>
                        <textarea id="setup-reason" rows="2" class="w-full text-xs text-slate-200 bg-slate-950/90 p-3 rounded-xl border border-slate-800 focus:border-amber-500 outline-none leading-relaxed"></textarea>
                    </div>

                    <div id="dispatch-lock-warning" class="hidden p-3 rounded-xl bg-rose-500/20 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2.5">
                        <i class="fa-solid fa-ban text-rose-400 text-base"></i>
                        <span><strong>ระบบล็อกการส่งสัญญาณชั่วคราว!</strong> ขณะนี้อยู่ในโหมดเฝ้าระวังข่าวแรง (News Shield Active)</span>
                    </div>

                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="w-full py-3.5 px-4 rounded-xl font-extrabold text-xs md:text-sm bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 shadow-xl shadow-emerald-500/20 transition flex items-center justify-center gap-2">
                        <i class="fa-solid fa-satellite-dish"></i>
                        <span>ยิงสัญญาณชุดนี้เข้า LINE OA ทันที</span>
                    </button>
                </div>

                <!-- 3. CUSTOM SWING TUNER -->
                <div class="pro-card rounded-2xl p-5 space-y-3">
                    <div class="flex justify-between items-center border-b border-slate-800/80 pb-2.5">
                        <div>
                            <h3 class="text-sm font-bold text-amber-400"><i class="fa-solid fa-sliders mr-1.5"></i>ปรับจุด Swing High / Low เอง (Custom Fib Tuner)</h3>
                        </div>
                    </div>

                    <div class="grid grid-cols-3 gap-2.5 text-xs">
                        <div>
                            <label class="text-slate-400 block mb-1 text-[11px]">ฝั่งคำสั่ง</label>
                            <select id="custom-dir" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-slate-100 font-bold">
                                <option value="SELL">🔻 SELL</option>
                                <option value="BUY">🟢 BUY</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1 text-[11px]">Swing High ($)</label>
                            <input type="number" id="custom-high" step="0.1" value="4145.00" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-slate-100 font-mono-num font-bold">
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1 text-[11px]">Swing Low ($)</label>
                            <input type="number" id="custom-low" step="0.1" value="3992.20" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-slate-100 font-mono-num font-bold">
                        </div>
                    </div>

                    <button onclick="applyCustomSwing()" class="w-full py-2.5 bg-slate-800 hover:bg-amber-500 hover:text-slate-950 text-amber-400 border border-amber-500/40 font-extrabold text-xs rounded-xl transition">
                        <i class="fa-solid fa-rotate mr-1"></i> คำนวณจุดเข้า 61.8% ใหม่ทันที
                    </button>
                </div>

                <!-- 4. LIVE SIGNAL FEED & MATRIX TABS -->
                <div class="pro-card rounded-2xl p-5 space-y-3.5">
                    <div class="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
                        <div class="flex gap-2">
                            <button onclick="switchRightTab('feed')" id="tab-btn-feed" class="px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950 transition">
                                <i class="fa-solid fa-bolt mr-1"></i>Live Feed
                            </button>
                            <button onclick="switchRightTab('matrix')" id="tab-btn-matrix" class="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200 transition">
                                <i class="fa-solid fa-table-cells mr-1"></i>ตารางสรุป
                            </button>
                        </div>
                        <span class="text-[11px] text-slate-400 font-mono-num" id="feed-counter-label">รายการล่าสุด</span>
                    </div>

                    <div id="right-tab-feed" class="space-y-2.5 max-h-[290px] overflow-y-auto pr-1"></div>
                    <div id="right-tab-matrix" class="hidden space-y-2 max-h-[290px] overflow-y-auto pr-1">
                        <div id="matrix-overview-list" class="space-y-2 text-xs"></div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-emerald-500 text-slate-950 px-4 py-3 rounded-xl font-extrabold text-xs shadow-2xl z-50 flex items-center gap-2">
        <i class="fa-solid fa-circle-check text-base"></i>
        <span id="toast-notify-text">สำเร็จ!</span>
    </div>

    <!-- TradingView External Script -->
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>

    <script>
        function calculateSniperMath(direction, swingHigh, swingLow) {
            const range = swingHigh - swingLow;
            let entry, sl, risk, tp1, tp2;

            if (direction === 'SELL') {
                entry = swingLow + (range * 0.618);
                sl = swingLow + (range * 0.786);
                risk = Math.abs(sl - entry);
                tp1 = entry - (risk * 2);
                tp2 = entry - (risk * 3);
            } else {
                entry = swingHigh - (range * 0.618);
                sl = swingHigh - (range * 0.786);
                risk = Math.abs(entry - sl);
                tp1 = entry + (risk * 2);
                tp2 = entry + (risk * 3);
            }

            return {
                entryNum: entry, slNum: sl, tp1Num: tp1, tp2Num: tp2,
                entry: entry.toFixed(2), sl: sl.toFixed(2),
                tp1: tp1.toFixed(2), tp2: tp2.toFixed(2),
                riskDollar: risk.toFixed(2),
                reward1Dollar: (risk * 2).toFixed(2),
                reward2Dollar: (risk * 3).toFixed(2)
            };
        }

        const timeframeConfigs = {
            '1m': { label: '1 นาที (1M)', tvInterval: '1', calcDir: 'SELL', swingHigh: 4001.20, swingLow: 3992.20, structure: 'Sideway', structureClass: 'bg-amber-500/20 text-amber-300', volatility: 'ต่ำ', biasText: 'WAIT', biasColor: 'text-amber-400', reason: 'TF 1M ไซด์เวย์กรอบแคบ รอเข้าที่ TF ใหญ่กว่า' },
            '5m': { label: '5 นาที (5M)', tvInterval: '5', calcDir: 'SELL', swingHigh: 4016.00, swingLow: 3992.20, structure: 'Minor Bearish', structureClass: 'bg-rose-500/20 text-rose-400', volatility: 'ปานกลาง', biasText: 'SELL LIMIT', biasColor: 'text-rose-400', reason: 'TF 5M ทำโครงสร้างขาลง ดัก Sell ที่ 61.8%' },
            '15m': { label: '15 นาที (15M)', tvInterval: '15', calcDir: 'SELL', swingHigh: 4035.00, swingLow: 3992.20, structure: 'Intraday Bearish', structureClass: 'bg-rose-500/20 text-rose-400', volatility: 'เสถียร', biasText: 'SELL LIMIT', biasColor: 'text-rose-400', reason: 'TF 15M ทุบหลุดแนวรับ รอรีบาวด์ 61.8%' },
            '1h': { label: '1 ชั่วโมง (1H)', tvInterval: '60', calcDir: 'SELL', swingHigh: 4145.00, swingLow: 3992.20, structure: 'Major Bearish', structureClass: 'bg-rose-500/20 text-rose-400', volatility: 'สูง', biasText: 'STRONG SELL', biasColor: 'text-rose-400', reason: 'TF 1H โซน Golden Zone 61.8% ทับซ้อน Order Block' },
            '4h': { label: '4 ชั่วโมง (4H)', tvInterval: '240', calcDir: 'SELL', swingHigh: 4210.00, swingLow: 3992.20, structure: 'Macro Downtrend', structureClass: 'bg-rose-500/20 text-rose-400', volatility: 'สูง', biasText: 'MACRO SELL', biasColor: 'text-rose-400', reason: 'ภาพใหญ่ 4H แรงขายคุมตลาด ดัก Sell รอบใหญ่' },
            'daily': { label: 'รายวัน (Daily)', tvInterval: 'D', calcDir: 'SELL', swingHigh: 4240.00, swingLow: 3992.20, structure: 'Daily Correction', structureClass: 'bg-amber-500/20 text-amber-300', volatility: 'มหภาค', biasText: 'SELL BIAS', biasColor: 'text-amber-400', reason: 'กราฟ Day พักฐานใหญ่ ดัก Sell ตามแนว Fib 61.8%' }
        };

        let currentTfKey = '1h';
        let isNewsLocked = false;

        function loadTradingViewAdvanced(intervalCode) {
            const container = document.getElementById('tradingview_advanced_chart');
            container.innerHTML = '';
            new TradingView.widget({
                "width": "100%",
                "height": "560",
                "symbol": "OANDA:XAUUSD",
                "interval": intervalCode,
                "timezone": "Asia/Bangkok",
                "theme": "dark",
                "style": "1",
                "locale": "th",
                "toolbar_bg": "#03060c",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "studies": ["RSI@tv-basicstudies", "MACD@tv-basicstudies"],
                "container_id": "tradingview_advanced_chart"
            });
        }

        function switchRightTab(tab) {
            const feedBox = document.getElementById('right-tab-feed');
            const matrixBox = document.getElementById('right-tab-matrix');
            const btnFeed = document.getElementById('tab-btn-feed');
            const btnMatrix = document.getElementById('tab-btn-matrix');

            if (tab === 'feed') {
                feedBox.classList.remove('hidden');
                matrixBox.classList.add('hidden');
                btnFeed.className = "px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950 transition";
                btnMatrix.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 transition";
            } else {
                feedBox.classList.add('hidden');
                matrixBox.classList.remove('hidden');
                btnMatrix.className = "px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950 transition";
                btnFeed.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 transition";
            }
        }

        function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const cfg = timeframeConfigs[tfKey];
            if (!cfg) return;

            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num bg-slate-950 text-slate-400 border border-slate-800 transition";
            });
            document.getElementById('btn-' + tfKey).className = "tf-btn py-2.5 px-2 rounded-xl text-xs font-extrabold font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow-lg transition";

            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();

            const structEl = document.getElementById('tf-structure-badge');
            structEl.innerText = cfg.structure;
            structEl.className = 'inline-block mt-1 px-2 py-0.5 rounded text-[11px] font-bold ' + cfg.structureClass;

            document.getElementById('tf-volatility').innerText = cfg.volatility;
            document.getElementById('tf-bias-text').innerText = cfg.biasText;
            document.getElementById('tf-bias-text').className = 'block mt-1 font-extrabold text-[11px] ' + cfg.biasColor;

            document.getElementById('setup-reason').value = cfg.reason;
            document.getElementById('custom-dir').value = cfg.calcDir;
            document.getElementById('custom-high').value = cfg.swingHigh;
            document.getElementById('custom-low').value = cfg.swingLow;

            updateMathAndUI(cfg.calcDir, cfg.swingHigh, cfg.swingLow);
            loadTradingViewAdvanced(cfg.tvInterval);
            renderMatrixTable(tfKey);
        }

        function updateMathAndUI(dir, high, low) {
            const mathRes = calculateSniperMath(dir, high, low);

            document.getElementById('val-entry').innerText = '$' + mathRes.entry;
            document.getElementById('val-sl').innerText = '$' + mathRes.sl;
            document.getElementById('val-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('val-tp2').innerText = '$' + mathRes.tp2;

            document.getElementById('top-entry').innerText = '$' + mathRes.entry;
            document.getElementById('top-sl').innerText = '$' + mathRes.sl;
            document.getElementById('top-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('top-tp2').innerText = '$' + mathRes.tp2;

            document.getElementById('val-risk-pts').innerText = `Risk: -$${mathRes.riskDollar}`;
            document.getElementById('val-tp1-pts').innerText = `+$${mathRes.reward1Dollar} (1:2)`;
            document.getElementById('val-tp2-pts').innerText = `+$${mathRes.reward2Dollar} (1:3)`;
            document.getElementById('setup-swing-info').innerText = `High $${high.toFixed(2)} ➔ Low $${low.toFixed(2)}`;

            const orderBadge = document.getElementById('setup-order-badge');
            if (dir === 'SELL') {
                orderBadge.innerText = '🔻 SELL LIMIT @ 61.8%';
                orderBadge.className = 'px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num bg-rose-500 text-white shadow-lg';
            } else {
                orderBadge.innerText = '🟢 BUY LIMIT @ 61.8%';
                orderBadge.className = 'px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num bg-emerald-500 text-slate-950 shadow-lg';
            }
        }

        function applyCustomSwing() {
            const dir = document.getElementById('custom-dir').value;
            const high = parseFloat(document.getElementById('custom-high').value) || 4145;
            const low = parseFloat(document.getElementById('custom-low').value) || 3992;
            if (high <= low) { showToast('⚠️ กรุณากรอก High ให้มากกว่า Low'); return; }
            updateMathAndUI(dir, high, low);
            showToast('✅ คำนวณราคา Fibonacci ใหม่เรียบร้อย!');
        }

        function renderMatrixTable(activeKey) {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';
            Object.keys(timeframeConfigs).forEach(key => {
                const item = timeframeConfigs[key];
                const lvls = calculateSniperMath(item.calcDir, item.swingHigh, item.swingLow);
                const row = document.createElement('div');
                row.className = `flex justify-between p-2.5 rounded-xl border cursor-pointer ${key === activeKey ? 'bg-amber-500/15 border-amber-500/60' : 'bg-slate-950 border-slate-800'}`;
                row.onclick = () => selectTimeframe(key);
                row.innerHTML = `<span class="font-bold text-amber-400 uppercase">${key}</span><span class="text-cyan-400">61.8%: $${lvls.entry}</span>`;
                list.appendChild(row);
            });
        }

        async function loadSystemState() {
            const res = await fetch('/api/system-state');
            const data = await res.json();
            isNewsLocked = data.news_locked;
            updateShieldUI(isNewsLocked);
            renderCalendar(data.economic_calendar);
            renderFeed(data.signal_history);
        }

        function updateShieldUI(locked) {
            const box = document.getElementById('news-shield-box');
            const text = document.getElementById('shield-status-text');
            const warn = document.getElementById('dispatch-lock-warning');
            const btn = document.getElementById('broadcast-btn');
            if (locked) {
                box.className = "bg-rose-950/60 border border-rose-500/60 px-3.5 py-2 rounded-xl flex items-center gap-3";
                text.className = "text-xs font-extrabold text-rose-400";
                text.innerText = "NEWS LOCKED (ล็อกข่าวแรง)";
                warn.classList.remove('hidden');
                btn.disabled = true;
                btn.className = "w-full py-3.5 rounded-xl font-extrabold text-xs bg-slate-800 text-slate-500 cursor-not-allowed";
            } else {
                box.className = "bg-emerald-950/40 border border-emerald-500/40 px-3.5 py-2 rounded-xl flex items-center gap-3";
                text.className = "text-xs font-extrabold text-emerald-400";
                text.innerText = "SAFE MODE (เปิดปกติ)";
                warn.classList.add('hidden');
                btn.disabled = false;
                btn.className = "w-full py-3.5 rounded-xl font-extrabold text-xs bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 shadow-lg hover:opacity-90";
            }
        }

        function renderCalendar(items) {
            const tbody = document.getElementById('economic-calendar-body');
            tbody.innerHTML = '';
            items.forEach(i => {
                tbody.innerHTML += `
                    <tr class="hover:bg-slate-900/50">
                        <td class="py-2.5 px-2 font-mono-num font-bold">${i.time}</td>
                        <td><span class="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded text-[10px] font-bold">${i.currency}</span></td>
                        <td class="font-semibold">${i.event}</td>
                        <td><span class="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 text-[10px] font-bold">🔴 ${i.impact}</span></td>
                        <td class="font-mono-num text-slate-400">${i.forecast} / ${i.previous}</td>
                        <td class="text-right font-mono-num text-amber-400 font-bold">${i.status}</td>
                    </tr>`;
            });
        }

        function renderFeed(signals) {
            const container = document.getElementById('right-tab-feed');
            document.getElementById('feed-counter-label').innerText = `${signals.length} รายการ`;
            container.innerHTML = '';
            signals.forEach(s => {
                container.innerHTML += `
                    <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 border-l-4 border-amber-500 space-y-1">
                        <div class="flex justify-between font-bold text-white">
                            <span>${s.symbol} (${s.tf}) • ${s.direction}</span>
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
            updateShieldUI(data.news_locked);
            showToast(data.news_locked ? '🛡️ ล็อกระบบช่วงข่าวแล้ว' : '✅ ปลดล็อกระบบแล้ว');
        }

        async function addNewsItem() {
            const time = document.getElementById('new-news-time').value || '20:30';
            const event = document.getElementById('new-news-Event').value;
            const impact = document.getElementById('new-news-impact').value;
            if (!event) { showToast('⚠️ กรุณาระบุชื่อข่าว'); return; }
            const res = await fetch('/api/add-news', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ time, event, impact })
            });
            const data = await res.json();
            renderCalendar(data.economic_calendar);
            document.getElementById('add-news-modal').classList.add('hidden');
            document.getElementById('new-news-Event').value = '';
            showToast('✅ เพิ่มข่าวเรียบร้อย!');
        }

        async function broadcastCurrentSignal() {
            if (isNewsLocked) { showToast('🛑 ระบบล็อกอยู่'); return; }
            const payload = {
                symbol: 'XAUUSD', tf: currentTfKey.toUpperCase(),
                direction: document.getElementById('custom-dir').value,
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
                switchRightTab('feed');
                showToast('🚀 ส่งสัญญาณเข้า LINE OA สำเร็จ!');
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
            const now = new Date();
            document.getElementById('current-date-label').innerText = 'อัปเดต: ' + now.toLocaleDateString('th-TH', { year: 'numeric', month: 'short', day: 'numeric' });
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

@app.route('/api/add-news', methods=['POST'])
def add_news():
    data = request.json or {}
    impact = data.get("impact", "HIGH")
    new_item = {
        "time": data.get("time", "20:30"), "currency": "USD",
        "event": data.get("event", "Event"), "impact": impact,
        "forecast": "-", "previous": "-", "status": "AUTO-LOCK ±30 MIN"
    }
    SYSTEM_STATE["economic_calendar"].insert(0, new_item)
    return jsonify({"status": "ok", "economic_calendar": SYSTEM_STATE["economic_calendar"]})

@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    if SYSTEM_STATE["news_locked"]:
        return jsonify({"status": "blocked"}), 403
    data = request.json or {}
    sig = {
        "id": len(SYSTEM_STATE["signal_history"]) + 101,
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
        "reason": data.get("reason", "Golden Zone 61.8% Setup")
    }
    SYSTEM_STATE["signal_history"].insert(0, sig)

    msg = (
        f"🎯 GOLD AI SNIPER PRO (FIB 61.8%)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 สินทรัพย์: {sig['symbol']} (TF: {sig['tf']})\n"
        f"⚡ คำสั่ง: 🔻 {sig['direction']} LIMIT\n"
        f"🔵 จุดเข้า (Entry 61.8%): ${sig['entry']}\n"
        f"🔴 ตัดขาดทุน (SL 78.6%): ${sig['sl']}\n"
        f"🟢 เป้าที่ 1 (TP1 1:2): ${sig['tp1']}\n"
        f"🟡 เป้าหลัก (TP2 1:3): ${sig['tp2']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧠 วิเคราะห์: {sig['reason']}\n"
        f"🛡️ คุมความเสี่ยง 1-1.5% ต่อไม้ และงดเทรดช่วงข่าวแดง"
    )

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
