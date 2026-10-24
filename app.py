import os
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold AI Analytics Pro - XAUUSD</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 font-sans antialiased min-h-screen p-4 md:p-8">
    <div class="max-w-6xl mx-auto space-y-6">
        <header class="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-slate-800 pb-4 gap-4">
            <div>
                <h1 class="text-2xl md:text-3xl font-black tracking-wider text-amber-400">GOLD AI ANALYTICS PRO</h1>
                <p class="text-xs md:text-sm text-slate-400">ระบบวิเคราะห์ราคาทองคำ XAUUSD + Fibonacci Retracement อัจฉริยะ</p>
            </div>
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                <span class="w-2 h-2 mr-2 bg-emerald-500 rounded-full animate-pulse"></span> ระบบออนไลน์ (Live)
            </span>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-2 space-y-6">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl">
                    <div class="flex justify-between items-center mb-4">
                        <h2 class="text-lg font-bold text-slate-200">กราฟราคา XAUUSD</h2>
                        <span id="current-price" class="text-xl font-bold text-amber-400">$2,684.50</span>
                    </div>
                    <!-- กำหนดความสูงและขนาดกล่องกราฟให้ชัดเจน -->
                    <div id="chart-container" style="width: 100%; height: 400px; position: relative;"></div>
                </div>
            </div>

            <div class="space-y-6">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
                    <h2 class="text-lg font-bold text-slate-200 border-b border-slate-800 pb-2">สัญญาณ AI & Fibonacci</h2>
                    <div class="flex justify-between items-center">
                        <span class="text-sm text-slate-400">สถานะ (Signal):</span>
                        <span class="px-3 py-1 rounded-lg text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">BUY (LONG)</span>
                    </div>
                    <div class="flex justify-between items-center">
                        <span class="text-sm text-slate-400">ความแม่นยำ (Win Rate):</span>
                        <span class="text-base font-bold text-emerald-400">88.4%</span>
                    </div>
                    <div class="grid grid-cols-2 gap-3 pt-2">
                        <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
                            <span class="text-xs text-slate-400 block">Fibonacci 61.8%</span>
                            <span class="text-sm font-bold text-cyan-400">$2,672.10</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
                            <span class="text-xs text-slate-400 block">Fibonacci 38.2%</span>
                            <span class="text-sm font-bold text-purple-400">$2,678.90</span>
                        </div>
                    </div>
                    <div class="space-y-1 pt-2">
                        <span class="text-xs text-slate-400 block">วิเคราะห์เชิงลึก:</span>
                        <p class="text-xs text-slate-300 bg-slate-950 p-3 rounded-xl border border-slate-800 leading-relaxed">
                            ราคาพักตัวลงมาแตะโซน Fibonacci Retracement 61.8% (Golden Pocket) พร้อมสัญญาณ Bullish Order Block สนับสนุนทิศทางขาขึ้น
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        window.addEventListener('DOMContentLoaded', () => {
            const container = document.getElementById('chart-container');
            const chart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 400,
                layout: { background: { type: 'solid', color: '#090d16' }, textColor: '#94a3b8' },
                grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
                rightPriceScale: { borderColor: '#334155' },
                timeScale: { borderColor: '#334155', timeVisible: true }
            });

            const candleSeries = chart.addCandlestickSeries({
                upColor: '#10b981', 
                downColor: '#f43f5e', 
                borderVisible: false, 
                wickUpColor: '#10b981', 
                wickDownColor: '#f43f5e'
            });

            // ข้อมูลจำลองแท่งเทียน XAUUSD
            const mockData = [
                { time: '2026-10-20', open: 2650.0, high: 2662.0, low: 2648.0, close: 2658.5 },
                { time: '2026-10-21', open: 2658.5, high: 2670.0, low: 2655.0, close: 2668.2 },
                { time: '2026-10-22', open: 2668.2, high: 2675.0, low: 2662.0, close: 2664.0 },
                { time: '2026-10-23', open: 2664.0, high: 2680.0, low: 2661.0, close: 2677.5 },
                { time: '2026-10-24', open: 2677.5, high: 2685.0, low: 2672.0, close: 2684.5 }
            ];

            candleSeries.setData(mockData);
            chart.timeScale().fitContent();

            // ปรับขนาดกราฟอัตโนมัติเมื่อจอเปลี่ยนขนาด
            window.addEventListener('resize', () => {
                chart.applyOptions({ width: container.clientWidth });
            });
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
