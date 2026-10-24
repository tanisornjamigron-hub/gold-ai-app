import os
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO - Dual-Chart & Auto Golden Zone 61.8%</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- TradingView Lightweight Charts (Standalone Version) -->
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Prompt', sans-serif; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #05080f; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #f59e0b; }
    </style>
</head>
<body class="bg-[#05080f] text-slate-100 antialiased min-h-screen p-3 md:p-5 selection:bg-amber-500 selection:text-slate-950">
    <div class="max-w-[1680px] mx-auto space-y-4">
        
        <!-- HEADER & DAILY BIAS -->
        <header class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-2xl backdrop-blur-md">
            <div class="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
                
                <div class="flex items-center gap-3.5">
                    <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 flex items-center justify-center shadow-lg shadow-amber-500/25 font-black text-slate-950 text-xl shrink-0">
                        XAU
                    </div>
                    <div>
                        <div class="flex flex-wrap items-center gap-2">
                            <h1 class="text-xl md:text-2xl font-black tracking-wide bg-gradient-to-r from-amber-200 via-amber-400 to-yellow-500 bg-clip-text text-transparent">
                                GOLD AI SNIPER PRO
                            </h1>
                            <span class="px-2.5 py-0.5 text-[11px] font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full">
                                DUAL-CHART • ENTRY 61.8% • SL 78.6% • RR 1:3
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-0.5">
                            ระบบกราฟคู่ตีเส้นจุดเข้าอัตโนมัติ (Auto Price Lines) + สตูดิโอวางแผน TradingView เต็มรูปแบบ
                        </p>
                    </div>
                </div>

                <!-- ป้ายบอกสถานะหน้าเทรดหลักของวัน (Daily Master Bias) -->
                <div class="flex flex-wrap items-center gap-3 w-full xl:w-auto justify-between xl:justify-end">
                    <div class="bg-slate-950 border border-slate-800 px-4 py-2.5 rounded-xl flex items-center gap-3">
                        <span class="text-xs text-slate-400">เทรนด์หลักวันนี้ (Daily Bias):</span>
                        <span id="master-daily-bias" class="px-3 py-1 rounded-lg text-xs font-extrabold bg-rose-500/20 text-rose-400 border border-rose-500/40">
                            🔻 SELL BIAS (เน้นดักเด้ง Short ที่ 61.8%)
                        </span>
                    </div>

                    <div class="bg-slate-950 border border-slate-800 px-4 py-2.5 rounded-xl flex items-center gap-2">
                        <span class="w-2.5 h-2.5 bg-emerald-400 rounded-full animate-ping"></span>
                        <span class="w-2.5 h-2.5 -ml-5 bg-emerald-500 rounded-full"></span>
                        <span class="text-xs font-bold text-emerald-400">XAUUSD LIVE (~$3,995.80)</span>
                    </div>
                </div>
            </div>
        </header>

        <!-- MAIN WORKSPACE GRID -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- ฝั่งซ้าย: ระบบกราฟ 2 โหมด (Dual-Chart) + กล่องวิเคราะห์ข่าวเศรษฐกิจ (7 ส่วน) -->
            <div class="xl:col-span-7 space-y-5">
                
                <!-- กล่องกราฟ Dual-Chart -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-2xl space-y-3">
                    
                    <!-- แถบปุ่มสลับโหมดกราฟ (Mode 1 vs Mode 2) -->
                    <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3 border-b border-slate-800 pb-3">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full sm:w-auto flex-1">
                            <!-- ปุ่มโหมดที่ 1 (ค่าเริ่มต้น) -->
                            <button onclick="switchChartMode('sniper')" id="mode-btn-sniper" class="py-2.5 px-4 rounded-xl text-xs font-extrabold transition flex items-center justify-center gap-2 bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow-lg shadow-amber-500/20">
                                <span>🎯 โหมดที่ 1: กราฟ AI ตีเส้นจุดเข้าอัตโนมัติ</span>
                            </button>
                            <!-- ปุ่มโหมดที่ 2 -->
                            <button onclick="switchChartMode('tv')" id="mode-btn-tv" class="py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 bg-slate-950 text-slate-300 border border-slate-800 hover:border-amber-500/50">
                                <span>🛠️ โหมดที่ 2: กราฟ TradingView (ตีแผนเอง)</span>
                            </button>
                        </div>

                        <div class="flex items-center justify-between sm:justify-end gap-2">
                            <span id="chart-tf-indicator" class="px-3 py-1.5 rounded-lg bg-slate-950 border border-amber-500/40 text-amber-400 text-xs font-black">
                                กราฟ: 1H
                            </span>
                        </div>
                    </div>

                    <!-- คำอธิบายเส้นสีบนกราฟ + ปุ่มกดคัดลอกราคา -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-950 p-2.5 rounded-xl border border-slate-800/90 text-xs">
                        <div onclick="copyPrice('val-entry')" class="cursor-pointer p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/40 hover:bg-cyan-500/20 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-cyan-300 font-bold block">🔵 เส้นจุดเข้า (61.8%)</span>
                                <span id="top-entry" class="font-black text-cyan-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-cyan-500/20 text-cyan-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-sl')" class="cursor-pointer p-2 rounded-lg bg-rose-500/10 border border-rose-500/40 hover:bg-rose-500/20 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-rose-300 font-bold block">🔴 เส้น SL (78.6%)</span>
                                <span id="top-sl" class="font-black text-rose-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-rose-500/20 text-rose-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-tp1')" class="cursor-pointer p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/40 hover:bg-emerald-500/20 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-emerald-300 font-bold block">🟢 เส้น TP1 (1:2)</span>
                                <span id="top-tp1" class="font-black text-emerald-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-emerald-500/20 text-emerald-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                        <div onclick="copyPrice('val-tp2')" class="cursor-pointer p-2 rounded-lg bg-amber-500/10 border border-amber-500/40 hover:bg-amber-500/20 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-amber-300 font-bold block">🟡 เส้น TP2 (1:3)</span>
                                <span id="top-tp2" class="font-black text-amber-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-amber-500/20 text-amber-200 px-1.5 py-0.5 rounded">Copy</span>
                        </div>
                    </div>

                    <!-- พื้นที่แสดงกราฟ โหมดที่ 1: AI Sniper Auto-Line Chart (Lightweight Charts) -->
                    <div id="sniper-chart-wrapper" class="space-y-2">
                        <div class="flex flex-wrap justify-between items-center text-[11px] text-slate-400 px-1">
                            <span>✨ <strong>AI Auto-Plot:</strong> ระบบขีดเส้น Entry 61.8%, SL 78.6%, TP1 (1:2) และ TP2 (1:3) ลงบนกราฟให้อัตโนมัติ (หมุนลูกกลิ้งเมาส์เพื่อซูมเข้า-ออกได้)</span>
                            <button onclick="resetSniperZoom()" class="text-amber-400 hover:underline font-bold">🔍 รีเซ็ตมุมมองกราฟให้เห็นครบทุกเส้น</button>
                        </div>
                        <div id="sniper-lw-chart" class="w-full h-[540px] rounded-xl overflow-hidden border border-slate-800 bg-[#070b14]"></div>
                    </div>

                    <!-- พื้นที่แสดงกราฟ โหมดที่ 2: TradingView Advanced Widget (ซ่อนไว้ตอนเริ่มต้น กดสลับมาดูได้ทันที) -->
                    <div id="tv-chart-wrapper" class="hidden space-y-2">
                        <div class="flex flex-wrap justify-between items-center text-[11px] text-amber-300 px-1">
                            <span>🛠️ <strong>TradingView Studio:</strong> ใช้เครื่องมือด้านซ้ายมือเพื่อลาก Fibonacci หรือกดปุ่ม Indicators ด้านบนเพื่อเปิด Auto Fib Retracement</span>
                        </div>
                        <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800" style="height:540px; width:100%;">
                            <div id="tradingview_studio_chart" style="height:100%; width:100%;"></div>
                        </div>
                    </div>
                </div>

                <!-- กล่องวิเคราะห์เศรษฐกิจมหภาคและตารางข่าว (Macro & Forex Factory Impact) -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-800 pb-3 gap-2">
                        <div class="flex items-center gap-2">
                            <span class="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-400 text-xs font-extrabold border border-amber-500/30">
                                MACRO & FOREX FACTORY AI
                            </span>
                            <h2 class="text-base font-bold text-slate-100">
                                วิเคราะห์ปัจจัยพื้นฐานและระดับความผันผวนของตลาด
                            </h2>
                        </div>
                        <span id="current-date-label" class="text-xs text-amber-400 font-semibold"></span>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-xs">
                        <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200">ทิศทาง Fed & ดอลลาร์ (DXY)</span>
                                <span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 font-bold text-[10px]">
                                    Bearish (กดดันทอง)
                                </span>
                            </div>
                            <p class="text-slate-400 leading-relaxed">
                                อัตราผลตอบแทนพันธบัตรสหรัฐฯ ทรงตัวระดับสูง กดดันให้ทองคำมีแรงเทขายทำกำไรเมื่อรีบาวด์ แผนดัก Sell ที่ระดับ 61.8% จึงได้เปรียบสูงสุด
                            </p>
                        </div>

                        <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200">สภาวะความผันผวนระหว่างวัน</span>
                                <span class="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 font-bold text-[10px]">
                                    Medium / Sideway
                                </span>
                            </div>
                            <p class="text-slate-400 leading-relaxed">
                                ช่วงก่อนตลาดอเมริกาเปิด กราฟอาจวิ่งสะสมพลังความผันผวนปานกลาง แนะนำให้รอราคาวิ่งมาชนเส้นสีฟ้า (Entry 61.8%) บนกราฟเท่านั้น ห้ามไล่ราคา
                            </p>
                        </div>

                        <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200">กลยุทธ์รับมือข่าว CPI / NFP</span>
                                <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold text-[10px]">
                                    Fix Risk 78.6%
                                </span>
                            </div>
                            <p class="text-slate-400 leading-relaxed">
                                การล็อกจุดเข้าที่ 61.8% และวาง SL ที่ 78.6% ทำให้ระยะตัดขาดทุนสั้นมาก เพียงชนะไม้เดียวที่ TP2 (RR 1:3) สามารถครอบคลุมการแพ้ได้ถึง 3 ครั้ง
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ฝั่งขวา: แผงควบคุม Multi-Timeframe + การ์ดจุดเข้า Sniper 61.8% & RR 1:3 (5 ส่วน) -->
            <div class="xl:col-span-5 space-y-5">
                
                <!-- 1. ปุ่มเลือกไทม์เฟรมและตัวกรองสถานะตลาด -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <h2 class="text-base font-bold text-amber-400">1. เลือกไทม์เฟรมวิเคราะห์ (Multi-Timeframe)</h2>
                            <p class="text-[11px] text-slate-400">กดปุ่มเพื่อเปลี่ยนกราฟและตีเส้น Entry 61.8% / SL 78.6% ใหม่อัตโนมัติ</p>
                        </div>
                        <span id="active-tf-badge" class="px-3 py-1 rounded-xl text-xs font-black bg-amber-500 text-slate-950">
                            TF: 1H
                        </span>
                    </div>

                    <!-- ปุ่ม Timeframe 6 ปุ่ม -->
                    <div class="grid grid-cols-3 gap-2">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">1 นาที (1M)</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">5 นาที (5M)</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">15 นาที (15M)</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">1 ชั่วโมง (1H)</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">4 ชั่วโมง (4H)</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">รายวัน (Daily)</button>
                    </div>

                    <!-- สถานะโครงสร้างของไทม์เฟรม -->
                    <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2.5 text-xs">
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">สถานะโครงสร้างตลาด:</span>
                            <span id="tf-structure-badge" class="px-2.5 py-1 rounded-md font-bold">--</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">ระดับความผันผวน:</span>
                            <span id="tf-volatility" class="font-bold text-slate-200">--</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">คำแนะนำหน้าเล่น (Bias):</span>
                            <span id="tf-bias-text" class="font-extrabold text-sm">--</span>
                        </div>
                    </div>
                </div>

                <!-- 2. การ์ดแผนจุดเข้าเทรด SNIPER SETUP (Entry 61.8% | SL 78.6% | TP1 1:2 | TP2 1:3) -->
                <div class="bg-slate-900/90 border border-amber-500/40 rounded-2xl p-5 shadow-2xl space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-amber-400 block">GOLDEN ZONE SNIPER</span>
                            <h2 class="text-lg font-black text-slate-100">2. แผนจุดเข้าเทรด (แสดงเส้นบนกราฟ)</h2>
                        </div>
                        <span id="setup-order-badge" class="px-3 py-1.5 rounded-xl text-xs font-black">--</span>
                    </div>

                    <!-- กล่องเตือนกรณี Sideway -->
                    <div id="sideway-warning" class="hidden bg-yellow-500/15 border border-yellow-500/50 rounded-xl p-3.5 text-xs text-yellow-200 space-y-1">
                        <div class="font-extrabold text-yellow-400 text-sm">⚠️ ตลาดกำลังเป็นไซด์เวย์ (Sideway) ในไทม์เฟรมนี้!</div>
                        <p>แนะนำให้ <strong>"นั่งทับมือ"</strong> รอให้กราฟเลือกทางชัดเจน หรือกดเปลี่ยนไปดูแผนของไทม์เฟรม <strong>15M / 1H</strong> แทนครับ</p>
                    </div>

                    <div class="flex justify-between items-center bg-slate-950 px-3.5 py-2.5 rounded-xl border border-slate-800 text-xs">
                        <span class="text-slate-400">ระยะสวิงที่ใช้วัด Fib:</span>
                        <span id="setup-swing-info" class="font-bold text-amber-300">--</span>
                    </div>

                    <!-- การ์ด 4 จุดหลัก -->
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <!-- ENTRY 61.8% -->
                        <div class="bg-gradient-to-br from-cyan-950/60 to-slate-950 p-4 rounded-xl border border-cyan-500/50 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-cyan-300">🔵 ENTRY (Fib 61.8%)</span>
                                <span class="text-[10px] bg-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded font-bold">จุดเข้าเดียว</span>
                            </div>
                            <div id="val-entry" class="text-2xl font-black text-cyan-400">--</div>
                            <p class="text-[11px] text-slate-400">เส้นสีฟ้าบนกราฟ (Golden Zone)</p>
                        </div>

                        <!-- STOP LOSS 78.6% -->
                        <div class="bg-gradient-to-br from-rose-950/60 to-slate-950 p-4 rounded-xl border border-rose-500/50 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-rose-300">🔴 STOP LOSS (78.6%)</span>
                                <span id="val-risk-pts" class="text-[10px] bg-rose-500/20 text-rose-300 px-2 py-0.5 rounded font-bold">Risk: --</span>
                            </div>
                            <div id="val-sl" class="text-2xl font-black text-rose-400">--</div>
                            <p class="text-[11px] text-slate-400">เส้นสีแดงบนกราฟ (จุดยอมแพ้)</p>
                        </div>

                        <!-- TP1 (RR 1:2) -->
                        <div class="bg-gradient-to-br from-emerald-950/60 to-slate-950 p-4 rounded-xl border border-emerald-500/50 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-emerald-300">🟢 TAKE PROFIT 1 (1:2)</span>
                                <span id="val-tp1-pts" class="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp1" class="text-2xl font-black text-emerald-400">--</div>
                            <p class="text-[11px] text-slate-400">เส้นสีเขียวบนกราฟ (เก็บกำไรรอบแรก)</p>
                        </div>

                        <!-- TP2 (RR 1:3) -->
                        <div class="bg-gradient-to-br from-amber-950/60 to-slate-950 p-4 rounded-xl border border-amber-500/60 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-amber-300">🟡 TAKE PROFIT 2 (1:3)</span>
                                <span id="val-tp2-pts" class="text-[10px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp2" class="text-2xl font-black text-amber-400">--</div>
                            <p class="text-[11px] text-slate-400">เส้นสีทองบนกราฟ (เป้าหลัก RR 1:3)</p>
                        </div>
                    </div>

                    <!-- คำอธิบาย AI -->
                    <div class="space-y-1">
                        <span class="text-xs font-bold text-amber-400 block">🧠 วิเคราะห์แผนการเทรดจาก AI:</span>
                        <p id="setup-reason" class="text-xs text-slate-200 bg-slate-950 p-3.5 rounded-xl border border-slate-800 leading-relaxed">
                            --
                        </p>
                    </div>
                </div>

                <!-- 3. กล่องปรับค่า Swing High / Swing Low เพื่อขีดเส้นบนกราฟใหม่ตามใจชอบ -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-3">
                    <div class="border-b border-slate-800 pb-2">
                        <h3 class="text-sm font-bold text-amber-400">⚡ ปรับจุด Swing High / Low เอง (อัปเดตเส้นบนกราฟทันที)</h3>
                        <p class="text-[11px] text-slate-400">เปลี่ยนฝั่ง Buy/Sell หรือใส่ราคา High/Low ใหม่ เส้นบนกราฟโหมดที่ 1 จะขยับตามทันที</p>
                    </div>
                    <div class="grid grid-cols-3 gap-2 text-xs">
                        <div>
                            <label class="text-slate-400 block mb-1">ฝั่งที่เล่น (Bias)</label>
                            <select id="custom-dir" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-100 font-bold">
                                <option value="SELL">ขาลง (ดัก Sell)</option>
                                <option value="BUY">ขาขึ้น (ดัก Buy)</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1">Swing High ($)</label>
                            <input type="number" id="custom-high" step="0.1" value="4145.00" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-100 font-bold">
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1">Swing Low ($)</label>
                            <input type="number" id="custom-low" step="0.1" value="3992.20" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-100 font-bold">
                        </div>
                    </div>
                    <button onclick="applyCustomSwing()" class="w-full py-2.5 bg-gradient-to-r from-amber-500 to-yellow-500 hover:from-amber-400 hover:to-yellow-400 text-slate-950 font-extrabold text-xs rounded-xl transition shadow-lg">
                        🔄 คำนวณและตีเส้น Entry 61.8% / SL 78.6% / TP 1:3 ลงบนกราฟใหม่
                    </button>
                </div>

                <!-- 4. ตารางสรุปภาพรวมทุกไทม์เฟรม (Matrix Overview) -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-3">
                    <h3 class="text-sm font-bold text-slate-200 border-b border-slate-800 pb-2">
                        📊 ตารางสรุปจุดเข้า 61.8% & เป้า 1:3 ทุกไทม์เฟรม
                    </h3>
                    <div class="space-y-2 text-xs" id="matrix-overview-list"></div>
                </div>

            </div>
        </div>
    </div>

    <!-- Toast แจ้งเตือนคัดลอกราคา -->
    <div id="toast-copy" class="fixed bottom-5 right-5 hidden bg-emerald-500 text-slate-950 px-4 py-2.5 rounded-xl font-extrabold text-xs shadow-2xl z-50">
        ✅ คัดลอกราคาเรียบร้อย!
    </div>

    <!-- TradingView External Script สำหรับโหมดที่ 2 -->
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>

    <script>
        // ==========================================
        // 1. ระบบคำนวณคณิตศาสตร์ Fib 61.8%, SL 78.6%, RR 1:2 & 1:3
        // ==========================================
        function calculateSniperMath(direction, swingHigh, swingLow) {
            const range = swingHigh - swingLow;
            let entry, sl, risk, tp1, tp2;

            if (direction === 'SELL') {
                // ขาลง: วัดจาก High ลงมา Low -> รอเด้งขึ้นไปที่ 61.8% เพื่อเปิด Sell, ตัดขาดทุนที่ 78.6%
                entry = swingLow + (range * 0.618);
                sl = swingLow + (range * 0.786);
                risk = Math.abs(sl - entry);
                tp1 = entry - (risk * 2);
                tp2 = entry - (risk * 3);
            } else {
                // ขาขึ้น: วัดจาก Low ขึ้นไป High -> รอย่อลงมาที่ 61.8% เพื่อเปิด Buy, ตัดขาดทุนที่ 78.6%
                entry = swingHigh - (range * 0.618);
                sl = swingHigh - (range * 0.786);
                risk = Math.abs(entry - sl);
                tp1 = entry + (risk * 2);
                tp2 = entry + (risk * 3);
            }

            return {
                entryNum: entry,
                slNum: sl,
                tp1Num: tp1,
                tp2Num: tp2,
                entry: entry.toFixed(2),
                sl: sl.toFixed(2),
                tp1: tp1.toFixed(2),
                tp2: tp2.toFixed(2),
                riskDollar: risk.toFixed(2),
                reward1Dollar: (risk * 2).toFixed(2),
                reward2Dollar: (risk * 3).toFixed(2)
            };
        }

        // ==========================================
        // 2. ข้อมูลแต่ละไทม์เฟรม (อ้างอิงราคาตลาด ~3,995.80)
        // ==========================================
        const timeframeConfigs = {
            '1m': {
                label: '1 นาที (1M)',
                tvInterval: '1',
                stepSec: 60,
                calcDir: 'SELL',
                swingHigh: 4001.20,
                swingLow: 3992.20,
                currentPrice: 3995.80,
                structure: 'ไซด์เวย์กรอบแคบ (Sideway)',
                structureClass: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40',
                volatility: 'ผันผวนปานกลาง-ต่ำ (แกว่งออกข้าง)',
                biasText: '🟡 NEUTRAL / SIDEWAY (แนะนำนั่งทับมือ)',
                biasColor: 'text-yellow-400',
                isSideway: true,
                reason: 'ไทม์เฟรม 1 นาที กราฟวิ่งสะสมพลังออกข้าง (Sideway) หากฝืนเข้ากลางกรอบจะโดนสวิงกิน Stop Loss ง่ายมาก แนะนำให้นั่งทับมือ หรือรอให้กราฟดีดขึ้นไปชนเส้นสีฟ้า (Entry 61.8% ที่ $3,997.76) บนกราฟเท่านั้น'
            },
            '5m': {
                label: '5 นาที (5M)',
                tvInterval: '5',
                stepSec: 300,
                calcDir: 'SELL',
                swingHigh: 4016.00,
                swingLow: 3992.20,
                currentPrice: 3995.80,
                structure: 'ขาลงระยะสั้น (Minor Downtrend)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนปานกลาง (Scalping)',
                biasText: '🔴 SELL BIAS (ดัก Sell ที่เส้นสีฟ้า 61.8%)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ไทม์เฟรม 5 นาทีทำโครงสร้างขาลงชัดเจน ดูที่เส้นสีฟ้าบนกราฟ ($4,006.91) คือจุดตั้ง Sell Limit ไม้เดียวเน้นๆ วาง SL ที่เส้นสีแดง 78.6% ($4,010.91) แล้วรันลงมาหาเส้นสีเขียว TP1 ($3,998.91) และเส้นสีทอง TP2 ($3,994.91)'
            },
            '15m': {
                label: '15 นาที (15M)',
                tvInterval: '15',
                stepSec: 900,
                calcDir: 'SELL',
                swingHigh: 4035.00,
                swingLow: 3992.20,
                currentPrice: 3995.80,
                structure: 'เทรนด์ขาลงชัดเจน (Intraday Bearish)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนกำลังดี (แนะนำเทรดระหว่างวัน)',
                biasText: '🔴 SELL BIAS (รอเข้าที่เส้นสีฟ้า 61.8%)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ไทม์เฟรม 15 นาทีเกิดการทุบทำลายโครงสร้างขาลง จุดเข้าที่ได้เปรียบที่สุดบนกราฟคือเส้นสีฟ้า Entry 61.8% ($4,018.65) ตัดขาดทุนที่เส้นสีแดง 78.6% ($4,025.84) ลุ้นเป้ากำไร RR 1:2 ที่ $4,004.27 และ RR 1:3 ที่ $3,997.08'
            },
            '1h': {
                label: '1 ชั่วโมง (1H)',
                tvInterval: '60',
                stepSec: 3600,
                calcDir: 'SELL',
                swingHigh: 4145.00,
                swingLow: 3992.20,
                currentPrice: 3995.80,
                structure: 'ขาลงหลัก / รอรีบาวด์ (Major Bearish)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนสูง (High Probability)',
                biasText: '🔴 STRONG SELL BIAS (โซนทองคำ 61.8%)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ไทม์เฟรม 1 ชั่วโมง กราฟทิ้งตัวลงมาจาก Swing High $4,145.00 ลงมาทำ Low ที่ $3,992.20 ระบบได้ขีดเส้นสีฟ้า Entry 61.8% ($4,086.63) และเส้นสีแดง SL 78.6% ($4,112.30) ไว้บนกราฟเรียบร้อย พร้อมเป้า TP1 (1:2) และ TP2 (1:3)'
            },
            '4h': {
                label: '4 ชั่วโมง (4H)',
                tvInterval: '240',
                stepSec: 14400,
                calcDir: 'SELL',
                swingHigh: 4210.00,
                swingLow: 3992.20,
                currentPrice: 3995.80,
                structure: 'ขาลงระดับมหภาค (Macro Downtrend)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนสูง (Swing Trade)',
                biasText: '🔴 SELL BIAS (คุมฝั่งขายตามเทรนด์ใหญ่)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ภาพใหญ่ 4 ชั่วโมง แท่งเทียนขาลงคุมตลาดอย่างสมบูรณ์ เส้นจุดเข้า 61.8% รอบใหญ่อยู่ที่ $4,126.80 และวาง SL ที่ 78.6% ($4,163.39) เพื่อถือรันเทรนด์เป้าใหญ่ RR 1:3 ที่ $4,017.03'
            },
            'daily': {
                label: 'รายวัน (Daily)',
                tvInterval: 'D',
                stepSec: 86400,
                calcDir: 'SELL',
                swingHigh: 4240.00,
                swingLow: 3992.20,
                currentPrice: 3995.80,
                structure: 'ปรับฐานรายวัน (Daily Correction)',
                structureClass: 'bg-amber-500/20 text-amber-300 border border-amber-500/40',
                volatility: 'ผันผวนระดับมหภาค (Position)',
                biasText: '🔴 SELL BIAS (เทรดหน้า Sell ตามแท่ง Day)',
                biasColor: 'text-amber-400',
                isSideway: false,
                reason: 'ภาพรวมรายวันเกิดการพักฐานใหญ่ลงมาจากยอด $4,240.00 แผนหลักของวันนี้จึงเน้นดักจังหวะเด้ง Sell ที่ระดับ 61.8% ในทุกไทม์เฟรมย่อย'
            }
        };

        // ==========================================
        // 3. ระบบกราฟโหมดที่ 1: Lightweight Charts + Auto Price Lines
        // ==========================================
        let lwChart = null;
        let candleSeries = null;
        let activePriceLines = [];
        let currentChartMode = 'sniper';
        let currentTfKey = '1h';
        let currentTvLoadedInterval = null;

        function initLightweightChart() {
            const container = document.getElementById('sniper-lw-chart');
            container.innerHTML = '';

            lwChart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 540,
                layout: {
                    background: { type: 'solid', color: '#070b14' },
                    textColor: '#cbd5e1',
                    fontFamily: 'Prompt, sans-serif'
                },
                grid: {
                    vertLines: { color: '#1e293b' },
                    horzLines: { color: '#1e293b' }
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal
                },
                rightPriceScale: {
                    borderColor: '#334155',
                    autoScale: true,
                    scaleMargins: { top: 0.08, bottom: 0.08 }
                },
                timeScale: {
                    borderColor: '#334155',
                    timeVisible: true,
                    secondsVisible: false
                }
            });

            candleSeries = lwChart.addCandlestickSeries({
                upColor: '#10b981',
                downColor: '#f43f5e',
                borderUpColor: '#10b981',
                borderDownColor: '#f43f5e',
                wickUpColor: '#10b981',
                wickDownColor: '#f43f5e'
            });

            window.addEventListener('resize', () => {
                if (lwChart && container.clientWidth > 0) {
                    lwChart.applyOptions({ width: container.clientWidth });
                }
            });
        }

        // สร้างแท่งเทียนจำลองโครงสร้างสวิงจริงของแต่ละไทม์เฟรมเพื่อให้เห็นเส้น Entry 61.8% / SL 78.6% / TP 1:3 ชัดเจนบนกราฟ
        function generateStructureCandles(direction, swingHigh, swingLow, currentPrice, stepSec, mathRes) {
            const candles = [];
            const totalBars = 75;
            const nowSec = Math.floor(Date.now() / 1000) - (totalBars * stepSec);
            const range = swingHigh - swingLow;

            // กำหนดจุดราคาหลักตามโครงสร้างสวิงเพื่อวาดกราฟแท่งเทียนที่สมจริง
            let waypoints;
            if (direction === 'SELL') {
                waypoints = [
                    { idx: 0, price: swingHigh - range * 0.25 },
                    { idx: 12, price: swingHigh }, // จุดยอด Swing High
                    { idx: 28, price: swingLow + range * 0.45 },
                    { idx: 36, price: swingLow + range * 0.60 },
                    { idx: 56, price: swingLow }, // จุดต่ำสุด Swing Low
                    { idx: 68, price: currentPrice + range * 0.08 },
                    { idx: 74, price: currentPrice } // ราคาปัจจุบัน
                ];
            } else {
                waypoints = [
                    { idx: 0, price: swingLow + range * 0.25 },
                    { idx: 12, price: swingLow }, // จุดต่ำสุด Swing Low
                    { idx: 32, price: swingHigh - range * 0.35 },
                    { idx: 52, price: swingHigh }, // จุดยอด Swing High
                    { idx: 66, price: swingHigh - range * 0.45 },
                    { idx: 74, price: currentPrice }
                ];
            }

            let prevClose = waypoints[0].price;

            for (let i = 0; i < totalBars; i++) {
                // หาช่วง Waypoint ปัจจุบัน
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

                // ใส่คลื่นความผันผวนของแท่งเทียน
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

        // ฟังก์ชันวาดเส้น Entry 61.8%, SL 78.6%, TP1 (1:2), TP2 (1:3) ลงบนกราฟโหมดที่ 1
        function drawSniperLinesOnChart(direction, swingHigh, swingLow, currentPrice, stepSec, mathRes) {
            if (!lwChart || !candleSeries) {
                initLightweightChart();
            }

            // ลบเส้นเก่าออกก่อน
            activePriceLines.forEach(line => {
                try { candleSeries.removePriceLine(line); } catch (e) {}
            });
            activePriceLines = [];

            // อัปเดตข้อมูลแท่งเทียน
            const candles = generateStructureCandles(direction, swingHigh, swingLow, currentPrice, stepSec, mathRes);
            candleSeries.setData(candles);

            // ขีดเส้นที่ 1: ENTRY (Fib 61.8%) - สีฟ้าเด่นชัด
            const lineEntry = candleSeries.createPriceLine({
                price: mathRes.entryNum,
                color: '#06b6d4',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: `🎯 จุดเข้า ENTRY (Fib 61.8% - ${direction})`
            });

            // ขีดเส้นที่ 2: STOP LOSS (Fib 78.6%) - สีแดง
            const lineSL = candleSeries.createPriceLine({
                price: mathRes.slNum,
                color: '#f43f5e',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: `🛑 STOP LOSS (Fib 78.6%)`
            });

            // ขีดเส้นที่ 3: TAKE PROFIT 1 (RR 1:2) - สีเขียว
            const lineTP1 = candleSeries.createPriceLine({
                price: mathRes.tp1Num,
                color: '#10b981',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `💰 TP 1 (RR 1:2)`
            });

            // ขีดเส้นที่ 4: TAKE PROFIT 2 (RR 1:3) - สีทอง
            const lineTP2 = candleSeries.createPriceLine({
                price: mathRes.tp2Num,
                color: '#f59e0b',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: `🚀 TP 2 เป้าหลัก (RR 1:3)`
            });

            // ขีดเส้นประบอกขอบเขต Swing High & Swing Low
            const lineHigh = candleSeries.createPriceLine({
                price: swingHigh,
                color: '#64748b',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: `Swing High (0%/100%)`
            });

            const lineLow = candleSeries.createPriceLine({
                price: swingLow,
                color: '#64748b',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: `Swing Low (100%/0%)`
            });

            activePriceLines.push(lineEntry, lineSL, lineTP1, lineTP2, lineHigh, lineLow);

            // ปรับ Autoscale เพื่อให้หน้าจอมองเห็นครบทั้งเส้น Entry, SL, และ TP2 ทันที
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
            if (lwChart) {
                lwChart.timeScale().fitContent();
            }
        }

        // ==========================================
        // 4. ระบบสลับโหมดกราฟ (โหมด 1: AI Sniper vs โหมด 2: TradingView Studio)
        // ==========================================
        function switchChartMode(mode) {
            currentChartMode = mode;
            const sniperWrap = document.getElementById('sniper-chart-wrapper');
            const tvWrap = document.getElementById('tv-chart-wrapper');
            const btnSniper = document.getElementById('mode-btn-sniper');
            const btnTv = document.getElementById('mode-btn-tv');

            if (mode === 'sniper') {
                sniperWrap.classList.remove('hidden');
                tvWrap.classList.add('hidden');
                btnSniper.className = "py-2.5 px-4 rounded-xl text-xs font-extrabold transition flex items-center justify-center gap-2 bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow-lg shadow-amber-500/20";
                btnTv.className = "py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 bg-slate-950 text-slate-300 border border-slate-800 hover:border-amber-500/50";
                
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
                btnTv.className = "py-2.5 px-4 rounded-xl text-xs font-extrabold transition flex items-center justify-center gap-2 bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow-lg shadow-amber-500/20";
                btnSniper.className = "py-2.5 px-4 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 bg-slate-950 text-slate-300 border border-slate-800 hover:border-amber-500/50";

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
                "width": "100%",
                "height": "540",
                "symbol": "OANDA:XAUUSD",
                "interval": intervalCode,
                "timezone": "Asia/Bangkok",
                "theme": "dark",
                "style": "1",
                "locale": "th",
                "toolbar_bg": "#05080f",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "studies": [
                    "RSI@tv-basicstudies"
                ],
                "container_id": "tradingview_studio_chart"
            });
        }

        // ==========================================
        // 5. การเลือกไทม์เฟรมและอัปเดตหน้าเว็บทั้งหมด
        // ==========================================
        function updateDashboardAndChart(calcDir, swingHigh, swingLow, cfg) {
            const mathRes = calculateSniperMath(calcDir, swingHigh, swingLow);

            // อัปเดตตัวเลขในการ์ดขวา
            document.getElementById('val-entry').innerText = '$' + mathRes.entry;
            document.getElementById('val-sl').innerText = '$' + mathRes.sl;
            document.getElementById('val-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('val-tp2').innerText = '$' + mathRes.tp2;

            // อัปเดตตัวเลขแถบด้านบนกราฟ
            document.getElementById('top-entry').innerText = '$' + mathRes.entry;
            document.getElementById('top-sl').innerText = '$' + mathRes.sl;
            document.getElementById('top-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('top-tp2').innerText = '$' + mathRes.tp2;

            // อัปเดตระยะ Risk / Reward
            document.getElementById('val-risk-pts').innerText = `Risk: -$${mathRes.riskDollar}`;
            document.getElementById('val-tp1-pts').innerText = `+$${mathRes.reward1Dollar} (1:2)`;
            document.getElementById('val-tp2-pts').innerText = `+$${mathRes.reward2Dollar} (1:3)`;
            document.getElementById('setup-swing-info').innerText = `High $${swingHigh.toFixed(2)} ➔ Low $${swingLow.toFixed(2)}`;

            const orderBadge = document.getElementById('setup-order-badge');
            if (cfg && cfg.isSideway) {
                orderBadge.innerText = '⏸️ NO TRADE (ไซด์เวย์)';
                orderBadge.className = 'px-3 py-1.5 rounded-xl text-xs font-black bg-yellow-500 text-slate-950';
            } else if (calcDir === 'SELL') {
                orderBadge.innerText = '🔻 SELL LIMIT @ 61.8%';
                orderBadge.className = 'px-3 py-1.5 rounded-xl text-xs font-black bg-rose-500 text-white shadow-lg shadow-rose-500/30';
            } else {
                orderBadge.innerText = '🟢 BUY LIMIT @ 61.8%';
                orderBadge.className = 'px-3 py-1.5 rounded-xl text-xs font-black bg-emerald-500 text-slate-950 shadow-lg shadow-emerald-500/30';
            }

            // วาดเส้นลงบนกราฟโหมดที่ 1 อัตโนมัติ
            const stepSec = cfg ? cfg.stepSec : 3600;
            const curPrice = cfg ? cfg.currentPrice : ((swingHigh + swingLow) / 2);
            drawSniperLinesOnChart(calcDir, swingHigh, swingLow, curPrice, stepSec, mathRes);
        }

        function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const cfg = timeframeConfigs[tfKey];
            if (!cfg) return;

            // อัปเดตสไตล์ปุ่ม Timeframe
            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn py-2.5 px-3 rounded-xl text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:border-amber-500/50 hover:text-slate-200 transition";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn py-2.5 px-3 rounded-xl text-xs font-extrabold bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 border border-amber-300 shadow-lg shadow-amber-500/20 transition";
            }

            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            document.getElementById('chart-tf-indicator').innerText = 'กราฟ: ' + cfg.label;

            const structEl = document.getElementById('tf-structure-badge');
            structEl.innerText = cfg.structure;
            structEl.className = 'px-2.5 py-1 rounded-md font-bold ' + cfg.structureClass;

            document.getElementById('tf-volatility').innerText = cfg.volatility;
            
            const biasEl = document.getElementById('tf-bias-text');
            biasEl.innerText = cfg.biasText;
            biasEl.className = 'font-extrabold text-xs ' + cfg.biasColor;

            const warnEl = document.getElementById('sideway-warning');
            if (cfg.isSideway) {
                warnEl.classList.remove('hidden');
            } else {
                warnEl.classList.add('hidden');
            }

            document.getElementById('setup-reason').innerText = cfg.reason;

            // ซิงค์ค่าลงในกล่อง Custom Swing
            document.getElementById('custom-dir').value = cfg.calcDir;
            document.getElementById('custom-high').value = cfg.swingHigh;
            document.getElementById('custom-low').value = cfg.swingLow;

            // อัปเดตตัวเลขและขีดเส้นบนกราฟโหมดที่ 1
            updateDashboardAndChart(cfg.calcDir, cfg.swingHigh, cfg.swingLow, cfg);

            // ถ้าเปิดโหมดที่ 2 อยู่ ให้ซิงค์กราฟ TradingView ตามด้วย
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
                alert('กรุณากรอกค่า Swing High ให้มากกว่า Swing Low ครับ');
                return;
            }

            const baseCfg = timeframeConfigs[currentTfKey];
            updateDashboardAndChart(dir, high, low, {
                isSideway: false,
                stepSec: baseCfg.stepSec,
                currentPrice: (high + low) / 2
            });

            document.getElementById('setup-reason').innerText = `อัปเดตเส้นบนกราฟตามสวิงที่คุณกำหนดเอง (${dir}): จุดเข้า 61.8%, จุดตัดขาดทุน 78.6% และเป้าทำกำไร RR 1:2 / 1:3 ถูกตีเส้นใหม่บนกราฟโหมดที่ 1 เรียบร้อยแล้ว!`;
            
            if (currentChartMode !== 'sniper') {
                switchChartMode('sniper');
            }
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
                    isSelected ? 'bg-amber-500/15 border-amber-500/60' : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`;
                row.onclick = () => selectTimeframe(key);
                row.innerHTML = `
                    <div class="flex items-center gap-2.5">
                        <span class="font-black text-amber-400 w-10 uppercase">${key}</span>
                        <span class="px-2 py-0.5 rounded text-[11px] font-bold ${item.structureClass}">${item.structure}</span>
                    </div>
                    <div class="flex items-center gap-3 text-[11px]">
                        <span class="text-cyan-400 font-bold">เข้า 61.8%: $${lvls.entry}</span>
                        <span class="text-rose-400 font-bold">SL 78.6%: $${lvls.sl}</span>
                        <span class="text-amber-400 font-bold">TP2 (1:3): $${lvls.tp2}</span>
                    </div>
                `;
                list.appendChild(row);
            });
        }

        function copyPrice(elementId) {
            const text = document.getElementById(elementId).innerText.replace('$', '');
            navigator.clipboard.writeText(text);
            const toast = document.getElementById('toast-copy');
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 2000);
        }

        // เริ่มต้นทำงานทันทีเมื่อเปิดหน้าเว็บ (เริ่มที่โหมด 1 และไทม์เฟรม 1H)
        window.addEventListener('DOMContentLoaded', () => {
            const now = new Date();
            document.getElementById('current-date-label').innerText = 'ข้อมูลประจำวันที่: ' + now.toLocaleDateString('th-TH', {
                year: 'numeric', month: 'short', day: 'numeric'
            });
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
