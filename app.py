import os
import random
from flask import Flask, render_template_string

app = Flask(__name__)

def get_multi_timeframe_analysis():
    # จำลองการวิเคราะห์โครงสร้างตลาดแต่ละไทม์เฟรม (สามารถเชื่อมต่อ API จริงภายหลังได้)
    timeframes = {
        "1m": {"trend": "Sideway", "bias": "Neutral", "color": "text-yellow-400", "bg": "bg-yellow-500/10"},
        "5m": {"trend": "Uptrend", "bias": "Bullish", "color": "text-emerald-400", "bg": "bg-emerald-500/10"},
        "15m": {"trend": "Uptrend", "bias": "Strong Buy", "color": "text-emerald-400", "bg": "bg-emerald-500/10"},
        "1h": {"trend": "Uptrend", "bias": "Golden Zone (61.8%)", "color": "text-cyan-400", "bg": "bg-cyan-500/10"},
        "4h": {"trend": "Uptrend", "bias": "Bullish Trend", "color": "text-emerald-400", "bg": "bg-emerald-500/10"},
        "Daily": {"trend": "Strong Uptrend", "bias": "Macro Bullish", "color": "text-amber-400", "bg": "bg-amber-500/10"}
    }
    return timeframes

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold AI Analytics Pro - Multi-Timeframe System</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 font-sans antialiased min-h-screen p-4 md:p-8">
    <div class="max-w-7xl mx-auto space-y-6">
        <header class="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-slate-800 pb-4 gap-4">
            <div>
                <h1 class="text-2xl md:text-3xl font-black tracking-wider text-amber-400">GOLD AI ANALYTICS PRO</h1>
                <p class="text-xs md:text-sm text-slate-400">ระบบวิเคราะห์ราคาทองคำ XAUUSD + Multi-Timeframe AI & Golden Zone</p>
            </div>
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                <span class="w-2 h-2 mr-2 bg-emerald-500 rounded-full animate-pulse"></span> ระบบออนไลน์ (Live)
            </span>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <!-- ฝั่งซ้าย: กราฟ TradingView (3 ส่วน) -->
            <div class="lg:col-span-3 space-y-6">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl">
                    <div class="flex justify-between items-center mb-4">
                        <h2 class="text-lg font-bold text-slate-200">กราฟมาตรฐาน TradingView (XAUUSD)</h2>
                        <span class="text-xs text-amber-400 font-semibold">ทริค: ใช้เครื่องมือวัด Fibonacci หาโซน 61.8% - 78.6%</span>
                    </div>
                    
                    <div class="tradingview-widget-container" style="height:550px;width:100%;">
                        <div id="tradingview_chart" style="height:100%;width:100%;"></div>
                        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                        <script type="text/javascript">
                        new TradingView.widget(
                        {
                            "width": "100%",
                            "height": "550",
                            "symbol": "OANDA:XAUUSD",
                            "interval": "60",
                            "timezone": "Asia/Bangkok",
                            "theme": "dark",
                            "style": "1",
                            "locale": "th",
                            "toolbar_bg": "#f1f3f6",
                            "enable_publishing": false,
                            "allow_symbol_change": true,
                            "container_id": "tradingview_chart"
                        }
                        );
                        </script>
                    </div>
                </div>
            </div>

            <!-- ฝั่งขวา: แผง Multi-Timeframe Analysis & AI (1 ส่วน) -->
            <div class="space-y-6">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
                    <h2 class="text-lg font-bold text-slate-200 border-b border-slate-800 pb-2">Multi-Timeframe Matrix</h2>
                    
                    <div class="space-y-2">
                        {% for tf, data in mtf.items() %}
                        <div class="flex justify-between items-center bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                            <span class="text-xs font-bold text-slate-300 uppercase w-12">{{ tf }}</span>
                            <span class="text-xs px-2 py-0.5 rounded {{ data.bg }} {{ data.color }} font-semibold">{{ data.trend }}</span>
                            <span class="text-xs font-bold {{ data.color }}">{{ data.bias }}</span>
                        </div>
                        {% endfor %}
                    </div>

                    <div class="border-t border-slate-800 pt-3 space-y-2">
                        <div class="flex justify-between items-center">
                            <span class="text-xs text-slate-400">Golden Zone (61.8% - 78.6%):</span>
                            <span class="text-xs font-bold text-cyan-400">Active ($2,665 - $2,642)</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-xs text-slate-400">สถานะคำสั่งซื้อ:</span>
                            <span class="px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">READY TO BUY</span>
                        </div>
                    </div>

                    <div class="space-y-1 pt-1">
                        <span class="text-xs text-slate-400 block font-semibold text-amber-300"> AI สรุปภาพรวม:</span>
                        <p class="text-xs text-slate-300 bg-slate-950 p-3 rounded-xl border border-slate-800 leading-relaxed">
                            ภาพใหญ่ Daily และ 4h เป็นเทรนด์ขาขึ้นแข็งแกร่ง ขณะที่ 1h ย่อตัวลงมาแตะโซน Golden Zone เปิดโอกาสเข้าสะสมไม้ Long ตามโครงสร้างตลาด
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    mtf_data = get_multi_timeframe_analysis()
    return render_template_string(HTML_TEMPLATE, mtf=mtf_data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
