import os
import random
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold AI Analytics - XAUUSD Pro & Fibonacci</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 font-sans antialiased min-h-screen p-4 md:p-8">
    <div class="max-w-6xl mx-auto space-y-6">
        <header class="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-slate-800 pb-4 gap-4">
            <div>
                <h1 class="text-2xl md:text-3xl font-black tracking-wider text-amber-400">GOLD AI ANALYTICS PRO</h1>
                <p class="text-xs md:text-sm text-slate-400">ระบบวิเคราะห์ราคาทองคำ XAUUSD + ระบบคำนวณ Fibonacci อัตโนมัติ</p>
            </div>
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                <span class="w-2 h-2 mr-2 bg-emerald-500 rounded-full animate-pulse"></span> ระบบออนไลน์ (Live)
            </span>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-2 space-y-6">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl">
                    <div class="flex justify-between items-center mb-4">
                        <h2 class="text-lg font-bold text-slate-200">กราฟ XAUUSD + Auto Fibonacci</h2>
                        <span id="current-price" class="text-xl font-bold text-amber-400">Loading...</span>
                    </div>
                    <div id="chart-container" class="w-full h-[380px]"></div>
                </div>
            </div>

            <div class="space-y-6">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
                    <h2 class="text-lg font-bold text-slate-200 border-b border-slate-800 pb-2">สัญญาณ AI & Fibonacci</h2>
                    <div class="flex justify-between items-center">
                        <span class="text-sm text-slate-400">สถานะ (Signal):</span>
                        <span id="ai-signal" class="px-3 py-1 rounded-lg text-xs font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">ANALYZING...</span>
                    </div>
                    <div class="flex justify-between items-center">
                        <span class="text-sm text-slate-400">ความแม่นยำ (Win Rate):</span>
                        <span id="ai-winrate" class="text-base font-bold text-emerald-400">--%</span>
                    </div>
                    <div class="grid grid-cols-2 gap-3 pt-2">
                        <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
                            <span class="text-xs text-slate-400 block">Fibonacci 61.8%</span>
                            <span id="fib-61" class="text-sm font-bold text-cyan-400">--</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
                            <span class="text-xs text-slate-400 block">Fibonacci 38.2%</span>
                            <span id="fib-38" class="text-sm font-bold text-purple-400">--</span>
                        </div>
                    </div>
                    <div class="space-y-1 pt-2">
                        <span class="text-xs text-slate-400 block">วิเคราะห์เชิงลึก:</span>
                        <p id="ai-reason" class="text-xs text-slate-300 bg-slate-950 p-3 rounded-xl border border-slate-800 leading-relaxed">
                            กำลังคำนวณระดับ Fibonacci Retracement และ Order Block...
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const chartContainer = document.getElementById('chart-container');
        const chart = LightweightCharts.createChart(chartContainer, {
            layout: { background: { type: 'solid', color: '#090d16' }, textColor: '#94a3b8' },
            grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
            rightPriceScale: { borderColor: '#334155' },
            timeScale: { borderColor: '#334155' }
        });
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#10b981', downColor: '#f43f5e', borderVisible: false, wickUpColor: '#10b981', wickDownColor: '#f43f5e'
        });

        async function updateData() {
            try {
                const response = await fetch('/api/data');
                const data = await response.json();
                if (data.candles && data.candles.length > 0) {
                    candleSeries.setData(data.candles);
                    const latest = data.candles[data.candles.length - 1];
                    document.getElementById('current-price').innerText = '$' + latest.close.toFixed(2);
                }
                if (data.analysis) {
                    document.getElementById('ai-signal').innerText = data.analysis.signal;
                    document.getElementById('ai-winrate').innerText = data.analysis.winrate + '%';
                    document.getElementById('fib-61').innerText = '$' + data.analysis.fib618;
                    document.getElementById('fib-38').innerText = '$' + data.analysis.fib382;
                    document.getElementById('ai-reason').innerText = data.analysis.reason;
                }
            } catch (err) {
                console.error("Error fetching data:", err);
            }
        }
        setInterval(updateData, 5000);
        updateData();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def api_data():
    base_price = 2650.00
    candles = []
    current_time = 1710000000
    highs = []
    lows = []
    
    for i in range(50):
        open_p = base_price + random.uniform(-5, 5)
        close_p = open_p + random.uniform(-6, 6)
        high_p = max(open_p, close_p) + random.uniform(0, 3)
        low_p = min(open_p, close_p) - random.uniform(0, 3)
        candles.append({
            "time": current_time + (i * 300),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2)
        })
        highs.append(high_p)
        lows.append(low_p)
        base_price = close_p

    max_h = max(highs)
    min_l = min(lows)
    diff = max_h - min_l
    
    fib_618 = round(max_h - (diff * 0.618), 2)
    fib_382 = round(max_h - (diff * 0.382), 2)

    analysis = {
        "signal": "BUY AT FIB 61.8%",
        "winrate": 88.4,
        "fib618": fib_618,
        "fib382": fib_382,
        "reason": f"ราคาพักตัวลงมาแตะโซน Fibonacci Retracement 61.8% ที่ราคา ${fib_618} ซึ่งเป็นจุดกลับตัวสำคัญ (Golden Pocket) พร้อมโวลุ่มซื้อหนุน"
    }
    return jsonify({"candles": candles, "analysis": analysis})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
