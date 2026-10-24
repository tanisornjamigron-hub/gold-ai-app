import os
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI ANALYTICS PRO - Sniper 61.8% & RR 1:3 System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Prompt', sans-serif; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #060911; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #f59e0b; }
    </style>
</head>
<body class="bg-[#05080f] text-slate-100 antialiased min-h-screen p-3 md:p-5 selection:bg-amber-500 selection:text-slate-950">
    <div class="max-w-[1650px] mx-auto space-y-4">
        
        <!-- TOP HEADER & DAILY MASTER BIAS -->
        <header class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-2xl backdrop-blur-md">
            <div class="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
                
                <!-- Brand Title -->
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
                                ENTRY 61.8% • SL 78.6% • RR 1:3
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-0.5">
                            ระบบวิเคราะห์จุดเข้าทองคำ XAUUSD แม่นยำสูง • ซิงค์กราฟ TradingView & คำนวณ Risk:Reward อัตโนมัติ
                        </p>
                    </div>
                </div>

                <!-- Master Daily Bias Banner (เห็นชัดทันทีว่าวันนี้เล่นหน้าไหน) -->
                <div class="flex flex-wrap items-center gap-3 w-full xl:w-auto justify-between xl:justify-end">
                    <div class="bg-slate-950 border border-slate-800 px-4 py-2.5 rounded-xl flex items-center gap-3">
                        <span class="text-xs text-slate-400">หน้าเทรดหลักวันนี้ (Daily Bias):</span>
                        <span id="header-master-bias" class="px-3 py-1 rounded-lg text-xs font-extrabold bg-rose-500/20 text-rose-400 border border-rose-500/40 flex items-center gap-1.5">
                            🔻 SELL BIAS (เน้นดักเด้ง Short)
                        </span>
                    </div>

                    <div class="bg-slate-950 border border-slate-800 px-4 py-2.5 rounded-xl flex items-center gap-2">
                        <span class="w-2.5 h-2.5 bg-emerald-400 rounded-full animate-ping"></span>
                        <span class="w-2.5 h-2.5 -ml-5 bg-emerald-500 rounded-full"></span>
                        <span class="text-xs font-bold text-emerald-400">OANDA:XAUUSD (Live)</span>
                    </div>
                </div>
            </div>
        </header>

        <!-- MAIN WORKSPACE GRID -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- ฝั่งซ้าย: กราฟ TradingView + คู่มือกางเส้นจุดเข้าบนกราฟ + ปฏิทินวิเคราะห์ข่าว (7 ส่วน) -->
            <div class="xl:col-span-7 space-y-5">
                
                <!-- กล่องกราฟ TradingView -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-2xl space-y-3">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800/80 pb-3">
                        <div class="flex items-center gap-2">
                            <span class="w-3 h-3 rounded-full bg-amber-400 shadow-sm shadow-amber-400"></span>
                            <h2 class="text-base font-bold text-slate-100">
                                กราฟ TradingView (ซิงค์ตามปุ่ม Timeframe ด้านขวา)
                            </h2>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-[11px] bg-amber-500/15 text-amber-300 px-3 py-1 rounded-lg border border-amber-500/30 font-medium">
                                💡 วิธีโชว์โซนบนกราฟ: กดปุ่ม <strong>Indicators</strong> ด้านบน ➔ พิมพ์ <strong>"Auto Fib Retracement"</strong>
                            </span>
                        </div>
                    </div>

                    <!-- แถบป้ายราคาสำหรับกด Copy ไปวางเส้น Horizontal Line บนกราฟ -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-950 p-2.5 rounded-xl border border-slate-800/90 text-xs">
                        <div onclick="copyPrice('val-entry')" class="cursor-pointer p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 hover:border-cyan-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-cyan-300 block">🎯 จุดเข้า (61.8%)</span>
                                <span id="bar-entry" class="font-black text-cyan-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-cyan-500/20 text-cyan-300 px-1.5 py-0.5 rounded">คัดลอก</span>
                        </div>
                        <div onclick="copyPrice('val-sl')" class="cursor-pointer p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 hover:border-rose-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-rose-300 block">🛑 Stop Loss (78.6%)</span>
                                <span id="bar-sl" class="font-black text-rose-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-rose-500/20 text-rose-300 px-1.5 py-0.5 rounded">คัดลอก</span>
                        </div>
                        <div onclick="copyPrice('val-tp1')" class="cursor-pointer p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 hover:border-emerald-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-emerald-300 block">💰 TP 1 (RR 1:2)</span>
                                <span id="bar-tp1" class="font-black text-emerald-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">คัดลอก</span>
                        </div>
                        <div onclick="copyPrice('val-tp2')" class="cursor-pointer p-2 rounded-lg bg-amber-500/10 border border-amber-500/30 hover:border-amber-400 transition flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-amber-300 block">🚀 TP 2 (RR 1:3)</span>
                                <span id="bar-tp2" class="font-black text-amber-400 text-sm">--</span>
                            </div>
                            <span class="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">คัดลอก</span>
                        </div>
                    </div>

                    <!-- ตัวกราฟ TradingView -->
                    <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800" style="height:560px; width:100%;">
                        <div id="tradingview_chart" style="height:100%; width:100%;"></div>
                    </div>
                </div>

                <!-- กล่องวิเคราะห์เศรษฐกิจมหภาคและตารางข่าว (Macro & Economic Impact) -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-800 pb-3 gap-2">
                        <div class="flex items-center gap-2">
                            <span class="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-400 text-xs font-extrabold border border-amber-500/30">
                                FOREX FACTORY & MACRO AI
                            </span>
                            <h2 class="text-base font-bold text-slate-100">
                                วิเคราะห์ปัจจัยข่าวและระดับความผันผวนของทองคำ
                            </h2>
                        </div>
                        <span id="current-date-display" class="text-xs text-amber-400 font-semibold"></span>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-xs">
                        <!-- สถานะข่าวที่ 1 -->
                        <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200">ดัชนีดอลลาร์ (DXY) & Fed</span>
                                <span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 font-bold text-[10px]">
                                    High Impact (กดดันทอง)
                                </span>
                            </div>
                            <p class="text-slate-400 leading-relaxed">
                                ตลาดกังวลเรื่องอัตราผลตอบแทนพันธบัตรสหรัฐฯ ที่ทรงตัวสูง ส่งผลให้มีแรงเทขายทองคำเมื่อราคาดีดตัวขึ้น (เน้นฝั่ง Sell ได้เปรียบกว่า)
                            </p>
                        </div>

                        <!-- สถานะข่าวที่ 2 (ระดับปานกลาง) -->
                        <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200">สภาพคล่องระหว่างวัน</span>
                                <span class="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 font-bold text-[10px]">
                                    Medium (ผันผวนปานกลาง)
                                </span>
                            </div>
                            <p class="text-slate-400 leading-relaxed">
                                ช่วงตลาดเอเชีย-ลอนดอน ราคาอาจแกว่งตัวสะสมพลังในกรอบ (Sideway) ห้ามไล่ราคาตรงกลางกรอบ ให้ตั้ง Pending Order รอที่ 61.8% เท่านั้น
                            </p>
                        </div>

                        <!-- สถานะข่าวที่ 3 -->
                        <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-slate-200">แผนรับมือตัวเลข CPI / NFP</span>
                                <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold text-[10px]">
                                    Sniper Rule 1:3
                                </span>
                            </div>
                            <p class="text-slate-400 leading-relaxed">
                                หากตัวเลขสหรัฐฯ ออกมาสูงกว่าคาด = ทองคำลงต่อ (เข้าแผน Sell) / หากต่ำกว่าคาด = ทองคำดีดขึ้นแรง ให้คุม Stop Loss ที่ระดับ 78.6% อย่างเคร่งครัด
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
                            <h2 class="text-base font-bold text-amber-400">1. เลือกไทม์เฟรมที่ต้องการเทรด</h2>
                            <p class="text-[11px] text-slate-400">กดปุ่มเพื่อซิงค์กราฟและคำนวณแผน Entry 61.8% / SL 78.6%</p>
                        </div>
                        <span id="active-tf-badge" class="px-3 py-1 rounded-xl text-xs font-black bg-amber-500 text-slate-950 shadow">
                            TF: 1H
                        </span>
                    </div>

                    <!-- ปุ่ม Timeframe 6 ปุ่ม -->
                    <div class="grid grid-cols-3 sm:grid-cols-6 xl:grid-cols-3 gap-2">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">1 นาที (1M)</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">5 นาที (5M)</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">15 นาที (15M)</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">1 ชั่วโมง (1H)</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">4 ชั่วโมง (4H)</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition">รายวัน (Daily)</button>
                    </div>

                    <!-- กล่องแสดงสถานะเทรนด์ & ความผันผวนของไทม์เฟรมที่เลือก -->
                    <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2.5 text-xs">
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">สถานะโครงสร้างตลาด:</span>
                            <span id="tf-structure-badge" class="px-2.5 py-1 rounded-md font-bold">--</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">ระดับความผันผวน (Volatility):</span>
                            <span id="tf-volatility" class="font-bold text-slate-200">--</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">หน้าเล่นที่ได้เปรียบ (Bias):</span>
                            <span id="tf-bias-text" class="font-extrabold text-sm">--</span>
                        </div>
                    </div>
                </div>

                <!-- 2. การ์ดแผนการเทรด SNIPER SETUP (Entry 61.8% | SL 78.6% | TP1 1:2 | TP2 1:3) -->
                <div class="bg-slate-900/90 border border-amber-500/40 rounded-2xl p-5 shadow-2xl space-y-4 relative overflow-hidden">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-amber-400 block">GOLDEN ZONE SNIPER</span>
                            <h2 class="text-lg font-black text-slate-100">2. แผนจุดเข้าเทรด (RR 1:2 & 1:3)</h2>
                        </div>
                        <span id="setup-direction-badge" class="px-3 py-1.5 rounded-xl text-xs font-black">--</span>
                    </div>

                    <!-- แจ้งเตือนกรณี Sideway ห้ามเทรด -->
                    <div id="sideway-warning" class="hidden bg-yellow-500/15 border border-yellow-500/50 rounded-xl p-3.5 text-xs text-yellow-200 space-y-1">
                        <div class="font-extrabold text-yellow-400 text-sm">⚠️ เตือนภัยไซด์เวย์ / ความผันผวนกลางกรอบ!</div>
                        <p>ไทม์เฟรมนี้ราคากำลังวิ่งสะสมพลังออกข้าง (Sideway) แนะนำให้ <strong>"นั่งทับมือ"</strong> รอให้กราฟเบรกเอาต์เลือกทางชัดเจน หรือสลับไปดูจุดเข้าที่ไทม์เฟรม 15M / 1H แทนครับ</p>
                    </div>

                    <!-- ข้อมูล Swing High / Swing Low ที่ใช้วัด Fibonacci -->
                    <div class="flex justify-between items-center bg-slate-950 px-3.5 py-2.5 rounded-xl border border-slate-800 text-xs">
                        <span class="text-slate-400">กรอบสวิงที่ใช้วัด Fib:</span>
                        <span id="setup-swing-range" class="font-bold text-amber-300">--</span>
                    </div>

                    <!-- ตารางการ์ด 4 จุดหลัก: ENTRY, SL, TP1, TP2 -->
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        
                        <!-- จุดเข้า ENTRY (61.8%) -->
                        <div class="bg-gradient-to-br from-cyan-950/50 to-slate-950 p-4 rounded-xl border border-cyan-500/50 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-cyan-300">🎯 จุดเข้า (ENTRY 61.8%)</span>
                                <span class="text-[10px] bg-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded font-bold">ไม้เดียวเน้นๆ</span>
                            </div>
                            <div id="val-entry" class="text-2xl font-black text-cyan-400 tracking-tight">--</div>
                            <p class="text-[11px] text-slate-400">ตั้งรอ Pending Order ที่ระดับ Fib 61.8%</p>
                        </div>

                        <!-- จุดตัดขาดทุน STOP LOSS (78.6%) -->
                        <div class="bg-gradient-to-br from-rose-950/50 to-slate-950 p-4 rounded-xl border border-rose-500/50 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-rose-300">🛑 ตัดขาดทุน (SL 78.6%)</span>
                                <span id="val-risk-pts" class="text-[10px] bg-rose-500/20 text-rose-300 px-2 py-0.5 rounded font-bold">Risk: --</span>
                            </div>
                            <div id="val-sl" class="text-2xl font-black text-rose-400 tracking-tight">--</div>
                            <p class="text-[11px] text-slate-400">ยอมแพ้ทันทีหากราคาหลุด Fib 78.6%</p>
                        </div>

                        <!-- เป้าทำกำไรที่ 1: TP1 (RR 1:2) -->
                        <div class="bg-gradient-to-br from-emerald-950/50 to-slate-950 p-4 rounded-xl border border-emerald-500/50 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-emerald-300">💰 เป้าแรก TP 1 (RR 1:2)</span>
                                <span id="val-tp1-pts" class="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-bold">+-- จุด</span>
                            </div>
                            <div id="val-tp1" class="text-2xl font-black text-emerald-400 tracking-tight">--</div>
                            <p class="text-[11px] text-slate-400">แบ่งปิดกำไร 50% และบังหน้าทุน (BE)</p>
                        </div>

                        <!-- เป้าทำกำไรที่ 2: TP2 (RR 1:3) -->
                        <div class="bg-gradient-to-br from-amber-950/50 to-slate-950 p-4 rounded-xl border border-amber-500/60 space-y-1">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-amber-300">🚀 เป้าหลัก TP 2 (RR 1:3)</span>
                                <span id="val-tp2-pts" class="text-[10px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold">+-- จุด</span>
                            </div>
                            <div id="val-tp2" class="text-2xl font-black text-amber-400 tracking-tight">--</div>
                            <p class="text-[11px] text-slate-400">เป้าทำกำไรเต็มระบบ 3 เท่าของความเสี่ยง</p>
                        </div>
                    </div>

                    <!-- แผนผังจำลองระดับราคา (Visual Price Ladder) เพื่อให้เห็นภาพเทียบกับกราฟ -->
                    <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                        <span class="text-xs font-bold text-slate-300 block">📐 แผนผังลำดับเส้นราคา (เทียบใส่กราฟ TradingView):</span>
                        <div class="relative pt-2 pb-1 space-y-1.5 text-xs font-mono" id="price-ladder-visual">
                            <!-- สร้างอัตโนมัติด้วย JS -->
                        </div>
                    </div>

                    <!-- คำอธิบายแผนการเทรดจาก AI -->
                    <div class="space-y-1">
                        <span class="text-xs font-bold text-amber-400 block">🧠 วิเคราะห์เหตุผลและจังหวะเข้าทำกำไร:</span>
                        <p id="setup-reason" class="text-xs text-slate-200 bg-slate-950 p-3.5 rounded-xl border border-slate-800 leading-relaxed">
                            --
                        </p>
                    </div>
                </div>

                <!-- 3. เครื่องคิดเลขคำนวณ Golden Zone สด (ปรับ Swing High / Low เองได้ตามกราฟจริง) -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-3">
                    <div class="border-b border-slate-800 pb-2">
                        <h3 class="text-sm font-bold text-amber-400">⚡ เครื่องคำนวณจุดเข้า 61.8% & RR 1:3 แบบกำหนดสวิงเอง</h3>
                        <p class="text-[11px] text-slate-400">ใส่ราคา High และ Low จากกราฟจริงเพื่อให้ระบบคำนวณจุดเข้า/SL/TP ให้อัตโนมัติ</p>
                    </div>
                    <div class="grid grid-cols-3 gap-2 text-xs">
                        <div>
                            <label class="text-slate-400 block mb-1">ทิศทางเทรนด์</label>
                            <select id="calc-trend" onchange="runCustomCalc()" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-100 font-bold">
                                <option value="SELL">ขาลง (ดัก Sell)</option>
                                <option value="BUY">ขาขึ้น (ดัก Buy)</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1">Swing High ($)</label>
                            <input type="number" id="calc-high" step="0.1" value="4145.00" oninput="runCustomCalc()" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-100 font-bold">
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1">Swing Low ($)</label>
                            <input type="number" id="calc-low" step="0.1" value="3992.20" oninput="runCustomCalc()" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-100 font-bold">
                        </div>
                    </div>
                    <button onclick="applyCustomToMainCard()" class="w-full py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs rounded-xl transition shadow">
                        🔄 นำค่าที่คำนวณใหม่ไปแสดงบนการ์ดหลักด้านบน
                    </button>
                </div>

                <!-- 4. ตารางสรุปภาพรวมทุกไทม์เฟรม (Multi-Timeframe Matrix) -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-3">
                    <h3 class="text-sm font-bold text-slate-200 border-b border-slate-800 pb-2">
                        📊 สรุปสถานะทั้ง 6 ไทม์เฟรม (Multi-Timeframe Matrix)
                    </h3>
                    <div class="space-y-2 text-xs" id="matrix-overview-list"></div>
                </div>

            </div>
        </div>
    </div>

    <!-- แจ้งเตือนเมื่อคัดลอกราคาสำเร็จ -->
    <div id="toast-copy" class="fixed bottom-5 right-5 hidden bg-emerald-500 text-slate-950 px-4 py-2.5 rounded-xl font-extrabold text-xs shadow-2xl">
        ✅ คัดลอกราคาเรียบร้อย! นำไปวางเส้นบนกราฟได้เลย
    </div>

    <!-- TradingView Widget Script -->
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        // ฟังก์ชันคำนวณคณิตศาสตร์ Fibonacci 61.8%, SL 78.6%, TP1 (1:2), TP2 (1:3)
        function calculateSniperLevels(direction, swingHigh, swingLow) {
            const range = swingHigh - swingLow;
            let entry618, sl786, risk, tp1, tp2;

            if (direction === 'SELL') {
                // เทรนด์ขาลง: วัดจาก High ลงหา Low -> รอเด้งขึ้นไปที่ 61.8% เพื่อ Sell, SL ที่ 78.6%
                entry618 = swingLow + (range * 0.618);
                sl786 = swingLow + (range * 0.786);
                risk = Math.abs(sl786 - entry618); // ระยะความเสี่ยง 1R
                tp1 = entry618 - (risk * 2);      // เป้า 1:2
                tp2 = entry618 - (risk * 3);      // เป้า 1:3
            } else {
                // เทรนด์ขาขึ้น: วัดจาก Low ขึ้นหา High -> รอย่อลงมาที่ 61.8% เพื่อ Buy, SL ที่ 78.6%
                entry618 = swingHigh - (range * 0.618);
                sl786 = swingHigh - (range * 0.786);
                risk = Math.abs(entry618 - sl786); // ระยะความเสี่ยง 1R
                tp1 = entry618 + (risk * 2);      // เป้า 1:2
                tp2 = entry618 + (risk * 3);      // เป้า 1:3
            }

            return {
                entry: entry618.toFixed(2),
                sl: sl786.toFixed(2),
                tp1: tp1.toFixed(2),
                tp2: tp2.toFixed(2),
                riskDollar: risk.toFixed(2),
                reward1Dollar: (risk * 2).toFixed(2),
                reward2Dollar: (risk * 3).toFixed(2)
            };
        }

        // ข้อมูลโครงสร้างราคาแยกตาม Timeframe (อ้างอิงราคาตลาด XAUUSD ปัจจุบัน ~$3,995.80)
        const timeframeConfigs = {
            '1m': {
                label: '1 นาที (1M)',
                tvInterval: '1',
                direction: 'NEUTRAL',
                calcDir: 'SELL',
                swingHigh: 4001.20,
                swingLow: 3992.20,
                structure: 'ไซด์เวย์กรอบแคบ (Sideway)',
                structureClass: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40',
                volatility: 'ผันผวนปานกลาง-ต่ำ (แกว่งในกรอบ)',
                biasText: '🟡 NEUTRAL (นั่งทับมือ ห้ามเทรด)',
                biasColor: 'text-yellow-400',
                isSideway: true,
                reason: 'กราฟ 1 นาทีกำลังวิ่งออกข้างสะสมพลัง (Sideway) กลางกรอบ ไม่มีความได้เปรียบเชิงสถิติ แนะนำให้นั่งทับมือพักการเทรดในไทม์เฟรมนี้ หรือถ้าต้องการตั้งดัก ให้รอที่กรอบบน 61.8% เท่านั้น'
            },
            '5m': {
                label: '5 นาที (5M)',
                tvInterval: '5',
                direction: 'SELL',
                calcDir: 'SELL',
                swingHigh: 4016.00,
                swingLow: 3992.20,
                structure: 'ขาลงระยะสั้น (Minor Downtrend)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนปานกลาง (เหมาะเก็บสั้น)',
                biasText: '🔴 SELL BIAS (รอเด้ง Short ที่ 61.8%)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ไทม์เฟรม 5 นาทีทำโครงสร้าง Lower Low ลงมาชัดเจน แผนคือตั้ง Sell Limit ที่โซน Fib 61.8% ($4,006.91) วาง Stop Loss ที่ระดับ 78.6% ($4,010.91) ความเสี่ยงแคบเพียง $4.00 เพื่อลุ้นเป้า TP 1:2 และ 1:3'
            },
            '15m': {
                label: '15 นาที (15M)',
                tvInterval: '15',
                direction: 'SELL',
                calcDir: 'SELL',
                swingHigh: 4035.00,
                swingLow: 3992.20,
                structure: 'เทรนด์ขาลงชัดเจน (Intraday Bearish)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนกำลังดี (แนะนำเทรดระหว่างวัน)',
                biasText: '🔴 SELL BIAS (ดักทุบที่ 61.8%)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ไทม์เฟรม 15 นาทีเป็นจังหวะ Intraday ที่คมที่สุด รอราคารีบาวด์ขึ้นมาแตะจุด Entry 61.8% ($4,018.65) แล้วตัดขาดทุนทันทีหากทะลุ 78.6% ($4,025.84) เก็บกำไรตามสัดส่วน RR 1:2 ที่ $4,004.27 และ RR 1:3 ที่ $3,997.08'
            },
            '1h': {
                label: '1 ชั่วโมง (1H)',
                tvInterval: '60',
                direction: 'SELL',
                calcDir: 'SELL',
                swingHigh: 4145.00,
                swingLow: 3992.20,
                structure: 'ขาลงหลัก / รอรีบาวด์ (Major Bearish)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนสูง (High Probability Setup)',
                biasText: '🔴 STRONG SELL BIAS (โซนสถาบัน 61.8%)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ไทม์เฟรม 1 ชั่วโมงเกิดแรงเทขายระดับสถาบันจาก $4,145 ลงมาที่ $3,992.20 จุดเข้าไม้เดียวที่คมที่สุดคือการดัก Sell Limit ที่ Fib 61.8% ($4,086.63) โดยมีจุด SL ที่ 78.6% ($4,112.30) และรันเทรนด์ลงไปกินคำใหญ่ระดับ RR 1:3'
            },
            '4h': {
                label: '4 ชั่วโมง (4H)',
                tvInterval: '240',
                direction: 'SELL',
                calcDir: 'SELL',
                swingHigh: 4210.00,
                swingLow: 3992.20,
                structure: 'ขาลงระดับมหภาค (Macro Downtrend)',
                structureClass: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                volatility: 'ผันผวนสูง (Swing Trade)',
                biasText: '🔴 SELL BIAS (ห้ามสวนเทรนด์หลัก)',
                biasColor: 'text-rose-400',
                isSideway: false,
                reason: 'ภาพใหญ่ 4 ชั่วโมงคุมทิศทางขาลงอย่างสมบูรณ์ การย่อตัวขึ้นเป็นเพียงการพักฐานเพื่อลงต่อ โซนดัก Sell รอบใหญ่อยู่ที่ Fib 61.8% ($4,126.80) และวาง SL ที่ 78.6% ($4,163.39)'
            },
            'daily': {
                label: 'รายวัน (Daily)',
                tvInterval: 'D',
                direction: 'SELL',
                calcDir: 'SELL',
                swingHigh: 4240.00,
                swingLow: 3992.20,
                structure: 'ปรับฐานรายวัน (Daily Correction)',
                structureClass: 'bg-amber-500/20 text-amber-300 border border-amber-500/40',
                volatility: 'ผันผวนระดับมหภาค (Position)',
                biasText: '🔴 SELL BIAS (มองลงตามแท่ง Day)',
                biasColor: 'text-amber-400',
                isSideway: false,
                reason: 'แท่งเทียน Daily ทิ้งตัวลงมาแรงหลังจบรอบขาขึ้นด้านบน ทำให้ภาพรวมรายวันเน้นเล่นหน้า Sell เป็นหลัก โดยใช้ไทม์เฟรม 15M และ 1H ในการหาจังหวะเข้าที่ 61.8%'
            }
        };

        let currentInterval = null;
        let currentTfKey = '1h';

        function loadTradingViewWidget(intervalCode) {
            if (currentInterval === intervalCode) return;
            currentInterval = intervalCode;
            const container = document.getElementById('tradingview_chart');
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
                "toolbar_bg": "#05080f",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "studies": [
                    "RSI@tv-basicstudies"
                ],
                "container_id": "tradingview_chart"
            });
        }

        function updateSetupUI(calcDir, high, low, cfg) {
            const res = calculateSniperLevels(calcDir, high, low);

            // อัปเดตตัวเลขในการ์ดหลัก
            document.getElementById('val-entry').innerText = '$' + res.entry;
            document.getElementById('val-sl').innerText = '$' + res.sl;
            document.getElementById('val-tp1').innerText = '$' + res.tp1;
            document.getElementById('val-tp2').innerText = '$' + res.tp2;

            // อัปเดตแถบด้านบนกราฟ
            document.getElementById('bar-entry').innerText = '$' + res.entry;
            document.getElementById('bar-sl').innerText = '$' + res.sl;
            document.getElementById('bar-tp1').innerText = '$' + res.tp1;
            document.getElementById('bar-tp2').innerText = '$' + res.tp2;

            // อัปเดตระยะความเสี่ยงและกำไร ($)
            document.getElementById('val-risk-pts').innerText = `Risk: -$${res.riskDollar}`;
            document.getElementById('val-tp1-pts').innerText = `+$${res.reward1Dollar} (1:2)`;
            document.getElementById('val-tp2-pts').innerText = `+$${res.reward2Dollar} (1:3)`;

            document.getElementById('setup-swing-range').innerText = `High $${high.toFixed(2)} ➔ Low $${low.toFixed(2)}`;

            // ป้ายบอกทิศทางออเดอร์
            const dirBadge = document.getElementById('setup-direction-badge');
            if (cfg && cfg.isSideway) {
                dirBadge.innerText = '⏸️ WAIT / NO TRADE (ไซด์เวย์)';
                dirBadge.className = 'px-3 py-1.5 rounded-xl text-xs font-black bg-yellow-500 text-slate-950';
            } else if (calcDir === 'SELL') {
                dirBadge.innerText = '🔻 SELL LIMIT @ 61.8%';
                dirBadge.className = 'px-3 py-1.5 rounded-xl text-xs font-black bg-rose-500 text-white shadow-lg shadow-rose-500/30';
            } else {
                dirBadge.innerText = '🟢 BUY LIMIT @ 61.8%';
                dirBadge.className = 'px-3 py-1.5 rounded-xl text-xs font-black bg-emerald-500 text-slate-950 shadow-lg shadow-emerald-500/30';
            }

            // สร้างแผนผังลำดับเส้นราคา (Visual Price Ladder)
            const ladder = document.getElementById('price-ladder-visual');
            if (calcDir === 'SELL') {
                ladder.innerHTML = `
                    <div class="flex justify-between items-center p-2 rounded bg-rose-500/15 border-l-4 border-rose-500 text-rose-300">
                        <span>🛑 <strong>STOP LOSS (Fib 78.6%)</strong></span>
                        <span class="font-bold">$${res.sl}</span>
                    </div>
                    <div class="flex justify-between items-center p-2 rounded bg-cyan-500/15 border-l-4 border-cyan-400 text-cyan-300">
                        <span>🎯 <strong>ENTRY SELL (Fib 61.8%)</strong></span>
                        <span class="font-bold">$${res.entry}</span>
                    </div>
                    <div class="flex justify-between items-center p-2 rounded bg-emerald-500/15 border-l-4 border-emerald-400 text-emerald-300">
                        <span>💰 <strong>TAKE PROFIT 1 (RR 1:2)</strong></span>
                        <span class="font-bold">$${res.tp1}</span>
                    </div>
                    <div class="flex justify-between items-center p-2 rounded bg-amber-500/15 border-l-4 border-amber-400 text-amber-300">
                        <span>🚀 <strong>TAKE PROFIT 2 (RR 1:3)</strong></span>
                        <span class="font-bold">$${res.tp2}</span>
                    </div>
                `;
            } else {
                ladder.innerHTML = `
                    <div class="flex justify-between items-center p-2 rounded bg-amber-500/15 border-l-4 border-amber-400 text-amber-300">
                        <span>🚀 <strong>TAKE PROFIT 2 (RR 1:3)</strong></span>
                        <span class="font-bold">$${res.tp2}</span>
                    </div>
                    <div class="flex justify-between items-center p-2 rounded bg-emerald-500/15 border-l-4 border-emerald-400 text-emerald-300">
                        <span>💰 <strong>TAKE PROFIT 1 (RR 1:2)</strong></span>
                        <span class="font-bold">$${res.tp1}</span>
                    </div>
                    <div class="flex justify-between items-center p-2 rounded bg-cyan-500/15 border-l-4 border-cyan-400 text-cyan-300">
                        <span>🎯 <strong>ENTRY BUY (Fib 61.8%)</strong></span>
                        <span class="font-bold">$${res.entry}</span>
                    </div>
                    <div class="flex justify-between items-center p-2 rounded bg-rose-500/15 border-l-4 border-rose-500 text-rose-300">
                        <span>🛑 <strong>STOP LOSS (Fib 78.6%)</strong></span>
                        <span class="font-bold">$${res.sl}</span>
                    </div>
                `;
            }
        }

        function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const cfg = timeframeConfigs[tfKey];
            if (!cfg) return;

            // อัปเดตสไตล์ปุ่ม
            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn py-2.5 px-3 rounded-xl text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:border-amber-500/50 hover:text-slate-200 transition";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn py-2.5 px-3 rounded-xl text-xs font-extrabold bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 border border-amber-300 shadow-lg shadow-amber-500/20 transition";
            }

            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            
            const structBadge = document.getElementById('tf-structure-badge');
            structBadge.innerText = cfg.structure;
            structBadge.className = 'px-2.5 py-1 rounded-md font-bold ' + cfg.structureClass;

            document.getElementById('tf-volatility').innerText = cfg.volatility;
            
            const biasEl = document.getElementById('tf-bias-text');
            biasEl.innerText = cfg.biasText;
            biasEl.className = 'font-extrabold text-xs ' + cfg.biasColor;

            // แสดง/ซ่อน กล่องเตือน Sideway
            const warnBox = document.getElementById('sideway-warning');
            if (cfg.isSideway) {
                warnBox.classList.remove('hidden');
            } else {
                warnBox.classList.add('hidden');
            }

            document.getElementById('setup-reason').innerText = cfg.reason;

            // อัปเดตค่าในช่องเครื่องคิดเลขให้ตรงกับ Timeframe
            document.getElementById('calc-trend').value = cfg.calcDir;
            document.getElementById('calc-high').value = cfg.swingHigh;
            document.getElementById('calc-low').value = cfg.swingLow;

            // คำนวณและแสดงผล Entry 61.8%, SL 78.6%, TP 1:2, TP 1:3
            updateSetupUI(cfg.calcDir, cfg.swingHigh, cfg.swingLow, cfg);

            // ซิงค์กราฟ TradingView
            loadTradingViewWidget(cfg.tvInterval);

            // อัปเดตตาราง Matrix ด้านล่าง
            renderMatrixOverview(tfKey);
        }

        function runCustomCalc() {
            // คำนวณสดเมื่อผู้ใช้ปรับเลข High/Low
        }

        function applyCustomToMainCard() {
            const dir = document.getElementById('calc-trend').value;
            const high = parseFloat(document.getElementById('calc-high').value) || 4100;
            const low = parseFloat(document.getElementById('calc-low').value) || 3990;
            if (high <= low) {
                alert('กรุณาใส่ค่า Swing High ให้มากกว่า Swing Low ครับ');
                return;
            }
            updateSetupUI(dir, high, low, { isSideway: false });
            document.getElementById('setup-reason').innerText = `คำนวณจากสวิงที่คุณกำหนดเอง (${dir}): เข้าที่ 61.8% ตัดขาดทุนที่ 78.6% และล็อกเป้าทำกำไร RR 1:2 และ 1:3 เรียบร้อยแล้ว`;
        }

        function renderMatrixOverview(activeKey) {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';

            Object.keys(timeframeConfigs).forEach(key => {
                const item = timeframeConfigs[key];
                const lvls = calculateSniperLevels(item.calcDir, item.swingHigh, item.swingLow);
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
                        <span class="text-amber-400 font-bold">TP(1:3): $${lvls.tp2}</span>
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
            setTimeout(() => toast.classList.add('hidden'), 2200);
        }

        // แสดงวันที่ปัจจุบันและโหลดไทม์เฟรมเริ่มต้น 1H
        window.addEventListener('DOMContentLoaded', () => {
            const now = new Date();
            document.getElementById('current-date-display').innerText = 'อัปเดตล่าสุด: ' + now.toLocaleDateString('th-TH', {
                year: 'numeric', month: 'short', day: 'numeric'
            });
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
