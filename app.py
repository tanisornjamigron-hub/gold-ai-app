from datetime import datetime
import os
from flask import Flask, jsonify, render_template_string, request
import urllib.request
import json

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

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
        }
        body {
            font-family: 'Prompt', sans-serif;
            background-color: var(--bg-deep);
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
            background: linear-gradient(145deg, rgba(17, 25, 44, 0.9), rgba(10, 15, 28, 0.95));
            border: 1px solid rgba(245, 158, 11, 0.35);
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
                        <span class="text-[10px] tracking-tighter leading-none opacity-80">AI QUANT</span>
                        <span class="text-lg tracking-tight leading-none font-mono-num">XAU</span>
                    </div>
                    <div>
                        <div class="flex flex-wrap items-center gap-2.5">
                            <h1 class="text-xl md:text-2xl font-black tracking-tight bg-gradient-to-r from-white via-amber-200 to-amber-400 bg-clip-text text-transparent">
                                GOLD AI SNIPER PRO
                            </h1>
                            <span class="px-2.5 py-0.5 text-[10px] font-extrabold uppercase bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-full">
                                FIB 61.8% • SL 78.6% • RR 1:3
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-1">Institutional Dual-Chart Terminal • ระบบกรองข่าวแรงอัตโนมัติ & ศูนย์กระจายสัญญาณ LINE / Discord</p>
                    </div>
                </div>

                <div class="flex flex-wrap items-center gap-2.5 w-full xl:w-auto justify-between xl:justify-end">
                    <div id="news-shield-box" class="bg-emerald-950/40 border border-emerald-500/40 px-3.5 py-2 rounded-xl flex items-center gap-3">
                        <div class="flex items-center gap-2">
                            <span id="shield-dot" class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
                            <div>
                                <span class="block text-[9px] uppercase text-slate-400 font-bold">NEWS FILTER SHIELD</span>
                                <span id="shield-status-text" class="text-xs font-extrabold text-emerald-400">SAFE MODE (เปิดรับสัญญาณ)</span>
                            </div>
                        </div>
                        <button onclick="toggleNewsLock()" class="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-[11px] font-bold text-slate-200 border border-slate-700">
                            สลับโหมดข่าวแดง
                        </button>
                    </div>

                    <div class="bg-slate-950/90 border border-amber-500/30 px-4 py-2 rounded-xl flex items-center gap-3">
                        <div class="text-right">
                            <span class="block text-[9px] uppercase text-amber-400/80 font-bold">XAUUSD SPOT</span>
                            <span id="live-ticker-price" class="font-mono-num text-sm md:text-base font-extrabold text-emerald-400">$3,995.80</span>
                        </div>
                        <span class="px-1.5 py-0.5 text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400 rounded">LIVE</span>
                    </div>
                </div>
            </div>
        </header>

        <!-- MAIN WORKSPACE -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- LEFT (7 COLS): CHARTS -->
            <div class="xl:col-span-7 space-y-5">
                <div class="pro-card rounded-2xl p-4 md:p-5 space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3 border-b border-slate-800 pb-3.5">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 flex-1">
                            <button onclick="switchChartMode('sniper')" id="mode-btn-sniper" class="py-2.5 px-4 rounded-xl text-xs font-extrabold bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow-lg">
                                🎯 โหมดที่ 1: AI Sniper ตีเส้น 61.8% อัตโนมัติ
                            </button>
                            <button onclick="switchChartMode('tv')" id="mode-btn-tv" class="py-2.5 px-4 rounded-xl text-xs font-bold bg-slate-950 text-slate-300 border border-slate-800">
                                🛠️ โหมดที่ 2: TradingView Studio
                            </button>
                        </div>
                        <span id="chart-tf-indicator" class="px-3.5 py-2 rounded-xl bg-amber-500/10 border border-amber-500/40 text-amber-300 text-xs font-black font-mono-num">
                            TF: 1H
                        </span>
                    </div>

                    <!-- Quick copy pills -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        <div onclick="copyPrice('val-entry')" class="cursor-pointer p-2.5 rounded-xl bg-cyan-950/30 border border-cyan-500/30 hover:border-cyan-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-cyan-300 font-bold block">🔵 ENTRY (61.8%)</span>
                                <span id="top-entry" class="font-mono-num font-extrabold text-cyan-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-cyan-500/20 text-cyan-200 px-2 py-0.5 rounded font-bold">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-sl')" class="cursor-pointer p-2.5 rounded-xl bg-rose-950/30 border border-rose-500/30 hover:border-rose-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-rose-300 font-bold block">🔴 SL (78.6%)</span>
                                <span id="top-sl" class="font-mono-num font-extrabold text-rose-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-rose-500/20 text-rose-200 px-2 py-0.5 rounded font-bold">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-tp1')" class="cursor-pointer p-2.5 rounded-xl bg-emerald-950/30 border border-emerald-500/30 hover:border-emerald-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-emerald-300 font-bold block">🟢 TP1 (1:2)</span>
                                <span id="top-tp1" class="font-mono-num font-extrabold text-emerald-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-emerald-500/20 text-emerald-200 px-2 py-0.5 rounded font-bold">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-tp2')" class="cursor-pointer p-2.5 rounded-xl bg-amber-950/30 border border-amber-500/30 hover:border-amber-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-amber-300 font-bold block">🟡 TP2 (1:3)</span>
                                <span id="top-tp2" class="font-mono-num font-extrabold text-amber-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-amber-500/20 text-amber-200 px-2 py-0.5 rounded font-bold">Copy</span>
                        </div>
                    </div>

                    <!-- Mode 1 Chart -->
                    <div id="sniper-chart-wrapper" class="space-y-2">
                        <div id="sniper-lw-chart" class="w-full h-[520px] rounded-xl overflow-hidden border border-slate-800 bg-[#050912]"></div>
                    </div>

                    <!-- Mode 2 Chart -->
                    <div id="tv-chart-wrapper" class="hidden space-y-2">
                        <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800" style="height:520px; width:100%;">
                            <div id="tradingview_studio_chart" style="height:100%; width:100%;"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- RIGHT (5 COLS): CONTROLS -->
            <div class="xl:col-span-5 space-y-5">
                
                <!-- TIMEFRAME SELECTOR -->
                <div class="pro-card rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold text-amber-400 block">STEP 1 • SELECT TIMEFRAME</span>
                            <h2 class="text-base font-bold text-white">เลือกไทม์เฟรมวิเคราะห์โครงสร้างตลาด</h2>
                        </div>
                        <span id="active-tf-badge" class="px-3 py-1 rounded-xl text-xs font-black font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950">
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
                </div>

                <!-- SNIPER SETUP CARD -->
                <div class="pro-card-gold rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold text-amber-400 block">STEP 2 • GOLDEN ZONE SNIPER & BROADCAST</span>
                            <h2 class="text-lg font-black text-white">แผนจุดเข้าเทรด 61.8% & ส่งสัญญาณ</h2>
                        </div>
                        <span id="setup-order-badge" class="px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num">--</span>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                        <div class="bg-cyan-950/50 p-3.5 rounded-xl border border-cyan-500/40">
                            <span class="font-extrabold text-cyan-300">🔵 ENTRY (61.8%)</span>
                            <div id="val-entry" class="text-2xl font-black font-mono-num text-cyan-400 mt-1">--</div>
                        </div>
                        <div class="bg-rose-950/50 p-3.5 rounded-xl border border-rose-500/40">
                            <span class="font-extrabold text-rose-300">🔴 SL (78.6%)</span>
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

                    <textarea id="setup-reason" rows="2" class="w-full text-xs text-slate-200 bg-slate-950 p-3 rounded-xl border border-slate-800"></textarea>

                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="w-full py-3.5 rounded-xl font-extrabold text-xs bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 shadow-lg">
                        🚀 ยิงสัญญาณเข้า LINE OA • Discord • Python Bot ทันที
                    </button>
                </div>

            </div>
        </div>
    </div>

    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-emerald-500 text-slate-950 px-4 py-3 rounded-xl font-extrabold text-xs shadow-2xl z-50">
        <span id="toast-notify-text">สำเร็จ!</span>
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
                entry: entry.toFixed(2), sl: sl.toFixed(2), tp1: tp1.toFixed(2), tp2: tp2.toFixed(2),
                riskDollar: risk.toFixed(2), reward1Dollar: (risk * 2).toFixed(2), reward2Dollar: (risk * 3).toFixed(2)
            };
        }

        // แต่ละ Timeframe มีโครงสร้างราคาสวิงและเมล็ดพันธุ์ความถี่กราฟ (seed) ไม่เหมือนกัน เพื่อไม่ให้กราฟซ้ำกัน
        const timeframeConfigs = {
            '1m': { label: '1 นาที (1M)', tvInterval: '1', stepSec: 60, calcDir: 'SELL', swingHigh: 4005.00, swingLow: 3991.00, currentPrice: 3996.50, seedOffset: 1.1 },
            '5m': { label: '5 นาที (5M)', tvInterval: '5', stepSec: 300, calcDir: 'SELL', swingHigh: 4022.00, swingLow: 3990.00, currentPrice: 3995.80, seedOffset: 2.3 },
            '15m': { label: '15 นาที (15M)', tvInterval: '15', stepSec: 900, calcDir: 'SELL', swingHigh: 4045.00, swingLow: 3988.00, currentPrice: 3995.80, seedOffset: 3.7 },
            '1h': { label: '1 ชั่วโมง (1H)', tvInterval: '60', stepSec: 3600, calcDir: 'SELL', swingHigh: 4145.00, swingLow: 3992.20, currentPrice: 3995.80, seedOffset: 5.0 },
            '4h': { label: '4 ชั่วโมง (4H)', tvInterval: '240', stepSec: 14400, calcDir: 'SELL', swingHigh: 4210.00, swingLow: 3980.00, currentPrice: 3995.80, seedOffset: 7.2 },
            'daily': { label: 'รายวัน (Daily)', tvInterval: 'D', stepSec: 86400, calcDir: 'SELL', swingHigh: 4240.00, swingLow: 3960.00, currentPrice: 3995.80, seedOffset: 9.8 }
        };

        let lwChart = null, candleSeries = null, activePriceLines = [], currentChartMode = 'sniper', currentTfKey = '1h', isNewsLocked = false;

        function initLightweightChart() {
            const container = document.getElementById('sniper-lw-chart');
            container.innerHTML = '';
            lwChart = LightweightCharts.createChart(container, {
                width: container.clientWidth, height: 520,
                layout: { background: { type: 'solid', color: '#050912' }, textColor: '#94a3b8' },
                grid: { vertLines: { color: 'rgba(30, 41, 59, 0.45)' }, horzLines: { color: 'rgba(30, 41, 59, 0.45)' } }
            });
            candleSeries = lwChart.addCandlestickSeries({ upColor: '#10b981', downColor: '#f43f5e' });
        }

        // สร้างทรงกราฟที่ไม่ซ้ำกันในแต่ละ TF โดยใช้ seedOffset และสูตรคลื่นแยกอิสระ
        function generateUniqueCandles(direction, swingHigh, swingLow, currentPrice, stepSec, seed) {
            const candles = [];
            const totalBars = 80;
            const nowSec = Math.floor(Date.now() / 1000) - (totalBars * stepSec);
            const range = swingHigh - swingLow;
            let prevClose = swingHigh - (range * 0.3);

            for (let i = 0; i < totalBars; i++) {
                const wave1 = Math.sin((i + seed) * 0.35) * (range * 0.28);
                const wave2 = Math.cos((i * seed) * 0.15) * (range * 0.15);
                const trendPull = (i / totalBars) * (currentPrice - (swingHigh - range * 0.3));
                
                let close = (swingHigh + swingLow) / 2 + wave1 + wave2 + trendPull;
                if (i === 0) close = swingHigh - range * 0.2;
                if (i === totalBars - 1) close = currentPrice;

                const open = prevClose;
                let high = Math.max(open, close) + Math.abs(Math.sin(i * seed)) * (range * 0.04);
                let low = Math.min(open, close) - Math.abs(Math.cos(i * seed)) * (range * 0.04);

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

        function drawSniperLinesOnChart(direction, swingHigh, swingLow, currentPrice, stepSec, mathRes, seed) {
            if (!lwChart || !candleSeries) initLightweightChart();
            activePriceLines.forEach(line => { try { candleSeries.removePriceLine(line); } catch(e){} });
            activePriceLines = [];

            const candles = generateUniqueCandles(direction, swingHigh, swingLow, currentPrice, stepSec, seed);
            candleSeries.setData(candles);

            activePriceLines.push(candleSeries.createPriceLine({ price: mathRes.entryNum, color: '#06b6d4', lineWidth: 2, title: `🎯 ENTRY 61.8%` }));
            activePriceLines.push(candleSeries.createPriceLine({ price: mathRes.slNum, color: '#f43f5e', lineWidth: 2, title: `🛑 SL 78.6%` }));
            activePriceLines.push(candleSeries.createPriceLine({ price: mathRes.tp1Num, color: '#10b981', lineWidth: 2, lineStyle: 2, title: `💰 TP1 (1:2)` }));
            activePriceLines.push(candleSeries.createPriceLine({ price: mathRes.tp2Num, color: '#f59e0b', lineWidth: 2, title: `🚀 TP2 (1:3)` }));

            lwChart.timeScale().fitContent();
        }

        function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const cfg = timeframeConfigs[tfKey];
            if (!cfg) return;

            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num bg-slate-950 text-slate-400 border border-slate-800";
            });
            document.getElementById('btn-' + tfKey).className = "tf-btn py-2.5 px-2 rounded-xl text-xs font-extrabold font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow-lg";

            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            document.getElementById('chart-tf-indicator').innerText = 'TF: ' + tfKey.toUpperCase();

            const mathRes = calculateSniperMath(cfg.calcDir, cfg.swingHigh, cfg.swingLow);
            document.getElementById('val-entry').innerText = '$' + mathRes.entry;
            document.getElementById('val-sl').innerText = '$' + mathRes.sl;
            document.getElementById('val-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('val-tp2').innerText = '$' + mathRes.tp2;
            document.getElementById('top-entry').innerText = '$' + mathRes.entry;
            document.getElementById('top-sl').innerText = '$' + mathRes.sl;
            document.getElementById('top-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('top-tp2').innerText = '$' + mathRes.tp2;

            document.getElementById('setup-reason').value = `แผนเทรนด์ TF ${tfKey.toUpperCase()}: ดักเข้าที่ Fib 61.8% ($${mathRes.entry}) SL ที่ 78.6% ($${mathRes.sl})`;
            
            drawSniperLinesOnChart(cfg.calcDir, cfg.swingHigh, cfg.swingLow, cfg.currentPrice, cfg.stepSec, mathRes, cfg.seedOffset);
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
            setTimeout(() => toast.classList.add('hidden'), 2000);
        }

        async function toggleNewsLock() {
            const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
            const data = await res.json();
            isNewsLocked = data.news_locked;
            showToast(isNewsLocked ? '🛡️ ล็อกระบบช่วงข่าวแล้ว' : '✅ ปลดล็อกระบบแล้ว');
        }

        async function broadcastCurrentSignal() {
            if (isNewsLocked) { showToast('🛑 ระบบล็อกอยู่'); return; }
            const payload = {
                symbol: 'XAUUSD', tf: currentTfKey.toUpperCase(),
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
            if(res.ok) showToast('🚀 ส่งสัญญาณเข้า LINE & Discord สำเร็จ!');
        }

        window.addEventListener('DOMContentLoaded', () => {
            initLightweightChart();
            selectTimeframe('1h');
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/toggle-news-lock', methods=['POST'])
def toggle_news_lock():
    SYSTEM_STATE["news_locked"] = not SYSTEM_STATE["news_locked"]
    return jsonify({"status": "ok", "news_locked": SYSTEM_STATE["news_locked"]})

@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    if SYSTEM_STATE["news_locked"]:
        return jsonify({"status": "blocked"}), 403
    data = request.json or {}
    msg = f"🎯 XAUUSD ({data.get('tf')}) SELL 61.8% | Entry: ${data.get('entry')} | SL: ${data.get('sl')} | TP2: ${data.get('tp2')}"
    
    if DISCORD_WEBHOOK_URL:
        try:
            req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=json.dumps({"content": msg}).encode("utf-8"), headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception as e: print("Discord Error:", e)

    if LINE_CHANNEL_ACCESS_TOKEN:
        try:
            req = urllib.request.Request("https://api.line.me/v2/bot/message/broadcast", data=json.dumps({"messages": [{"type": "text", "text": msg}]}).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"})
            urllib.request.urlopen(req, timeout=5)
        except Exception as e: print("LINE Error:", e)

    return jsonify({"status": "success"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
