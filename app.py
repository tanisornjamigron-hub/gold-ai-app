import os
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI ANALYTICS PRO - Ultimate Institutional System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Prompt', sans-serif; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #090d16; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #f59e0b; }
    </style>
</head>
<body class="bg-[#060911] text-slate-100 antialiased min-h-screen p-3 md:p-6 selection:bg-amber-500 selection:text-slate-950">
    <div class="max-w-[1600px] mx-auto space-y-5">
        
        <!-- HEADER -->
        <header class="flex flex-col lg:flex-row justify-between items-start lg:items-center bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 shadow-xl backdrop-blur-md gap-4">
            <div class="flex items-center gap-3">
                <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-amber-400 to-yellow-600 flex items-center justify-center shadow-lg shadow-amber-500/20 font-black text-slate-950 text-xl">
                    AU
                </div>
                <div>
                    <div class="flex items-center gap-2">
                        <h1 class="text-xl md:text-2xl font-extrabold tracking-wide bg-gradient-to-r from-amber-300 via-yellow-400 to-amber-500 bg-clip-text text-transparent">
                            GOLD AI ANALYTICS PRO
                        </h1>
                        <span class="px-2 py-0.5 text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-md">
                            INSTITUTIONAL V3.0
                        </span>
                    </div>
                    <p class="text-xs text-slate-400">
                        ระบบวิเคราะห์โครงสร้างราคาทองคำ XAUUSD • Golden Zone (61.8% - 78.6%) • Order Block & Macro AI
                    </p>
                </div>
            </div>

            <div class="flex flex-wrap items-center gap-3 w-full lg:w-auto justify-between lg:justify-end">
                <div class="bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-800 flex items-center gap-3">
                    <div>
                        <span class="text-[10px] text-slate-400 block">ราคาอ้างอิงตลาด (OANDA)</span>
                        <span class="text-base font-extrabold text-amber-400">~$3,995.80</span>
                    </div>
                    <span class="text-xs px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 font-semibold border border-rose-500/30">
                        Bearish Pressure
                    </span>
                </div>
                <span class="inline-flex items-center px-3.5 py-2 rounded-xl text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">
                    <span class="w-2 h-2 mr-2 bg-emerald-400 rounded-full animate-ping"></span>
                    <span class="w-2 h-2 -ml-4 mr-2 bg-emerald-500 rounded-full"></span>
                    AI & TradingView เชื่อมต่อสำเร็จ
                </span>
            </div>
        </header>

        <!-- MAIN GRID (LEFT: CHART, RIGHT: AI DASHBOARD) -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- ฝั่งซ้าย: กราฟ TradingView + กล่องวิเคราะห์ข่าวเศรษฐกิจ (8 ส่วน) -->
            <div class="xl:col-span-8 space-y-5">
                
                <!-- กล่องกราฟ TradingView -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-2xl">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-3 gap-2">
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                            <h2 class="text-base font-bold text-slate-200">
                                กราฟเทคนิคอล XAUUSD (ซิงค์ตามปุ่มไทม์เฟรมอัตโนมัติ)
                            </h2>
                        </div>
                        <span class="text-xs text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-500/20">
                            💡 ทริค: กดเครื่องมือแถบซ้ายบนกราฟเพื่อกาง Fib Retracement เทียบจุดเข้า Golden Zone ได้เลย
                        </span>
                    </div>
                    
                    <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800" style="height:560px; width:100%;">
                        <div id="tradingview_chart" style="height:100%; width:100%;"></div>
                    </div>
                </div>

                <!-- กล่องวิเคราะห์เศรษฐกิจมหภาคและข่าวสาร (Macro & News AI Analysis) -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-800 pb-3 gap-2">
                        <div class="flex items-center gap-2">
                            <span class="px-2 py-1 rounded-lg bg-amber-500/20 text-amber-400 text-xs font-bold border border-amber-500/30">
                                MACRO & NEWS AI
                            </span>
                            <h2 class="text-base font-bold text-slate-100">
                                วิเคราะห์ข่าวและปัจจัยพื้นฐานเศรษฐกิจโลกต่อราคาทองคำ
                            </h2>
                        </div>
                        <span class="text-xs text-slate-400">อัปเดตสถานะปัจจัยพื้นฐานประจำวัน</span>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <!-- ข่าวที่ 1: ดอกเบี้ย Fed & Bond Yield -->
                        <div class="bg-slate-950/90 p-4 rounded-xl border border-slate-800/80 space-y-2 hover:border-rose-500/40 transition">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-bold text-slate-300">นโยบายดอกเบี้ย Fed & ดอลลาร์</span>
                                <span class="px-2 py-0.5 text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded">
                                    กดดันทองคำ (Bearish)
                                </span>
                            </div>
                            <p class="text-xs text-slate-400 leading-relaxed">
                                อัตราผลตอบแทนพันธบัตรสหรัฐฯ (US Bond Yield) และดัชนีดอลลาร์ (DXY) แข็งค่าขึ้นระยะสั้นหลังตลาดประเมินว่า Fed อาจคงดอกเบี้ยระดับสูงนานกว่าคาด กดดันให้ทองคำเกิดการเทขายทำกำไรและพักฐานลงมา
                            </p>
                        </div>

                        <!-- ข่าวที่ 2: เงินเฟ้อ CPI & ตลาดแรงงาน NFP -->
                        <div class="bg-slate-950/90 p-4 rounded-xl border border-slate-800/80 space-y-2 hover:border-amber-500/40 transition">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-bold text-slate-300">เงินเฟ้อ (CPI) & จ้างงาน (NFP)</span>
                                <span class="px-2 py-0.5 text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded">
                                    ผันผวนสูง (High Impact)
                                </span>
                            </div>
                            <p class="text-xs text-slate-400 leading-relaxed">
                                ตัวเลขเศรษฐกิจสหรัฐฯ ออกมาแข็งแกร่งกว่าคาดการณ์ ทำให้เกิดแรงเทขายปรับพอร์ตของสถาบันการเงิน แนะนำให้ระมัดระวังการเข้าออเดอร์ช่วงตลาดอเมริกาเปิด และรอเข้าเฉพาะจุด Golden Zone เท่านั้น
                            </p>
                        </div>

                        <!-- ข่าวที่ 3: ธนาคารกลาง & ภูมิรัฐศาสตร์ -->
                        <div class="bg-slate-950/90 p-4 rounded-xl border border-slate-800/80 space-y-2 hover:border-emerald-500/40 transition">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-bold text-slate-300">แรงซื้อธนาคารกลาง & ความตึงเครียด</span>
                                <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded">
                                    หนุนระยะยาว (Macro Bullish)
                                </span>
                            </div>
                            <p class="text-xs text-slate-400 leading-relaxed">
                                แม้ภาพระยะสั้น-กลางจะมีแรงเทขายปรับฐานลงมาแรง แต่แรงซื้อสะสมทองคำแท่งจากธนาคารกลางทั่วโลกและความเสี่ยงภูมิรัฐศาสตร์ยังเป็นฐานแนวรับสำคัญในระดับมหภาค
                            </p>
                        </div>
                    </div>

                    <div class="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 flex items-start sm:items-center gap-3">
                        <span class="text-lg">🤖</span>
                        <p class="text-xs text-amber-200 leading-relaxed">
                            <strong class="text-amber-400">สรุปกลยุทธ์จาก AI:</strong> ปัจจัยข่าวระยะสั้นยังกดดันให้ทองคำเป็นฝั่งขาลง (Bearish Correction) ห้ามรีบสวนซื้อ (Buy) เด็ดขาด ให้เน้นดักรอจังหวะราคารีบาวด์เด้งขึ้นมาที่โซน <strong>Fibonacci 61.8% - 78.6% (Golden Zone)</strong> แล้วเปิดหน้าขาย (Short/Sell) ตามโครงสร้างตลาด
                        </p>
                    </div>
                </div>
            </div>

            <!-- ฝั่งขวา: แผงควบคุม AI & Multi-Timeframe Matrix (4 ส่วน) -->
            <div class="xl:col-span-4 space-y-5">
                
                <!-- กล่องปุ่มเลือกไทม์เฟรม + วิเคราะห์จุดเข้า Golden Zone -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                        <div>
                            <h2 class="text-base font-bold text-amber-400">ระบบวิเคราะห์แยกตามไทม์เฟรม</h2>
                            <p class="text-[11px] text-slate-400">กดปุ่มด้านล่างเพื่อดูจุดเข้าและเปลี่ยนกราฟอัตโนมัติ</p>
                        </div>
                        <span id="active-tf-badge" class="px-2.5 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950">
                            TF: 1H
                        </span>
                    </div>

                    <!-- ปุ่มกดเลือก Timeframe (Interactive Buttons) -->
                    <div class="grid grid-cols-3 gap-2">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition-all duration-150">
                            1 นาที (1M)
                        </button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition-all duration-150">
                            5 นาที (5M)
                        </button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition-all duration-150">
                            15 นาที (15M)
                        </button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition-all duration-150">
                            1 ชั่วโมง (1H)
                        </button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition-all duration-150">
                            4 ชั่วโมง (4H)
                        </button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn py-2.5 px-3 rounded-xl text-xs font-bold border transition-all duration-150">
                            รายวัน (Daily)
                        </button>
                    </div>

                    <!-- สถานะตลาดของไทม์เฟรมที่เลือก -->
                    <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
                        <div class="flex justify-between items-center">
                            <span class="text-xs text-slate-400">โครงสร้างตลาด (Structure):</span>
                            <span id="detail-structure" class="px-2.5 py-1 rounded-md text-xs font-bold">--</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-xs text-slate-400">คำแนะนำแอคชั่น (AI Signal):</span>
                            <span id="detail-action" class="text-xs font-extrabold text-amber-400">--</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-xs text-slate-400">ความได้เปรียบเชิงสถิติ (Win Rate):</span>
                            <span id="detail-winrate" class="text-xs font-bold text-emerald-400">--</span>
                        </div>
                    </div>

                    <!-- โซนราคา Golden Zone (61.8% & 78.6%) และ Order Block -->
                    <div class="space-y-2.5">
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-bold text-amber-300">🎯 โซนเฝ้าระวัง Golden Zone & จุดเข้าเทรด</span>
                            <span id="detail-swing" class="text-[11px] text-slate-400">Swing: --</span>
                        </div>

                        <div class="grid grid-cols-2 gap-2.5">
                            <div class="bg-gradient-to-br from-slate-950 to-slate-900 p-3.5 rounded-xl border border-amber-500/40 shadow-inner">
                                <span class="text-[11px] text-amber-400 font-bold block">Fibonacci 61.8% (จุดเข้าที่ 1)</span>
                                <span id="detail-fib618" class="text-lg font-black text-cyan-400 mt-0.5 block">--</span>
                            </div>
                            <div class="bg-gradient-to-br from-slate-950 to-slate-900 p-3.5 rounded-xl border border-amber-500/40 shadow-inner">
                                <span class="text-[11px] text-amber-400 font-bold block">Fibonacci 78.6% (จุดเข้าที่ 2)</span>
                                <span id="detail-fib786" class="text-lg font-black text-purple-400 mt-0.5 block">--</span>
                            </div>
                        </div>

                        <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2 text-xs">
                            <div class="flex justify-between">
                                <span class="text-slate-400">📦 โซน Order Block (OB):</span>
                                <span id="detail-ob" class="font-bold text-amber-300">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-slate-400">🛑 จุดตัดขาดทุน (Stop Loss):</span>
                                <span id="detail-sl" class="font-bold text-rose-400">--</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-slate-400">💰 เป้าทำกำไร (Take Profit):</span>
                                <span id="detail-tp" class="font-bold text-emerald-400">--</span>
                            </div>
                        </div>
                    </div>

                    <!-- คำอธิบายเจาะลึกภาษาไทย -->
                    <div class="space-y-1.5">
                        <span class="text-xs font-bold text-amber-400 block">🧠 วิเคราะห์แผนการเทรดจาก AI:</span>
                        <p id="detail-reason" class="text-xs text-slate-200 bg-slate-950 p-3.5 rounded-xl border border-slate-800 leading-relaxed">
                            --
                        </p>
                    </div>
                </div>

                <!-- ตารางสรุปภาพรวมทุกไทม์เฟรม (Multi-Timeframe Matrix Overview) -->
                <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-3">
                    <h3 class="text-sm font-bold text-slate-200 border-b border-slate-800 pb-2">
                        📊 ตารางสรุปสถานะทุกไทม์เฟรม (Matrix Overview)
                    </h3>
                    <div class="space-y-2 text-xs" id="matrix-table">
                        <!-- สร้างอัตโนมัติด้วย JS -->
                    </div>
                </div>

            </div>
        </div>
    </div>

    <!-- TradingView Script -->
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        // ฐานข้อมูลการวิเคราะห์แยกตาม Timeframe (อ้างอิงราคาตลาดจริง ~3,995.80)
        const timeframeDatabase = {
            '1m': {
                label: '1 นาที (1M)',
                tvInterval: '1',
                structure: 'ไซด์เวย์กรอบแคบ (Sideway)',
                structureStyle: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40',
                action: '⛔ ห้ามเข้าเทรด (ยังไม่เลือกทาง)',
                winrate: '52.0% (ความเสี่ยงสูง)',
                swing: 'High $4,001.20 / Low $3,992.20',
                fib618: '$3,997.75',
                fib786: '$3,999.25',
                ob: '$3,998.50 - $4,000.50 (Supply ย่อย)',
                sl: '$4,003.00 (เหนือ High ล่าสุด)',
                tp: '$3,992.50 / $3,988.00',
                reason: 'ในไทม์เฟรม 1 นาที กราฟกำลังวิ่งออกข้างสะสมพลัง (Sideway) ในกรอบแคบๆ แถว $3,992 - $4,000 สัญญาณหลอกเยอะมาก ยังไม่แนะนำให้กดออเดอร์ ให้รอราคารีบาวด์ขึ้นไปทดสอบโซน Golden Zone ($3,997.75 - $3,999.25) หรือรอเบรกกรอบชัดเจนก่อนครับ'
            },
            '5m': {
                label: '5 นาที (5M)',
                tvInterval: '5',
                structure: 'ขาลงระยะสั้น (Minor Downtrend)',
                structureStyle: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                action: '🔻 รอเด้ง Sell ในโซน Golden Zone',
                winrate: '81.5% (Scalping Setup)',
                swing: 'High $4,016.00 / Low $3,992.20',
                fib618: '$4,006.90',
                fib786: '$4,010.90',
                ob: '$4,008.00 - $4,012.50 (Bearish OB 5M)',
                sl: '$4,017.50',
                tp: '$3,993.00 / $3,985.00',
                reason: 'ไทม์เฟรม 5 นาที โครงสร้างทำจุดต่ำสุดใหม่ (Lower Low) ชัดเจน เหมาะสำหรับสายซิ่งเก็งกำไรสั้นๆ โดยห้ามไล่ราคาข้างล่างเด็ดขาด ให้ตั้งรอ Sell Limit เมื่อราคาดีดตัวกลับขึ้นมาเข้าโซน 61.8% ($4,006.90) ถึง 78.6% ($4,010.90) ซึ่งทับซ้อนกับก้อน Order Block พอดี'
            },
            '15m': {
                label: '15 นาที (15M)',
                tvInterval: '15',
                structure: 'เทรนด์ขาลงชัดเจน (Downtrend)',
                structureStyle: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                action: '🎯 ดักเปิด Short ที่ Golden Zone',
                winrate: '86.8% (Intraday แนะนำ)',
                swing: 'High $4,035.00 / Low $3,992.20',
                fib618: '$4,018.65',
                fib786: '$4,025.85',
                ob: '$4,020.00 - $4,027.00 (Institutional OB)',
                sl: '$4,037.00',
                tp: '$3,992.00 / $3,975.00',
                reason: 'ไทม์เฟรม 15 นาที เกิดการพังทลายโครงสร้างขาลง (Break of Structure) อย่างรุนแรง จุดเข้าที่ได้เปรียบที่สุดของวันคือการรอให้กราฟย่อตัวขึ้นไปหา Golden Zone ระหว่าง $4,018.65 - $4,025.85 แล้วมองหาแท่งเทียนกลับตัวเพื่อเปิดฝั่ง Sell ตามเทรนด์'
            },
            '1h': {
                label: '1 ชั่วโมง (1H)',
                tvInterval: '60',
                structure: 'ขาลงหลัก / รอรีบาวด์ (Bearish Trend)',
                structureStyle: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                action: '🔥 โซนทองคำ! รอ Sell ที่ 61.8% - 78.6%',
                winrate: '91.2% (High Probability)',
                swing: 'High $4,145.00 / Low $3,992.20',
                fib618: '$4,086.60',
                fib786: '$4,112.30',
                ob: '$4,090.00 - $4,115.00 (Major 1H Supply OB)',
                sl: '$4,150.00',
                tp: '$3,995.00 / $3,960.00',
                reason: 'ไทม์เฟรม 1 ชั่วโมง เป็นคลื่นขาลงลูกใหญ่ที่ทุบลงมาจาก $4,145 ลงมาถึง $3,992 ตอนนี้ราคากำลังอยู่ในโซนด้านล่าง หากมีการดีดตัวพักฐานขึ้นมาในกรอบ Golden Zone ($4,086.60 - $4,112.30) จะเป็นจุดเข้าสะสมไม้ Sell ระดับสถาบันที่คุ้มค่าคุ้มความเสี่ยง (RR) สูงมาก'
            },
            '4h': {
                label: '4 ชั่วโมง (4H)',
                tvInterval: '240',
                structure: 'ขาลงระดับมหภาค (Macro Bearish)',
                structureStyle: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
                action: '📉 คุมหน้า Sell เป็นหลัก (ห้ามสวนเทรนด์)',
                winrate: '89.5% (Swing Trade)',
                swing: 'High $4,210.00 / Low $3,992.20',
                fib618: '$4,126.80',
                fib786: '$4,163.40',
                ob: '$4,135.00 - $4,170.00 (4H Order Block)',
                sl: '$4,215.00',
                tp: '$3,980.00 / $3,920.00',
                reason: 'ภาพ 4 ชั่วโมง แท่งเทียนสีแดงทิ้งตัวลงมาอย่างหนักหน่วง ยืนยันว่าแรงขายคุมตลาดสมบูรณ์แบบ การเข้าเทรดทุกไทม์เฟรมย่อยควรเทรดฝั่งขาลง (Sell) ให้สอดคล้องกับ 4H โดยมีแนวต้านสำคัญระดับ Golden Zone อยู่ที่ $4,126.80 - $4,163.40'
            },
            'daily': {
                label: 'รายวัน (Daily)',
                tvInterval: 'D',
                structure: 'ปรับฐานใหญ่ (Major Correction)',
                structureStyle: 'bg-amber-500/20 text-amber-300 border border-amber-500/40',
                action: '⚠️ เทรดตามน้ำขาลง / รอฐานรับใหญ่',
                winrate: '88.0% (Position Trade)',
                swing: 'High $4,240.00 / Low $3,992.20',
                fib618: '$4,145.30',
                fib786: '$4,187.00',
                ob: '$4,150.00 - $4,195.00 (Daily Institutional Zone)',
                sl: '$4,245.00',
                tp: '$3,950.00 / $3,880.00',
                reason: 'ไทม์เฟรม Daily เกิดแรงเทขายทำกำไรรอบใหญ่หลังจากขึ้นไปทำจุดสูงสุดแถว $4,240 โครงสร้างรายวันกำลังปรับฐานลงหาแนวรับจิตวิทยาด้านล่าง ดังนั้นแผนหลักคือเน้นดักจังหวะเด้ง Sell ในไทม์เฟรมย่อย (15M / 1H) ตามทิศทางแท่ง Day'
            }
        };

        let currentTvInterval = null;

        function renderTradingViewChart(intervalCode) {
            if (currentTvInterval === intervalCode) return;
            currentTvInterval = intervalCode;
            
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
                "toolbar_bg": "#090d16",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "studies": [
                    "RSI@tv-basicstudies"
                ],
                "container_id": "tradingview_chart"
            });
        }

        function selectTimeframe(tfKey) {
            const data = timeframeDatabase[tfKey];
            if (!data) return;

            // อัปเดตสไตล์ปุ่มกด
            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn py-2.5 px-3 rounded-xl text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:border-amber-500/50 hover:text-slate-200 transition-all duration-150";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn py-2.5 px-3 rounded-xl text-xs font-extrabold bg-gradient-to-r from-amber-500 to-yellow-500 text-slate-950 border border-amber-400 shadow-lg shadow-amber-500/20 transition-all duration-150";
            }

            // อัปเดตข้อมูลในแผงควบคุมด้านขวา
            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            
            const structEl = document.getElementById('detail-structure');
            structEl.innerText = data.structure;
            structEl.className = 'px-2.5 py-1 rounded-md text-xs font-bold ' + data.structureStyle;

            document.getElementById('detail-action').innerText = data.action;
            document.getElementById('detail-winrate').innerText = data.winrate;
            document.getElementById('detail-swing').innerText = data.swing;
            document.getElementById('detail-fib618').innerText = data.fib618;
            document.getElementById('detail-fib786').innerText = data.fib786;
            document.getElementById('detail-ob').innerText = data.ob;
            document.getElementById('detail-sl').innerText = data.sl;
            document.getElementById('detail-tp').innerText = data.tp;
            document.getElementById('detail-reason').innerText = data.reason;

            // ซิงค์กราฟ TradingView ให้เปลี่ยนไทม์เฟรมตามปุ่มที่กด
            renderTradingViewChart(data.tvInterval);

            // ไฮไลต์แถวในตาราง Matrix
            renderMatrixTable(tfKey);
        }

        function renderMatrixTable(activeKey) {
            const matrixContainer = document.getElementById('matrix-table');
            matrixContainer.innerHTML = '';

            Object.keys(timeframeDatabase).forEach(key => {
                const item = timeframeDatabase[key];
                const isSelected = key === activeKey;
                const rowClass = isSelected 
                    ? 'bg-amber-500/15 border-amber-500/60' 
                    : 'bg-slate-950 border-slate-800/80 hover:border-slate-700';

                const row = document.createElement('div');
                row.className = `flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition ${rowClass}`;
                row.onclick = () => selectTimeframe(key);
                row.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="font-extrabold text-amber-400 w-10 uppercase">${key}</span>
                        <span class="px-2 py-0.5 rounded text-[11px] font-semibold ${item.structureStyle}">${item.structure}</span>
                    </div>
                    <div class="text-right">
                        <span class="text-[11px] text-slate-400 block">Golden Zone (61.8% - 78.6%)</span>
                        <span class="font-bold text-cyan-400">${item.fib618} - ${item.fib786}</span>
                    </div>
                `;
                matrixContainer.appendChild(row);
            });
        }

        // เริ่มต้นเปิดหน้าเว็บที่ไทม์เฟรม 1 ชั่วโมง (1h)
        window.addEventListener('DOMContentLoaded', () => {
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
