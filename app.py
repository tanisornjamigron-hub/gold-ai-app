import os
import json
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# ==============================================================================
# ตั้งค่า Webhook สำหรับแจ้งเตือนลูกค้า (ใส่ลิงก์จริงเมื่อพร้อมใช้งาน)
# ==============================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

# ฐานข้อมูลจำลองในหน่วยความจำ (In-Memory State สำหรับ Bot & Web)
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
            "entry": "4086.63",
            "sl": "4112.30",
            "tp1": "4035.29",
            "tp2": "4009.62",
            "rr": "1:3",
            "status": "RUNNING",
            "reason": "ราคาชน Golden Zone 61.8% + Order Block H1 กดดันตามเทรนด์หลัก"
        },
        {
            "id": 100,
            "time": "10:15:00",
            "symbol": "XAUUSD",
            "tf": "15M",
            "direction": "SELL",
            "entry": "4018.65",
            "sl": "4025.84",
            "tp1": "4004.27",
            "tp2": "3997.08",
            "rr": "1:3",
            "status": "TP2 HIT (+2,157 pts)",
            "reason": "ย่อชน Fib 61.8% รอบสั้น ไหลลงตามโครงสร้าง Intraday Bearish"
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
            "time": "19:30",
            "currency": "USD",
            "event": "Unemployment Claims (จำนวนผู้ขอรับสวัสดิการว่างงาน)",
            "impact": "HIGH",
            "forecast": "215K",
            "previous": "212K",
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
    <title>GOLD AI SNIPER PRO — Institutional Trading Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #03060c;
            --bg-card: rgba(13, 20, 36, 0.78);
            --border-subtle: rgba(255, 255, 255, 0.07);
            --gold-glow: rgba(245, 158, 11, 0.25);
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
            background: linear-gradient(145deg, rgba(17, 25, 44, 0.9), rgba(10, 15, 28, 0.95));
            border: 1px solid rgba(245, 158, 11, 0.35);
            box-shadow: 0 20px 50px -15px rgba(245, 158, 11, 0.12), inset 0 1px 0 0 rgba(251, 191, 36, 0.2);
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #03060c; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 9999px; }
        ::-webkit-scrollbar-thumb:hover { background: #f59e0b; }
    </style>
</head>
<body class="antialiased min-h-screen p-3 md:p-5 selection:bg-amber-500 selection:text-slate-950">
    <div class="max-w-[1740px] mx-auto space-y-5">

        <!-- TOP INSTITUTIONAL NAVBAR & NEWS SHIELD STATUS -->
        <header class="pro-card rounded-2xl p-4 lg:px-6 transition-all duration-300">
            <div class="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
                
                <div class="flex items-center gap-4">
                    <div class="relative group">
                        <div class="absolute -inset-1 bg-gradient-to-r from-amber-400 to-yellow-600 rounded-2xl blur opacity-40 group-hover:opacity-75 transition"></div>
                        <div class="relative px-3.5 py-2.5 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 flex flex-col items-center justify-center shadow-xl font-black text-slate-950 shrink-0">
                            <span class="text-[10px] tracking-tighter leading-none opacity-80">AI QUANT</span>
                            <span class="text-lg tracking-tight leading-none font-mono-num">XAU</span>
                        </div>
                    </div>
                    <div>
                        <div class="flex flex-wrap items-center gap-2.5">
                            <h1 class="text-xl md:text-2xl font-black tracking-tight bg-gradient-to-r from-white via-amber-200 to-amber-400 bg-clip-text text-transparent">
                                GOLD AI SNIPER PRO
                            </h1>
                            <span class="px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-full">
                                <i class="fa-solid fa-crosshairs mr-1"></i>FIB 61.8% • SL 78.6% • RR 1:3
                            </span>
                            <span class="px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 rounded-full">
                                <i class="fa-solid fa-bolt mr-1"></i>LINE & DISCORD HUB
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-1 flex items-center gap-2">
                            <span>Institutional Dual-Chart Terminal • ระบบกรองข่าวแรงอัตโนมัติ & ศูนย์กระจายสัญญาณเทรดความเสี่ยงต่ำ</span>
                            <span class="hidden md:inline text-slate-600">|</span>
                            <span id="current-date-label" class="hidden md:inline text-amber-400/90 font-medium"></span>
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
                            <span id="live-ticker-price" class="font-mono-num text-sm md:text-base font-extrabold text-emerald-400">$3,995.80</span>
                        </div>
                        <span class="px-1.5 py-0.5 text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400 rounded border border-emerald-500/30">LIVE</span>
                    </div>
                </div>
            </div>
        </header>

        <!-- KPI METRICS BAR -->
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
                        <span class="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs"><i class="fa-brands fa-discord mr-1"></i>Discord</span>
                        <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs"><i class="fa-brands fa-line mr-1"></i>LINE OA</span>
                        <span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs"><i class="fa-brands fa-python mr-1"></i>MT5</span>
                    </div>
                    <span class="text-[11px] text-emerald-400 mt-1 block"><i class="fa-solid fa-circle-check mr-1"></i>API Endpoint Ready</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 text-lg">
                    <i class="fa-solid fa-tower-broadcast"></i>
                </div>
            </div>
        </section>

        <!-- MAIN WORKSPACE GRID -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- LEFT COLUMN (7 COLS) -->
            <div class="xl:col-span-7 space-y-5">
                
                <!-- 1. DUAL-CHART TERMINAL CARD -->
                <div class="pro-card rounded-2xl p-4 md:p-5 space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3 border-b border-slate-800/80 pb-3.5">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 flex-1">
                            <button onclick="switchChartMode('sniper')" id="mode-btn-sniper" class="py-2.5 px-4 rounded-xl text-xs font-extrabold transition-all flex items-center justify-center gap-2 bg-gradient-to-r from-amber-400 via-amber-500 to-yellow-500 text-slate-950 shadow-lg shadow-amber-500/20">
                                <i class="fa-solid fa-crosshairs"></i>
                                <span>โหมดที่ 1: AI Sniper ตีเส้น 61.8% อัตโนมัติ</span>
                            </button>
                            <button onclick="switchChartMode('tv')" id="mode-btn-tv" class="py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 bg-slate-950/90 text-slate-300 border border-slate-800 hover:border-amber-500/40">
                                <i class="fa-solid fa-chart-line"></i>
                                <span>โหมดที่ 2: TradingView Studio (ตีกราฟเอง)</span>
                            </button>
                        </div>

                        <div class="flex items-center justify-between sm:justify-end gap-2">
                            <button onclick="resetSniperZoom()" class="px-3 py-2 rounded-xl bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-300 text-xs font-semibold transition flex items-center gap-1.5">
                                <i class="fa-solid fa-expand text-amber-400"></i> รีเซ็ตมุมมอง
                            </button>
                            <span id="chart-tf-indicator" class="px-3.5 py-2 rounded-xl bg-amber-500/10 border border-amber-500/40 text-amber-300 text-xs font-black font-mono-num">
                                TF: 1H
                            </span>
                        </div>
                    </div>

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

                    <div id="sniper-chart-wrapper" class="space-y-2">
                        <div class="flex flex-wrap justify-between items-center text-[11px] text-slate-400 px-1">
                            <span><i class="fa-solid fa-wand-magic-sparkles text-amber-400 mr-1"></i><strong>AI Auto-Plot:</strong> ขีดเส้น Entry 61.8%, SL 78.6%, TP1 (1:2) และ TP2 (1:3) อัตโนมัติตามโครงสร้างสวิง</span>
                            <span class="text-slate-500">เลื่อนลูกกลิ้งเมาส์เพื่อซูมกราฟ</span>
                        </div>
                        <div id="sniper-lw-chart" class="w-full h-[520px] rounded-xl overflow-hidden border border-slate-800/90 bg-[#050912]"></div>
                    </div>

                    <div id="tv-chart-wrapper" class="hidden space-y-2">
                        <div class="flex flex-wrap justify-between items-center text-[11px] text-amber-300 px-1">
                            <span><i class="fa-solid fa-compass-drafting mr-1"></i><strong>TradingView Studio:</strong> ใช้แถบเครื่องมือซ้ายมือเพื่อวาด Fibonacci Retracement หรือ Order Block เพิ่มเติมได้เต็มรูปแบบ</span>
                        </div>
                        <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800" style="height:520px; width:100%;">
                            <div id="tradingview_studio_chart" style="height:100%; width:100%;"></div>
                        </div>
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

            <!-- RIGHT COLUMN (5 COLS) -->
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
                            <span class="text-[10px] text-slate-400 block">โครงสร้างตลาด (Structure)</span>
                            <span id="tf-structure-badge" class="inline-block mt-1 px-2 py-0.5 rounded text-[11px] font-bold">--</span>
                        </div>
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">ความผันผวน (Volatility)</span>
                            <span id="tf-volatility" class="block mt-1 font-bold text-slate-200 text-[11px]">--</span>
                        </div>
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">คำแนะนำหน้าเทรด (AI Bias)</span>
                            <span id="tf-bias-text" class="block mt-1 font-extrabold text-[11px]">--</span>
                        </div>
                    </div>
                </div>

                <!-- 2. GOLDEN ZONE SNIPER SETUP CARD + ONE-CLICK DISPATCH -->
                <div class="pro-card-gold rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800/80 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-amber-400 block">STEP 2 • GOLDEN ZONE SNIPER & BROADCAST</span>
                            <h2 class="text-lg font-black text-white">แผนจุดเข้าเทรด 61.8% & ส่งสัญญาณหาลูกค้า</h2>
                        </div>
                        <span id="setup-order-badge" class="px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num">--</span>
                    </div>

                    <div id="sideway-warning" class="hidden bg-amber-500/15 border border-amber-500/50 rounded-xl p-3 text-xs text-amber-200 flex items-start gap-2.5">
                        <i class="fa-solid fa-triangle-exclamation text-amber-400 text-base mt-0.5"></i>
                        <div>
                            <div class="font-extrabold text-amber-300">ตลาดกำลังสะสมพลัง (Sideway) ในไทม์เฟรมนี้!</div>
                            <p class="text-[11px] mt-0.5">แนะนำให้ <strong>"นั่งทับมือ"</strong> หรือสลับไปใช้แผนของไทม์เฟรม <strong>15M / 1H / 4H</strong> เพื่อความแม่นยำสูงสุด</p>
                        </div>
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
                            <p class="text-[11px] text-slate-400 mt-0.5">จุดตั้ง Pending Order ไม้เดียวเน้นๆ</p>
                        </div>

                        <div class="bg-gradient-to-br from-rose-950/50 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-rose-500/40">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-rose-300">🔴 STOP LOSS (78.6%)</span>
                                <span id="val-risk-pts" class="text-[10px] font-mono-num bg-rose-500/20 text-rose-300 px-2 py-0.5 rounded font-bold">Risk: --</span>
                            </div>
                            <div id="val-sl" class="text-2xl font-black font-mono-num text-rose-400 mt-1">--</div>
                            <p class="text-[11px] text-slate-400 mt-0.5">จุดยอมแพ้หากหลุดโครงสร้างสวิง</p>
                        </div>

                        <div class="bg-gradient-to-br from-emerald-950/50 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-emerald-500/40">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-emerald-300">🟢 TAKE PROFIT 1 (1:2)</span>
                                <span id="val-tp1-pts" class="text-[10px] font-mono-num bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp1" class="text-2xl font-black font-mono-num text-emerald-400 mt-1">--</div>
                            <p class="text-[11px] text-slate-400 mt-0.5">แบ่งปิดทำกำไร 50% และบังหน้าทุน</p>
                        </div>

                        <div class="bg-gradient-to-br from-amber-950/50 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-amber-500/50">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-amber-300">🟡 TAKE PROFIT 2 (1:3)</span>
                                <span id="val-tp2-pts" class="text-[10px] font-mono-num bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp2" class="text-2xl font-black font-mono-num text-amber-400 mt-1">--</div>
                            <p class="text-[11px] text-slate-400 mt-0.5">เป้าหมายหลัก (Sniper Target 1:3)</p>
                        </div>
                    </div>

                    <div class="space-y-1">
                        <span class="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                            <i class="fa-solid fa-microchip"></i> เหตุผลประกอบสัญญาณจาก AI (ส่งแนบไปกับ LINE & Discord):
                        </span>
                        <textarea id="setup-reason" rows="2" class="w-full text-xs text-slate-200 bg-slate-950/90 p-3 rounded-xl border border-slate-800 focus:border-amber-500 outline-none leading-relaxed"></textarea>
                    </div>

                    <div id="dispatch-lock-warning" class="hidden p-3 rounded-xl bg-rose-500/20 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2.5">
                        <i class="fa-solid fa-ban text-rose-400 text-base"></i>
                        <span><strong>ระบบล็อกการส่งสัญญาณชั่วคราว!</strong> ขณะนี้อยู่ในโหมดเฝ้าระวังข่าวแรง (High Impact News Shield) เพื่อความปลอดภัยของพอร์ตลูกค้า</span>
                    </div>

                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="w-full py-3.5 px-4 rounded-xl font-extrabold text-xs md:text-sm bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 shadow-xl shadow-emerald-500/20 transition flex items-center justify-center gap-2">
                        <i class="fa-solid fa-satellite-dish"></i>
                        <span>ยิงสัญญาณชุดนี้เข้า LINE OA • Discord • Python Bot ทันที</span>
                    </button>
                </div>

                <!-- 3. CUSTOM SWING TUNER -->
                <div class="pro-card rounded-2xl p-5 space-y-3">
                    <div class="flex justify-between items-center border-b border-slate-800/80 pb-2.5">
                        <div>
                            <h3 class="text-sm font-bold text-amber-400"><i class="fa-solid fa-sliders mr-1.5"></i>ปรับจุด Swing High / Low เอง (Custom Fib Tuner)</h3>
                            <p class="text-[11px] text-slate-400">ใส่ราคา High/Low ที่คุณมองเห็น เส้นบนกราฟและจุดเข้า 61.8% จะคำนวณใหม่ทันที</p>
                        </div>
                    </div>

                    <div class="grid grid-cols-3 gap-2.5 text-xs">
                        <div>
                            <label class="text-slate-400 block mb-1 text-[11px]">ฝั่งคำสั่ง (Bias)</label>
                            <select id="custom-dir" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-slate-100 font-bold">
                                <option value="SELL">🔻 SELL (ดักเด้ง)</option>
                                <option value="BUY">🟢 BUY (ดักย่อ)</option>
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
                        <i class="fa-solid fa-rotate mr-1"></i> คำนวณจุดเข้า 61.8% ใหม่และวาดเส้นบนกราฟทันที
                    </button>
                </div>

                <!-- 4. LIVE SIGNAL FEED & MULTI-TIMEFRAME MATRIX TABS -->
                <div class="pro-card rounded-2xl p-5 space-y-3.5">
                    <div class="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
                        <div class="flex gap-2">
                            <button onclick="switchRightTab('feed')" id="tab-btn-feed" class="px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950 transition">
                                <i class="fa-solid fa-bolt mr-1"></i>Live Signal Feed
                            </button>
                            <button onclick="switchRightTab('matrix')" id="tab-btn-matrix" class="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200 transition">
                                <i class="fa-solid fa-table-cells mr-1"></i>ตารางสรุปทุก TF
                            </button>
                        </div>
                        <span class="text-[11px] text-slate-400 font-mono-num" id="feed-counter-label">2 รายการล่าสุด</span>
                    </div>

                    <div id="right-tab-feed" class="space-y-2.5 max-h-[290px] overflow-y-auto pr-1"></div>
                    <div id="right-tab-matrix" class="hidden space-y-2 max-h-[290px] overflow-y-auto pr-1">
                        <div id="matrix-overview-list" class="space-y-2 text-xs"></div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-emerald-500 text-slate-950 px-4 py-3 rounded-xl font-extrabold text-xs shadow-2xl z-50 flex items-center gap-2">
        <i class="fa-solid fa-circle-check text-base"></i>
        <span id="toast-notify-text">ดำเนินการสำเร็จ!</span>
    </div>

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
            '1m': {
                label: '1 นาที (1M)', tvInterval: '1', stepSec: 60,
                calcDir: 'SELL', swingHigh: 4001.20, swingLow: 3992.20, currentPrice: 3995.80,
                structure: 'ไซด์เวย์กรอบแคบ (Sideway)',
                structureClass: 'bg-amber-500/20 text-amber-300 border border-amber-500/40',
                volatility: 'แกว่งตัวสะสมพลัง',
                biasText: '🟡 WAIT / NO TRADE', biasColor: 'text-amber-400',
                isSideway: true,
                reason: 'TF 1M กราฟวิ่งออกข้างในกรอบแคบ เสี่ยงโดนกวาด Stop Loss แนะนำให้รอเข้าที่ TF 15M หรือ 1H แทน'
            },
            '5m': {
                label: '5 นาที (5M)', tvInterval: '5', stepSec: 300,
                calcDir: 'SELL', swingHigh: 4016.00, swingLow: 3992.20, currentPrice: 3995.80,
                structure: 'ขาลงระยะสั้น (Minor Bearish)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ปานกลาง (Scalping)',
                biasText: '🔴 SELL LIMIT @ 61.8%', biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'TF 5M ทำโครงสร้าง Lower Low ชัดเจน ดัก Sell Limit ที่โซน 61.8% ($4,006.91) วาง SL ที่ 78.6% ($4,010.91) เป้า RR 1:3'
            },
            '15m': {
                label: '15 นาที (15M)', tvInterval: '15', stepSec: 900,
                calcDir: 'SELL', swingHigh: 4035.00, swingLow: 3992.20, currentPrice: 3995.80,
                structure: 'เทรนด์ขาลงระหว่างวัน (Intraday Bearish)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'เสถียร (แนะนำ Day Trade)',
                biasText: '🔴 SELL LIMIT @ 61.8%', biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'TF 15M ทุบหลุดแนวรับสำคัญ รอราคารีบาวด์ขึ้นมาทดสอบ Fib 61.8% ($4,018.65) ค่อยเปิด Sell เน้นๆ'
            },
            '1h': {
                label: '1 ชั่วโมง (1H)', tvInterval: '60', stepSec: 3600,
                calcDir: 'SELL', swingHigh: 4145.00, swingLow: 3992.20, currentPrice: 3995.80,
                structure: 'ขาลงหลัก (Major Bearish Orderflow)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'แม่นยำสูง (High Probability)',
                biasText: '🔴 STRONG SELL @ 61.8%', biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'TF 1H ทิ้งตัวลงมาจาก Swing High $4,145.00 ลงมาทำ Low ที่ $3,992.20 โซน Golden Zone 61.8% ($4,086.63) ทับซ้อนกับ Order Block พอดี'
            },
            '4h': {
                label: '4 ชั่วโมง (4H)', tvInterval: '240', stepSec: 14400,
                calcDir: 'SELL', swingHigh: 4210.00, swingLow: 3992.20, currentPrice: 3995.80,
                structure: 'ขาลงภาพใหญ่ (Macro Downtrend)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'สวิงเทรด (Swing Trade)',
                biasText: '🔴 MACRO SELL @ 61.8%', biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ภาพใหญ่ 4H แรงขายคุมตลาดสมบูรณ์ ดัก Sell รอบใหญ่ที่ 61.8% ($4,126.80) SL ที่ 78.6% ($4,163.39) ลุ้นรันเทรนด์ RR 1:3'
            },
            'daily': {
                label: 'รายวัน (Daily)', tvInterval: 'D', stepSec: 86400,
                calcDir: 'SELL', swingHigh: 4240.00, swingLow: 3992.20, currentPrice: 3995.80,
                structure: 'ปรับฐานรายวัน (Daily Correction)',
                structureClass: 'bg-amber-500/20 text-amber-300 border border-amber-500/40',
                volatility: 'ระดับมหภาค (Position)',
                biasText: '🔴 SELL BIAS ตามแท่ง Day', biasColor: 'text-amber-400',
                isSideway: false,
                reason: 'กราฟ Day พักฐานลงมาจากยอด $4,240.00 กลยุทธ์ที่ปลอดภัยที่สุดคือการดัก Sell ตามแนว Fib 61.8% และเลี่ยงช่วงข่าวแดง'
            }
        };

        let lwChart = null;
        let candleSeries = null;
        let activePriceLines = [];
        let currentChartMode = 'sniper';
        let currentTfKey = '1h';
        let currentTvLoadedInterval = null;
        let isNewsLocked = false;

        function initLightweightChart() {
            const container = document.getElementById('sniper-lw-chart');
            container.innerHTML = '';

            lwChart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 520,
                layout: {
                    background: { type: 'solid', color: '#050912' },
                    textColor: '#94a3b8',
                    fontFamily: 'JetBrains Mono, Prompt, sans-serif'
                },
                grid: {
                    vertLines: { color: 'rgba(30, 41, 59, 0.45)' },
                    horzLines: { color: 'rgba(30, 41, 59, 0.45)' }
                },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                rightPriceScale: {
                    borderColor: '#1e293b',
                    autoScale: true,
                    scaleMargins: { top: 0.08, bottom: 0.08 }
                },
                timeScale: {
                    borderColor: '#1e293b',
                    timeVisible: true,
                    secondsVisible: false
                }
            });

            candleSeries = lwChart.addCandlestickSeries({
                upColor: '#10b981', downColor: '#f43f5e',
                borderUpColor: '#10b981', borderDownColor: '#f43f5e',
                wickUpColor: '#10b981', wickDownColor: '#f43f5e'
            });

            window.addEventListener('resize', () => {
                if (lwChart && container.clientWidth > 0) {
                    lwChart.applyOptions({ width: container.clientWidth });
                }
            });
        }

        function generateStructureCandles(direction, swingHigh, swingLow, currentPrice, stepSec) {
            const candles = [];
            const totalBars = 75;
            const nowSec = Math.floor(Date.now() / 1000) - (totalBars * stepSec);
            const range = swingHigh - swingLow;

            let waypoints;
            if (direction === 'SELL') {
                waypoints = [
                    { idx: 0, price: swingHigh - range * 0.25 },
                    { idx: 12, price: swingHigh },
                    { idx: 28, price: swingLow + range * 0.45 },
                    { idx: 36, price: swingLow + range * 0.60 },
                    { idx: 56, price: swingLow },
                    { idx: 68, price: currentPrice + range * 0.08 },
                    { idx: 74, price: currentPrice }
                ];
            } else {
                waypoints = [
                    { idx: 0, price: swingLow + range * 0.25 },
                    { idx: 12, price: swingLow },
                    { idx: 32, price: swingHigh - range * 0.35 },
                    { idx: 52, price: swingHigh },
                    { idx: 66, price: swingHigh - range * 0.45 },
                    { idx: 74, price: currentPrice }
                ];
            }

            let prevClose = waypoints[0].price;

            for (let i = 0; i < totalBars; i++) {
                let wpStart = waypoints[0], wpEnd = waypoints[waypoints.length - 1];
                for (let w = 0; w < waypoints.length - 1; w++) {
                    if (i >= waypoints[w].idx && i <= waypoints[w + 1].idx) {
                        wpStart = waypoints[w];
                        wpEnd = waypoints[w + 1];
                        break;
                    }
                }

                const progress = (i - wpStart.idx) / Math.max(1, (wpEnd.idx - wpStart.idx));
                const targetBase = wpStart.price + (wpEnd.price - wpStart.price) * progress;

                const wave = Math.sin(i * 1.4) * (range * 0.025);
                let close = targetBase + wave;
                if (i === 12 && direction === 'SELL') close = swingHigh - (range * 0.01);
                if (i === 56 && direction === 'SELL') close = swingLow + (range * 0.01);
                if (i === totalBars - 1) close = currentPrice;

                const open = prevClose;
                let high = Math.max(open, close) + Math.abs(Math.cos(i * 0.9)) * (range * 0.022);
                let low = Math.min(open, close) - Math.abs(Math.sin(i * 1.1)) * (range * 0.022);

                if (i === 12 && direction === 'SELL') high = swingHigh;
                if (i === 56 && direction === 'SELL') low = swingLow;

                candles.push({
                    time: nowSec + (i * stepSec),
                    open: parseFloat(open.toFixed(2)),
                    high: parseFloat(high.toFixed(2)),
                    low: parseFloat(low.toFixed(2)),
                    close: parseFloat(close.toFixed(2))
                });

                prevClose = close;
            }
            return candles;
        }

        function drawSniperLinesOnChart(direction, swingHigh, swingLow, currentPrice, stepSec, mathRes) {
            if (!lwChart || !candleSeries) initLightweightChart();

            activePriceLines.forEach(line => {
                try { candleSeries.removePriceLine(line); } catch (e) {}
            });
            activePriceLines = [];

            const candles = generateStructureCandles(direction, swingHigh, swingLow, currentPrice, stepSec);
            candleSeries.setData(candles);

            const lineEntry = candleSeries.createPriceLine({
                price: mathRes.entryNum, color: '#06b6d4', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true,
                title: `🎯 ENTRY 61.8% (${direction})`
            });
            const lineSL = candleSeries.createPriceLine({
                price: mathRes.slNum, color: '#f43f5e', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true,
                title: `🛑 SL 78.6%`
            });
            const lineTP1 = candleSeries.createPriceLine({
                price: mathRes.tp1Num, color: '#10b981', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true,
                title: `💰 TP1 (RR 1:2)`
            });
            const lineTP2 = candleSeries.createPriceLine({
                price: mathRes.tp2Num, color: '#f59e0b', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true,
                title: `🚀 TP2 TARGET (RR 1:3)`
            });
            const lineHigh = candleSeries.createPriceLine({
                price: swingHigh, color: '#475569', lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true,
                title: `Swing High`
            });
            const lineLow = candleSeries.createPriceLine({
                price: swingLow, color: '#475569', lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true,
                title: `Swing Low`
            });

            activePriceLines.push(lineEntry, lineSL, lineTP1, lineTP2, lineHigh, lineLow);

            candleSeries.applyOptions({
                autoscaleInfoProvider: () => ({
                    priceRange: {
                        minValue: Math.min(swingLow, mathRes.tp2Num, mathRes.slNum) - 5,
                        maxValue: Math.max(swingHigh, mathRes.tp2Num, mathRes.slNum) + 5
                    }
                })
            });

            lwChart.timeScale().fitContent();
        }

        function resetSniperZoom() {
            if (lwChart) lwChart.timeScale().fitContent();
        }

        function switchChartMode(mode) {
            currentChartMode = mode;
            const sniperWrap = document.getElementById('sniper-chart-wrapper');
            const tvWrap = document.getElementById('tv-chart-wrapper');
            const btnSniper = document.getElementById('mode-btn-sniper');
            const btnTv = document.getElementById('mode-btn-tv');

            if (mode === 'sniper') {
                sniperWrap.classList.remove('hidden');
                tvWrap.classList.add('hidden');
                btnSniper.className = "py-2.5 px-4 rounded-xl text-xs font-extrabold transition-all flex items-center justify-center gap-2 bg-gradient-to-r from-amber-400 via-amber-500 to-yellow-500 text-slate-950 shadow-lg shadow-amber-500/20";
                btnTv.className = "py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 bg-slate-950/90 text-slate-300 border border-slate-800 hover:border-amber-500/40";
                setTimeout(() => {
                    if (lwChart) {
                        const container = document.getElementById('sniper-lw-chart');
                        lwChart.applyOptions({ width: container.clientWidth });
                        lwChart.timeScale().fitContent();
                    }
                }, 50);
            } else {
                sniperWrap.classList.add('hidden');
                tvWrap.classList.remove('hidden');
                btnTv.className = "py-2.5 px-4 rounded-xl text-xs font-extrabold transition-all flex items-center justify-center gap-2 bg-gradient-to-r from-amber-400 via-amber-500 to-yellow-500 text-slate-950 shadow-lg shadow-amber-500/20";
                btnSniper.className = "py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 bg-slate-950/90 text-slate-300 border border-slate-800 hover:border-amber-500/40";
                const cfg = timeframeConfigs[currentTfKey];
                loadTradingViewStudio(cfg.tvInterval);
            }
        }

        function loadTradingViewStudio(intervalCode) {
            if (currentTvLoadedInterval === intervalCode) return;
            currentTvLoadedInterval = intervalCode;
            const container = document.getElementById('tradingview_studio_chart');
            container.innerHTML = '';
            new TradingView.widget({
                "width": "100%", "height": "520", "symbol": "OANDA:XAUUSD",
                "interval": intervalCode, "timezone": "Asia/Bangkok",
                "theme": "dark", "style": "1", "locale": "th",
                "toolbar_bg": "#050912", "enable_publishing": false,
                "hide_side_toolbar": false, "allow_symbol_change": true,
                "studies": ["RSI@tv-basicstudies"],
                "container_id": "tradingview_studio_chart"
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
                btnMatrix.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200 transition";
            } else {
                feedBox.classList.add('hidden');
                matrixBox.classList.remove('hidden');
                btnMatrix.className = "px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950 transition";
                btnFeed.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200 transition";
            }
        }

        function updateDashboardAndChart(calcDir, swingHigh, swingLow, cfg) {
            const mathRes = calculateSniperMath(calcDir, swingHigh, swingLow);

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
            document.getElementById('setup-swing-info').innerText = `High $${swingHigh.toFixed(2)} ➔ Low $${swingLow.toFixed(2)}`;

            const orderBadge = document.getElementById('setup-order-badge');
            if (cfg && cfg.isSideway) {
                orderBadge.innerText = '⏸️ NO TRADE (SIDEWAY)';
                orderBadge.className = 'px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num bg-amber-500 text-slate-950';
            } else if (calcDir === 'SELL') {
                orderBadge.innerText = '🔻 SELL LIMIT @ 61.8%';
                orderBadge.className = 'px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num bg-rose-500 text-white shadow-lg shadow-rose-500/30';
            } else {
                orderBadge.innerText = '🟢 BUY LIMIT @ 61.8%';
                orderBadge.className = 'px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num bg-emerald-500 text-slate-950 shadow-lg shadow-emerald-500/30';
            }

            const stepSec = cfg ? cfg.stepSec : 3600;
            const curPrice = cfg ? cfg.currentPrice : ((swingHigh + swingLow) / 2);
            drawSniperLinesOnChart(calcDir, swingHigh, swingLow, curPrice, stepSec, mathRes);
        }

        function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const cfg = timeframeConfigs[tfKey];
            if (!cfg) return;

            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num bg-slate-950 text-slate-400 border border-slate-800 hover:border-amber-500/40 hover:text-slate-200 transition";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn py-2.5 px-2 rounded-xl text-xs font-extrabold font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 border border-amber-300 shadow-lg shadow-amber-500/20 transition";
            }

            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            document.getElementById('chart-tf-indicator').innerText = 'TF: ' + tfKey.toUpperCase();

            const structEl = document.getElementById('tf-structure-badge');
            structEl.innerText = cfg.structure;
            structEl.className = 'inline-block mt-1 px-2 py-0.5 rounded text-[11px] font-bold ' + cfg.structureClass;

            document.getElementById('tf-volatility').innerText = cfg.volatility;

            const biasEl = document.getElementById('tf-bias-text');
            biasEl.innerText = cfg.biasText;
            biasEl.className = 'block mt-1 font-extrabold text-[11px] ' + cfg.biasColor;

            const warnEl = document.getElementById('sideway-warning');
            if (cfg.isSideway) warnEl.classList.remove('hidden');
            else warnEl.classList.add('hidden');

            document.getElementById('setup-reason').value = cfg.reason;
            document.getElementById('custom-dir').value = cfg.calcDir;
            document.getElementById('custom-high').value = cfg.swingHigh;
            document.getElementById('custom-low').value = cfg.swingLow;

            updateDashboardAndChart(cfg.calcDir, cfg.swingHigh, cfg.swingLow, cfg);

            if (currentChartMode === 'tv') {
                loadTradingViewStudio(cfg.tvInterval);
            }
            renderMatrixTable(tfKey);
        }

        function applyCustomSwing() {
            const dir = document.getElementById('custom-dir').value;
            const high = parseFloat(document.getElementById('custom-high').value) || 4145;
            const low = parseFloat(document.getElementById('custom-low').value) || 3992;

            if (high <= low) {
                showToast('⚠️ กรุณากรอก Swing High ให้มากกว่า Swing Low');
                return;
            }

            const baseCfg = timeframeConfigs[currentTfKey];
            updateDashboardAndChart(dir, high, low, {
                isSideway: false,
                stepSec: baseCfg.stepSec,
                currentPrice: (high + low) / 2
            });

            document.getElementById('setup-reason').value = `Custom Sniper Setup (${dir} @ TF ${currentTfKey.toUpperCase()}): ดักเข้าที่ Golden Zone 61.8% วาง SL ที่ 78.6% เป้าทำกำไร RR 1:2 และ 1:3`;
            if (currentChartMode !== 'sniper') switchChartMode('sniper');
            showToast('✅ คำนวณจุดเข้า 61.8% และตีเส้นบนกราฟใหม่เรียบร้อย!');
        }

        function renderMatrixTable(activeKey) {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';

            Object.keys(timeframeConfigs).forEach(key => {
                const item = timeframeConfigs[key];
                const lvls = calculateSniperMath(item.calcDir, item.swingHigh, item.swingLow);
                const isSelected = key === activeKey;

                const row = document.createElement('div');
                row.className = `flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-xl border cursor-pointer transition gap-2 ${
                    isSelected ? 'bg-amber-500/15 border-amber-500/60' : 'bg-slate-950/90 border-slate-800 hover:border-slate-700'
                }`;
                row.onclick = () => selectTimeframe(key);
                row.innerHTML = `
                    <div class="flex items-center gap-2.5">
                        <span class="font-black font-mono-num text-amber-400 w-12 uppercase">${key}</span>
                        <span class="px-2 py-0.5 rounded text-[10px] font-bold ${item.structureClass}">${item.structure}</span>
                    </div>
                    <div class="flex items-center gap-3 text-[11px] font-mono-num">
                        <span class="text-cyan-400 font-bold">61.8%: $${lvls.entry}</span>
                        <span class="text-rose-400 font-bold">SL: $${lvls.sl}</span>
                        <span class="text-amber-400 font-bold">TP2: $${lvls.tp2}</span>
                    </div>
                `;
                list.appendChild(row);
            });
        }

        async function loadSystemState() {
            try {
                const res = await fetch('/api/system-state');
                const data = await res.json();
                isNewsLocked = data.news_locked;
                updateNewsShieldUI(isNewsLocked);
                renderCalendarTable(data.economic_calendar);
                renderSignalFeed(data.signal_history);
            } catch (e) {
                console.error(e);
            }
        }

        function updateNewsShieldUI(locked) {
            const box = document.getElementById('news-shield-box');
            const dot = document.getElementById('shield-dot');
            const text = document.getElementById('shield-status-text');
            const warn = document.getElementById('dispatch-lock-warning');
            const btn = document.getElementById('broadcast-btn');

            if (locked) {
                box.className = "bg-rose-950/60 border border-rose-500/60 px-3.5 py-2 rounded-xl flex items-center gap-3 transition-all";
                dot.className = "w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping";
                text.className = "text-xs font-extrabold text-rose-400";
                text.innerText = "NEWS LOCKED (งดส่งสัญญาณช่วงข่าวแดง)";
                warn.classList.remove('hidden');
                btn.disabled = true;
                btn.className = "w-full py-3.5 px-4 rounded-xl font-extrabold text-xs md:text-sm bg-slate-800 text-slate-500 cursor-not-allowed flex items-center justify-center gap-2";
            } else {
                box.className = "bg-emerald-950/40 border border-emerald-500/40 px-3.5 py-2 rounded-xl flex items-center gap-3 transition-all";
                dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping";
                text.className = "text-xs font-extrabold text-emerald-400";
                text.innerText = "SAFE MODE (เปิดรับสัญญาณปกติ)";
                warn.classList.add('hidden');
                btn.disabled = false;
                btn.className = "w-full py-3.5 px-4 rounded-xl font-extrabold text-xs md:text-sm bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 shadow-xl shadow-emerald-500/20 transition flex items-center justify-center gap-2";
            }
        }

        async function toggleNewsLock() {
            try {
                const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
                const data = await res.json();
                isNewsLocked = data.news_locked;
                updateNewsShieldUI(isNewsLocked);
                showToast(isNewsLocked ? '🛡️ เปิดโหมดล็อกสัญญาณช่วงข่าวแรงแล้ว!' : '✅ ปลดล็อกระบบ เปิดส่งสัญญาณตามปกติ');
            } catch (e) {}
        }

        function renderCalendarTable(items) {
            const tbody = document.getElementById('economic-calendar-body');
            tbody.innerHTML = '';
            items.forEach(item => {
                let badge = '';
                let statusBadge = '';
                if (item.impact === 'HIGH') {
                    badge = '<span class="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/40 font-bold text-[10px]">🔴 ข่าวแดง (High)</span>';
                    statusBadge = `<span class="text-rose-400 font-bold"><i class="fa-solid fa-lock mr-1"></i>${item.status}</span>`;
                } else if (item.impact === 'MEDIUM') {
                    badge = '<span class="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold text-[10px]">🟠 ปานกลาง (Med)</span>';
                    statusBadge = `<span class="text-amber-300 font-semibold"><i class="fa-solid fa-triangle-exclamation mr-1"></i>${item.status}</span>`;
                } else {
                    badge = '<span class="px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-300 font-bold text-[10px]">🟡 ทั่วไป (Low)</span>';
                    statusBadge = `<span class="text-emerald-400 font-semibold"><i class="fa-solid fa-check mr-1"></i>${item.status}</span>`;
                }

                const tr = document.createElement('tr');
                tr.className = "hover:bg-slate-900/50 transition";
                tr.innerHTML = `
                    <td class="py-3 px-2 font-mono-num font-bold text-slate-200">${item.time}</td>
                    <td class="py-3 px-2"><span class="px-2 py-0.5 bg-blue-500/15 text-blue-300 border border-blue-500/30 rounded font-mono-num font-bold text-[10px]">${item.currency}</span></td>
                    <td class="py-3 px-2 font-semibold text-slate-100">${item.event}</td>
                    <td class="py-3 px-2">${badge}</td>
                    <td class="py-3 px-2 font-mono-num text-slate-400">${item.forecast} / ${item.previous}</td>
                    <td class="py-3 px-2 text-right font-mono-num text-[11px]">${statusBadge}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        async function addNewsItem() {
            const time = document.getElementById('new-news-time').value || '20:30';
            const event = document.getElementById('new-news-Event').value;
            const impact = document.getElementById('new-news-impact').value;
            if (!event) {
                showToast('⚠️ กรุณาระบุชื่อข่าวเศรษฐกิจ');
                return;
            }
            const res = await fetch('/api/add-news', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ time, event, impact })
            });
            const data = await res.json();
            renderCalendarTable(data.economic_calendar);
            document.getElementById('add-news-modal').classList.add('hidden');
            document.getElementById('new-news-Event').value = '';
            showToast('✅ เพิ่มตารางข่าวเศรษฐกิจเรียบร้อย!');
        }

        function renderSignalFeed(signals) {
            const container = document.getElementById('right-tab-feed');
            document.getElementById('feed-counter-label').innerText = `${signals.length} สัญญาณล่าสุด`;
            container.innerHTML = '';

            signals.forEach(sig => {
                const isSell = sig.direction === 'SELL';
                const borderCol = isSell ? 'border-rose-500' : 'border-emerald-500';
                const dirBadge = isSell
                    ? '<span class="px-2 py-0.5 bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded text-[10px] font-black">🔻 SELL 61.8%</span>'
                    : '<span class="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded text-[10px] font-black">🟢 BUY 61.8%</span>';

                const card = document.createElement('div');
                card.className = `p-3.5 rounded-xl bg-slate-950/90 border border-slate-800/90 border-l-4 ${borderCol} space-y-1.5`;
                card.innerHTML = `
                    <div class="flex justify-between items-center">
                        <div class="flex items-center gap-2">
                            <span class="font-black font-mono-num text-white text-sm">${sig.symbol}</span>
                            ${dirBadge}
                            <span class="text-[11px] font-mono-num text-amber-400 font-bold">TF ${sig.tf}</span>
                        </div>
                        <span class="text-[10px] font-mono-num text-slate-400"><i class="fa-regular fa-clock mr-1"></i>${sig.time}</span>
                    </div>
                    <div class="grid grid-cols-4 gap-1.5 pt-1 text-[11px] font-mono-num">
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">ENTRY</span><span class="text-cyan-400 font-bold">$${sig.entry}</span></div>
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">SL (78.6%)</span><span class="text-rose-400 font-bold">$${sig.sl}</span></div>
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">TP1 (1:2)</span><span class="text-emerald-400 font-bold">$${sig.tp1}</span></div>
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">TP2 (1:3)</span><span class="text-amber-400 font-bold">$${sig.tp2}</span></div>
                    </div>
                    <div class="flex justify-between items-center pt-1 text-[11px]">
                        <span class="text-slate-400 truncate max-w-[70%]">${sig.reason}</span>
                        <span class="px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 font-mono-num text-[10px] font-bold">${sig.status}</span>
                    </div>
                `;
                container.appendChild(card);
            });
        }

        async function broadcastCurrentSignal() {
            if (isNewsLocked) {
                showToast('🛑 ระบบล็อกอยู่เนื่องจากอยู่ในช่วงข่าวแรง!');
                return;
            }

            const payload = {
                symbol: 'XAUUSD',
                tf: currentTfKey.toUpperCase(),
                direction: document.getElementById('custom-dir').value,
                entry: document.getElementById('val-entry').innerText.replace('$', ''),
                sl: document.getElementById('val-sl').innerText.replace('$', ''),
                tp1: document.getElementById('val-tp1').innerText.replace('$', ''),
                tp2: document.getElementById('val-tp2').innerText.replace('$', ''),
                reason: document.getElementById('setup-reason').value
            };

            const res = await fetch('/api/send-signal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                const data = await res.json();
                renderSignalFeed(data.signal_history);
                switchRightTab('feed');
                showToast('🚀 กระจายสัญญาณเข้า LINE OA, Discord และ Bot เรียบร้อย!');
            } else {
                const err = await res.json();
                showToast('⚠️ ' + (err.message || 'ไม่สามารถส่งสัญญาณได้'));
            }
        }

        function copyPrice(elementId) {
            const text = document.getElementById(elementId).innerText.replace('$', '');
            navigator.clipboard.writeText(text);
            showToast(`✅ คัดลอกราคา $${text} เรียบร้อย!`);
        }

        function showToast(msg) {
            const toast = document.getElementById('toast-notify');
            document.getElementById('toast-notify-text').innerText = msg;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 2600);
        }

        setInterval(() => {
            const el = document.getElementById('live-ticker-price');
            const base = 3995.80;
            const jitter = (Math.random() - 0.5) * 1.4;
            const price = (base + jitter).toFixed(2);
            el.innerText = '$' + price.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",");
        }, 2500);

        window.addEventListener('DOMContentLoaded', () => {
            const now = new Date();
            document.getElementById('current-date-label').innerText = 'อัปเดตล่าสุด: ' + now.toLocaleDateString('th-TH', {
                year: 'numeric', month: 'short', day: 'numeric'
            });
            initLightweightChart();
            selectTimeframe('1h');
            loadSystemState();
        });
    </script>
</body>
</html>
"""

# ==============================================================================
# BACKEND API ENDPOINTS (ใช้ urllib.request ในตัว Python ไม่ต้องลง requests เพิ่ม)
# ==============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/system-state', methods=['GET'])
def get_system_state():
    return jsonify({
        "safe_to_trade": not SYSTEM_STATE["news_locked"],
        "news_locked": SYSTEM_STATE["news_locked"],
        "lock_reason": SYSTEM_STATE["lock_reason"],
        "latest_signal": SYSTEM_STATE["latest_signal"],
        "signal_history": SYSTEM_STATE["signal_history"],
        "economic_calendar": SYSTEM_STATE["economic_calendar"],
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/api/toggle-news-lock', methods=['POST'])
def toggle_news_lock():
    SYSTEM_STATE["news_locked"] = not SYSTEM_STATE["news_locked"]
    SYSTEM_STATE["lock_reason"] = (
        "งดเทรดชั่วคราวเนื่องจากมีข่าวเศรษฐกิจความรุนแรงสูง (High Impact News)"
        if SYSTEM_STATE["news_locked"]
        else "ตลาดปกติ (Normal Market Conditions)"
    )
    return jsonify({
        "status": "ok",
        "news_locked": SYSTEM_STATE["news_locked"],
        "lock_reason": SYSTEM_STATE["lock_reason"]
    })

@app.route('/api/add-news', methods=['POST'])
def add_news():
    data = request.json or {}
    impact = data.get("impact", "HIGH")
    status_map = {
        "HIGH": "AUTO-LOCK ±30 MIN",
        "MEDIUM": "REDUCE LOT 50%",
        "LOW": "NORMAL TRADE"
    }
    new_item = {
        "time": data.get("time", "20:30"),
        "currency": "USD",
        "event": data.get("event", "Economic Event"),
        "impact": impact,
        "forecast": "-",
        "previous": "-",
        "status": status_map.get(impact, "NORMAL TRADE")
    }
    SYSTEM_STATE["economic_calendar"].insert(0, new_item)
    return jsonify({"status": "ok", "economic_calendar": SYSTEM_STATE["economic_calendar"]})

@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    if SYSTEM_STATE["news_locked"]:
        return jsonify({
            "status": "blocked",
            "message": "ระบบล็อกการส่งสัญญาณเนื่องจากอยู่ในช่วงข่าวแรง (News Shield Active)"
        }), 403

    data = request.json or {}
    sig = {
        "id": len(SYSTEM_STATE["signal_history"]) + 101,
        "time": datetime.now().strftime("%H:%M:%S"),
        "symbol": data.get("symbol", "XAUUSD"),
        "tf": data.get("tf", "1H"),
        "direction": data.get("direction", "SELL"),
        "entry": data.get("entry", "4086.63"),
        "sl": data.get("sl", "4112.30"),
        "tp1": data.get("tp1", "4035.29"),
        "tp2": data.get("tp2", "4009.62"),
        "rr": "1:3",
        "status": "BROADCASTED",
        "reason": data.get("reason", "Golden Zone 61.8% Setup")
    }

    SYSTEM_STATE["latest_signal"] = sig
    SYSTEM_STATE["signal_history"].insert(0, sig)

    icon = "🔻" if sig["direction"] == "SELL" else "🟢"
    msg = (
        f"🎯 **GOLD AI SNIPER PRO (FIB 61.8%)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 สินทรัพย์: **{sig['symbol']}** (TF: {sig['tf']})\n"
        f"⚡ คำสั่ง: {icon} **{sig['direction']} LIMIT**\n"
        f"🔵 จุดเข้า (Entry 61.8%): `${sig['entry']}`\n"
        f"🔴 ตัดขาดทุน (SL 78.6%): `${sig['sl']}`\n"
        f"🟢 เป้าที่ 1 (TP1 1:2): `${sig['tp1']}`\n"
        f"🟡 เป้าหลัก (TP2 1:3): `${sig['tp2']}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧠 เหตุผล AI: {sig['reason']}\n"
        f"🛡️ *คุมความเสี่ยง 1-1.5% ต่อไม้ และงดเทรดช่วงข่าวแดง*"
    )

    notify_discord(msg)
    notify_line(msg)

    return jsonify({
        "status": "success",
        "latest_signal": sig,
        "signal_history": SYSTEM_STATE["signal_history"]
    })

def notify_discord(text):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        payload = json.dumps({"content": text}).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print("Discord Webhook Error:", e)

def notify_line(text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return
    try:
        payload = json.dumps({
            "messages": [{"type": "text", "text": text.replace("**", "")}]
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.line.me/v2/bot/message/broadcast",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print("LINE Broadcast Error:", e)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
