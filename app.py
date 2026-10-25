import os
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# ==============================================================================
# ตั้งค่า LINE OA Messaging API Token (ตั้งใน Environment Variables ของ Render)
# ==============================================================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

# เขตเวลาประเทศไทย (UTC+7)
TH_TZ = timezone(timedelta(hours=7))

# แคชข้อมูลข่าว Forex Factory เพื่อความรวดเร็วและป้องกันการถูกจำกัดการดึงข้อมูล
FF_CACHE = {
    "last_fetched": 0,
    "events": []
}

# สถานะระบบหลัก
SYSTEM_STATE = {
    "manual_news_lock": False,
    "latest_signal": None,
    "signal_history": [
        {
            "id": 102,
            "date": "25 ต.ค. 2026",
            "time": "16:30:00",
            "symbol": "XAUUSD",
            "tf": "1H",
            "direction": "SELL",
            "entry": "2738.50",
            "sl": "2745.20",
            "tp1": "2725.10",
            "tp2": "2718.40",
            "rr": "1:3",
            "status": "READY / ACTIVE",
            "reason": "คำนวณจาก Golden Zone Fib 61.8% ในไทม์เฟรม 1H แนวต้านสำคัญ"
        },
        {
            "id": 101,
            "date": "24 ต.ค. 2026",
            "time": "20:15:00",
            "symbol": "XAUUSD",
            "tf": "15M",
            "direction": "BUY",
            "entry": "2722.40",
            "sl": "2717.80",
            "tp1": "2731.60",
            "tp2": "2736.20",
            "rr": "1:3",
            "status": "TP2 HIT (+1,380 pts)",
            "reason": "ราคาย่อตัวลงมาแตะ Fib 61.8% หลังข่าวประกาศ แล้วดีดกลับตามเทรนด์หลัก"
        }
    ],
    "custom_news": []
}

THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."
]


def format_thai_date(dt_obj):
    """แปลง datetime เป็นข้อความวัน-เดือน-ปีภาษาไทย เช่น 'พ. 28 ต.ค. 2026'"""
    day_name = THAI_DAYS[dt_obj.weekday()]
    month_name = THAI_MONTHS[dt_obj.month]
    return f"{day_name} {dt_obj.day} {month_name} {dt_obj.year}"


def compute_countdown_and_lock(event_dt, now_dt, impact):
    """คำนวณเวลานับถอยหลัง และตรวจสอบว่าอยู่ในช่วงล็อกก่อน-หลังข่าวแดง 30 นาทีหรือไม่"""
    diff_sec = (event_dt - now_dt).total_seconds()
    is_same_day = (event_dt.date() == now_dt.date())
    is_tomorrow = (event_dt.date() == (now_dt.date() + timedelta(days=1)))

    # ตรวจสอบการล็อกอัตโนมัติ (เฉพาะข่าว HIGH และอยู่ในช่วง -30 นาที ถึง +30 นาทีของเวลาจริง)
    is_auto_locking_now = (impact == "HIGH" and -1800 <= diff_sec <= 1800)

    if -1800 <= diff_sec <= 1800:
        countdown = "🔥 กำลังประกาศข่าว! (อยู่ในช่วงเฝ้าระวัง ±30 นาที)"
        urgency = "NOW"
    elif diff_sec < -1800:
        countdown = "ประกาศผลแล้ว"
        urgency = "PAST"
    else:
        hours = int(diff_sec // 3600)
        mins = int((diff_sec % 3600) // 60)
        days = int(diff_sec // 86400)
        if is_same_day:
            if hours > 0:
                countdown = f"วันนี้ • อีก {hours} ชม. {mins} นาที"
            else:
                countdown = f"⚠️ วันนี้ • อีก {mins} นาที!"
            urgency = "TODAY"
        elif is_tomorrow:
            countdown = f"พรุ่งนี้ • เวลา {event_dt.strftime('%H:%M')} น."
            urgency = "TOMORROW"
        else:
            countdown = f"อีก {days} วัน ({format_thai_date(event_dt)})"
            urgency = "FUTURE"

    return countdown, urgency, is_auto_locking_now


def get_fallback_forex_factory_schedule(now_dt):
    """ตารางข่าวมาตรฐานอ้างอิงเวลาจริงของสัปดาห์ปัจจุบัน (กรณี API ภายนอกติด Rate Limit)"""
    # หาวันจันทร์ของสัปดาห์ปัจจุบัน (หรือสัปดาห์ถัดไปหากเป็นวันอาทิตย์เย็น)
    base_date = now_dt.date()
    if now_dt.weekday() == 6:  # วันอาทิตย์ ให้แสดงตารางสัปดาห์หน้าตั้งแต่วันจันทร์
        monday = base_date + timedelta(days=1)
    else:
        monday = base_date - timedelta(days=now_dt.weekday())

    template_events = [
        (0, 21, 0, "USD", "CB Consumer Confidence (ดัชนีความเชื่อมั่นผู้บริโภค)", "MEDIUM", "99.5", "98.7"),
        (1, 19, 30, "USD", "Prelim GDP q/q (ตัวเลขผลิตภัณฑ์มวลรวมในประเทศเบื้องต้น)", "HIGH", "2.9%", "3.0%"),
        (1, 21, 0, "USD", "JOLTS Job Openings (ตำแหน่งงานว่างเปิดใหม่สหรัฐฯ)", "HIGH", "7.92M", "8.04M"),
        (2, 19, 15, "USD", "ADP Non-Farm Employment Change (การจ้างงานภาคเอกชน)", "HIGH", "115K", "143K"),
        (2, 19, 30, "USD", "Core CPI / PCE Price Index m/m (ดัชนีเงินเฟ้อพื้นฐานสหรัฐฯ)", "HIGH", "0.3%", "0.2%"),
        (3, 19, 30, "USD", "Unemployment Claims (จำนวนผู้ขอรับสวัสดิการว่างงานรายสัปดาห์)", "HIGH", "222K", "227K"),
        (3, 20, 45, "USD", "Chicago PMI (ดัชนีผู้จัดการฝ่ายจัดซื้อเขตชิคาโก)", "MEDIUM", "47.1", "46.6"),
        (4, 19, 30, "USD", "Non-Farm Employment Change - NFP (การจ้างงานนอกภาคเกษตร)", "HIGH", "148K", "254K"),
        (4, 19, 30, "USD", "Unemployment Rate (อัตราการว่างงานสหรัฐฯ)", "HIGH", "4.1%", "4.1%"),
        (4, 21, 0, "USD", "ISM Manufacturing PMI (ดัชนีผู้จัดการฝ่ายจัดซื้อภาคการผลิต)", "HIGH", "47.6", "47.2"),
    ]

    results = []
    for day_offset, hr, mn, curr, title, impact, forecast, previous in template_events:
        ev_date = monday + timedelta(days=day_offset)
        ev_dt = datetime(ev_date.year, ev_date.month, ev_date.day, hr, mn, tzinfo=TH_TZ)
        countdown, urgency, is_locking = compute_countdown_and_lock(ev_dt, now_dt, impact)

        lock_start = (ev_dt - timedelta(minutes=30)).strftime("%H:%M")
        lock_end = (ev_dt + timedelta(minutes=30)).strftime("%H:%M")
        if impact == "HIGH":
            rule_text = f"ล็อกอัตโนมัติ {lock_start}-{lock_end} น."
        elif impact == "MEDIUM":
            rule_text = "ลดขนาด Lot 50%"
        else:
            rule_text = "เทรดปกติ"

        results.append({
            "timestamp": int(ev_dt.timestamp()),
            "date_label": format_thai_date(ev_dt),
            "iso_date": ev_dt.strftime("%Y-%m-%d"),
            "time_label": ev_dt.strftime("%H:%M น."),
            "currency": curr,
            "event": title,
            "impact": impact,
            "forecast": forecast,
            "previous": previous,
            "countdown": countdown,
            "urgency": urgency,
            "is_locking_now": is_locking,
            "status": rule_text,
            "source": "Forex Factory Schedule"
        })
    return results


def fetch_forex_factory_calendar():
    """ดึงข้อมูลปฏิทินเศรษฐกิจจริงจาก Forex Factory JSON Feed พร้อมแปลงเป็นเวลาไทย"""
    now_dt = datetime.now(TH_TZ)
    now_ts = now_dt.timestamp()

    # ใช้ Cache 15 นาทีเพื่อความเร็วสูง
    if FF_CACHE["events"] and (now_ts - FF_CACHE["last_fetched"] < 900):
        raw_list = FF_CACHE["events"]
    else:
        raw_list = None
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    raw_list = data
                    FF_CACHE["events"] = raw_list
                    FF_CACHE["last_fetched"] = now_ts
        except Exception as e:
            print("Forex Factory live fetch fallback:", e)

    parsed_events = []
    if raw_list:
        for item in raw_list:
            if item.get("country") != "USD":
                continue
            impact_raw = item.get("impact", "Low").upper()
            if impact_raw not in ["HIGH", "MEDIUM", "LOW"]:
                continue

            date_str = item.get("date", "")
            try:
                ev_dt = datetime.fromisoformat(date_str).astimezone(TH_TZ)
            except Exception:
                continue

            countdown, urgency, is_locking = compute_countdown_and_lock(ev_dt, now_dt, impact_raw)
            lock_start = (ev_dt - timedelta(minutes=30)).strftime("%H:%M")
            lock_end = (ev_dt + timedelta(minutes=30)).strftime("%H:%M")

            if impact_raw == "HIGH":
                rule_text = f"ล็อกอัตโนมัติ {lock_start}-{lock_end} น."
            elif impact_raw == "MEDIUM":
                rule_text = "ลดขนาด Lot 50%"
            else:
                rule_text = "เทรดปกติ"

            parsed_events.append({
                "timestamp": int(ev_dt.timestamp()),
                "date_label": format_thai_date(ev_dt),
                "iso_date": ev_dt.strftime("%Y-%m-%d"),
                "time_label": ev_dt.strftime("%H:%M น."),
                "currency": "USD",
                "event": item.get("title", "USD Economic Event"),
                "impact": impact_raw,
                "forecast": item.get("forecast") or "-",
                "previous": item.get("previous") or "-",
                "countdown": countdown,
                "urgency": urgency,
                "is_locking_now": is_locking,
                "status": rule_text,
                "source": "Forex Factory Live"
            })

    if not parsed_events:
        parsed_events = get_fallback_forex_factory_schedule(now_dt)

    # รวมข่าวที่ผู้ใช้เพิ่มเองเข้าไปด้วย
    all_events = SYSTEM_STATE["custom_news"] + parsed_events
    all_events.sort(key=lambda x: x.get("timestamp", 0))
    return all_events


# ==============================================================================
# FRONTEND HTML TEMPLATE (PRO UI + MICRO-INTERACTIONS + AUTO FIBONACCI ENGINE)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — TradingView & Auto Fibonacci Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
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
                radial-gradient(circle at 10% 5%, rgba(245, 158, 11, 0.09), transparent 35%),
                radial-gradient(circle at 90% 12%, rgba(6, 182, 212, 0.08), transparent 35%),
                radial-gradient(circle at 50% 95%, rgba(16, 185, 129, 0.06), transparent 40%),
                linear-gradient(to bottom, rgba(15, 23, 42, 0.28) 1px, transparent 1px),
                linear-gradient(to right, rgba(15, 23, 42, 0.28) 1px, transparent 1px);
            background-size: 100% 100%, 100% 100%, 100% 100%, 36px 36px, 36px 36px;
            color: #f1f5f9;
            overflow-x: hidden;
        }
        .font-mono-num { font-family: 'JetBrains Mono', monospace; }

        /* การ์ดหลักพร้อมมิติแสงและการขยับเมื่อชี้เมาส์ */
        .pro-card {
            background: var(--bg-card);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid var(--border-subtle);
            box-shadow: 0 20px 50px -15px rgba(0, 0, 0, 0.75), inset 0 1px 0 0 rgba(255, 255, 255, 0.08);
            transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.28s ease, box-shadow 0.28s ease;
        }
        .pro-card:hover {
            border-color: rgba(255, 255, 255, 0.15);
        }
        .pro-card-gold {
            background: linear-gradient(145deg, rgba(18, 27, 48, 0.95), rgba(9, 14, 26, 0.98));
            border: 1px solid rgba(245, 158, 11, 0.42);
            box-shadow: 0 22px 55px -15px rgba(245, 158, 11, 0.16), inset 0 1px 0 0 rgba(251, 191, 36, 0.25);
            transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.28s ease;
        }

        /* Micro-Interactions สำหรับปุ่มกดทุกประเภท */
        .btn-interactive {
            position: relative;
            overflow: hidden;
            transition: all 0.24s cubic-bezier(0.34, 1.56, 0.64, 1);
            transform: translateY(0) scale(1);
        }
        .btn-interactive:hover:not(:disabled) {
            transform: translateY(-2px) scale(1.025);
            box-shadow: 0 10px 25px -5px rgba(245, 158, 11, 0.35);
        }
        .btn-interactive:active:not(:disabled) {
            transform: translateY(1px) scale(0.965);
        }

        /* ปุ่มกดคำนวณ Fibonacci พิเศษพร้อมเอฟเฟกต์แสงวิ่ง (Shimmer) */
        .btn-fib-magic {
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, #f59e0b 0%, #eab308 50%, #06b6d4 100%);
            background-size: 200% 200%;
            animation: gradientShift 4s ease infinite;
            transition: all 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .btn-fib-magic:hover {
            transform: translateY(-3px) scale(1.02);
            box-shadow: 0 14px 32px -6px rgba(245, 158, 11, 0.55), 0 0 20px rgba(6, 182, 212, 0.4);
        }
        .btn-fib-magic:active {
            transform: translateY(1px) scale(0.97);
        }
        .btn-fib-magic::after {
            content: "";
            position: absolute;
            top: -50%;
            left: -60%;
            width: 40%;
            height: 200%;
            background: rgba(255, 255, 255, 0.35);
            transform: rotate(30deg);
            transition: all 0.65s ease;
        }
        .btn-fib-magic:hover::after {
            left: 130%;
        }

        /* การ์ดราคาที่กด Copy ได้ มีจังหวะเด้งเวลาชี้เมาส์ */
        .price-card-interactive {
            transition: all 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .price-card-interactive:hover {
            transform: translateY(-3px) scale(1.02);
            box-shadow: 0 12px 24px -8px rgba(6, 182, 212, 0.3);
        }
        .price-card-interactive:active {
            transform: scale(0.97);
        }

        @keyframes gradientShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #03060c; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 9999px; }
        ::-webkit-scrollbar-thumb:hover { background: #f59e0b; }
    </style>
</head>
<body class="antialiased min-h-screen p-3 md:p-5 selection:bg-amber-500 selection:text-slate-950">
    <div class="max-w-[1780px] mx-auto space-y-5">

        <!-- ================================================================ -->
        <!-- 1. TOP INSTITUTIONAL NAVBAR & FOREX FACTORY SHIELD               -->
        <!-- ================================================================ -->
        <header class="pro-card rounded-2xl p-4 lg:px-6">
            <div class="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
                
                <!-- Brand Identity -->
                <div class="flex items-center gap-4">
                    <div class="relative group cursor-pointer">
                        <div class="absolute -inset-1 bg-gradient-to-r from-amber-400 via-yellow-500 to-cyan-500 rounded-2xl blur opacity-45 group-hover:opacity-90 transition duration-300"></div>
                        <div class="relative px-4 py-2.5 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 flex flex-col items-center justify-center shadow-xl font-black text-slate-950 shrink-0">
                            <span class="text-[10px] tracking-tighter leading-none opacity-85">TRADINGVIEW</span>
                            <span class="text-lg tracking-tight leading-none font-mono-num">XAU</span>
                        </div>
                    </div>
                    <div>
                        <div class="flex flex-wrap items-center gap-2.5">
                            <h1 class="text-xl md:text-2xl font-black tracking-tight bg-gradient-to-r from-white via-amber-200 to-amber-400 bg-clip-text text-transparent">
                                GOLD AI SNIPER PRO
                            </h1>
                            <span class="px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-full">
                                <i class="fa-solid fa-wand-magic-sparkles mr-1"></i>AUTO FIBONACCI CALCULATOR • 61.8% & 78.6%
                            </span>
                            <span class="px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 rounded-full">
                                <i class="fa-solid fa-calendar-days mr-1"></i>FOREX FACTORY LIVE SYNC
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-1 flex flex-wrap items-center gap-2">
                            <span>ระบบกราฟ TradingView แท้ + ปุ่มคำนวณและตีเส้น Fibonacci อัตโนมัติ (ย้อนหลัง 1,000 แท่ง) & ปฏิทินข่าวระบุวัน-เวลาชัดเจน</span>
                            <span class="hidden md:inline text-slate-600">|</span>
                            <span id="current-date-label" class="text-amber-400 font-semibold"></span>
                        </p>
                    </div>
                </div>

                <!-- Right Controls: Active Bias + News Shield + Live Price -->
                <div class="flex flex-wrap items-center gap-2.5 w-full xl:w-auto justify-between xl:justify-end">
                    
                    <div class="bg-slate-950/90 border border-slate-800 px-3.5 py-2 rounded-xl flex items-center gap-2.5">
                        <div class="text-[11px]">
                            <span class="block text-[9px] uppercase tracking-wider text-slate-500 font-bold">ACTIVE FIB BIAS</span>
                            <span id="master-daily-bias" class="font-extrabold text-amber-400 flex items-center gap-1">
                                <i class="fa-solid fa-crosshairs"></i> พร้อมคำนวณ Fibonacci
                            </span>
                        </div>
                    </div>

                    <!-- News Filter Shield Status -->
                    <div id="news-shield-box" class="bg-emerald-950/40 border border-emerald-500/40 px-3.5 py-2 rounded-xl flex items-center gap-3 transition-all">
                        <div class="flex items-center gap-2">
                            <span id="shield-dot" class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
                            <div>
                                <span class="block text-[9px] uppercase tracking-wider text-slate-400 font-bold">FOREX FACTORY SHIELD</span>
                                <span id="shield-status-text" class="text-xs font-extrabold text-emerald-400">SAFE MODE (ตลาดปกติ)</span>
                            </div>
                        </div>
                        <button onclick="toggleNewsLock()" class="btn-interactive px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-[11px] font-bold text-slate-200 border border-slate-700">
                            <i class="fa-solid fa-shield-halved text-amber-400 mr-1"></i>ทดสอบล็อกข่าว
                        </button>
                    </div>

                    <!-- Live XAUUSD Price Ticker -->
                    <div class="bg-slate-950/90 border border-amber-500/40 px-4 py-2 rounded-xl flex items-center gap-3">
                        <div class="text-right">
                            <span class="block text-[9px] uppercase tracking-wider text-amber-400/80 font-bold">XAUUSD MARKET</span>
                            <span id="live-ticker-price" class="font-mono-num text-sm md:text-base font-extrabold text-emerald-400">LOADING...</span>
                        </div>
                        <span class="px-1.5 py-0.5 text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400 rounded border border-emerald-500/30">LIVE</span>
                    </div>

                </div>
            </div>
        </header>

        <!-- ================================================================ -->
        <!-- 2. KPI METRICS BAR (4 PRO INTERACTIVE CARDS)                     -->
        <!-- ================================================================ -->
        <section class="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">ระบบคำนวณจุดเข้า (Auto Fib)</span>
                    <div class="text-xl md:text-2xl font-black font-mono-num text-amber-400 mt-0.5">Golden 61.8%</div>
                    <span class="text-[11px] text-slate-400">ตีเส้น Fib ครบทุกระดับในคลิกเดียว</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 text-lg">
                    <i class="fa-solid fa-wand-magic-sparkles"></i>
                </div>
            </div>

            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">ข้อมูลกราฟย้อนหลัง (History)</span>
                    <div class="text-xl md:text-2xl font-black font-mono-num text-cyan-400 mt-0.5">1,000+ แท่ง</div>
                    <span class="text-[11px] text-slate-400">เลื่อนดูอดีตได้ยาว + กราฟ TradingView แท้</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center text-cyan-400 text-lg">
                    <i class="fa-solid fa-chart-candlestick"></i>
                </div>
            </div>

            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">อัตราส่วนคุ้มค่า (RR Ratio)</span>
                    <div class="text-xl md:text-2xl font-black font-mono-num text-emerald-400 mt-0.5">1 : 2 & 1 : 3</div>
                    <span class="text-[11px] text-slate-400">SL สั้นที่ 78.6% คุมความเสี่ยงพอร์ต</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-lg">
                    <i class="fa-solid fa-scale-balanced"></i>
                </div>
            </div>

            <div class="pro-card rounded-2xl p-4 flex items-center justify-between">
                <div>
                    <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">ปฏิทินข่าว Forex Factory</span>
                    <div class="text-base font-black text-white mt-1 flex items-center gap-2">
                        <span id="next-high-news-badge" class="px-2.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs">กำลังโหลดตารางสัปดาห์นี้...</span>
                    </div>
                    <span class="text-[11px] text-slate-400 mt-1 block">ระบุวัน-เดือน-ปี และเวลาไทยชัดเจน</span>
                </div>
                <div class="w-11 h-11 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 text-lg">
                    <i class="fa-solid fa-bell"></i>
                </div>
            </div>
        </section>

        <!-- ================================================================ -->
        <!-- 3. MAIN WORKSPACE GRID (12 COLUMNS)                              -->
        <!-- ================================================================ -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-5">
            
            <!-- ============================================================ -->
            <!-- LEFT COLUMN (7 COLS): TRADINGVIEW & AUTO-FIB + FOREX FACTORY -->
            <!-- ============================================================ -->
            <div class="xl:col-span-7 space-y-5">
                
                <!-- 3.1 CHART & AUTO-FIBONACCI STUDIO -->
                <div class="pro-card rounded-2xl p-4 md:p-5 space-y-4">
                    
                    <!-- Top Action Bar: 3 Chart Modes + Big "Calculate Auto Fibonacci" Button -->
                    <div class="flex flex-col lg:flex-row justify-between items-stretch lg:items-center gap-3 border-b border-slate-800/80 pb-3.5">
                        
                        <!-- 3 View Modes -->
                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 flex-1">
                            <button onclick="switchChartMode('split')" id="mode-btn-split" class="btn-interactive py-2.5 px-3 rounded-xl text-xs font-extrabold flex items-center justify-center gap-1.5 bg-gradient-to-r from-amber-400 via-amber-500 to-yellow-500 text-slate-950 shadow-lg">
                                <i class="fa-solid fa-columns"></i>
                                <span>ดูคู่กัน (TradingView + กราฟตีเส้น Fib)</span>
                            </button>
                            <button onclick="switchChartMode('tv')" id="mode-btn-tv" class="btn-interactive py-2.5 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 bg-slate-950 text-slate-300 border border-slate-800 hover:border-amber-500/50">
                                <i class="fa-solid fa-chart-line text-cyan-400"></i>
                                <span>TradingView แท้เต็มจอ (OANDA)</span>
                            </button>
                            <button onclick="switchChartMode('autofib')" id="mode-btn-autofib" class="btn-interactive py-2.5 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 bg-slate-950 text-slate-300 border border-slate-800 hover:border-amber-500/50">
                                <i class="fa-solid fa-crosshairs text-amber-400"></i>
                                <span>กราฟ AI ตีเส้น Fib เต็มจอ (1,000 แท่ง)</span>
                            </button>
                        </div>

                        <!-- THE ONE-CLICK AUTO FIBONACCI BUTTON -->
                        <button onclick="triggerAutoFibonacciCalculation(true)" id="btn-calc-fib-main" class="btn-fib-magic py-2.5 px-5 rounded-xl text-xs md:text-sm font-black text-slate-950 flex items-center justify-center gap-2 shrink-0">
                            <i id="fib-spin-icon" class="fa-solid fa-bolt"></i>
                            <span>คำนวณ Fibonacci อัตโนมัติทันที</span>
                        </button>
                    </div>

                    <!-- Quick Copy Price Pills Above Chart -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        <div onclick="copyPrice('val-entry')" class="price-card-interactive cursor-pointer p-2.5 rounded-xl bg-cyan-950/35 border border-cyan-500/40 flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-cyan-300 font-bold uppercase tracking-wider block">🔵 จุดเข้า ENTRY (61.8%)</span>
                                <span id="top-entry" class="font-mono-num font-extrabold text-cyan-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-cyan-500/20 text-cyan-200 px-2 py-0.5 rounded-md font-bold">คัดลอก</span>
                        </div>

                        <div onclick="copyPrice('val-sl')" class="price-card-interactive cursor-pointer p-2.5 rounded-xl bg-rose-950/35 border border-rose-500/40 flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-rose-300 font-bold uppercase tracking-wider block">🔴 ตัดขาดทุน SL (78.6%)</span>
                                <span id="top-sl" class="font-mono-num font-extrabold text-rose-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-rose-500/20 text-rose-200 px-2 py-0.5 rounded-md font-bold">คัดลอก</span>
                        </div>

                        <div onclick="copyPrice('val-tp1')" class="price-card-interactive cursor-pointer p-2.5 rounded-xl bg-emerald-950/35 border border-emerald-500/40 flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-emerald-300 font-bold uppercase tracking-wider block">🟢 เป้า TP1 (RR 1:2)</span>
                                <span id="top-tp1" class="font-mono-num font-extrabold text-emerald-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-emerald-500/20 text-emerald-200 px-2 py-0.5 rounded-md font-bold">คัดลอก</span>
                        </div>

                        <div onclick="copyPrice('val-tp2')" class="price-card-interactive cursor-pointer p-2.5 rounded-xl bg-amber-950/35 border border-amber-500/40 flex justify-between items-center">
                            <div>
                                <span class="text-[10px] text-amber-300 font-bold uppercase tracking-wider block">🟡 เป้าหลัก TP2 (RR 1:3)</span>
                                <span id="top-tp2" class="font-mono-num font-extrabold text-amber-400 text-sm md:text-base">--</span>
                            </div>
                            <span class="text-[10px] bg-amber-500/20 text-amber-200 px-2 py-0.5 rounded-md font-bold">คัดลอก</span>
                        </div>
                    </div>

                    <!-- CHART CONTAINER 1: TRADINGVIEW OFFICIAL ADVANCED CHART -->
                    <div id="tv-chart-section" class="space-y-2">
                        <div class="flex flex-wrap justify-between items-center text-[11px] bg-slate-950/80 px-3 py-2 rounded-xl border border-slate-800">
                            <span class="text-amber-300 font-semibold">
                                <i class="fa-solid fa-circle-check text-emerald-400 mr-1"></i><strong>กราฟที่ 1: TradingView แท้ (OANDA:XAUUSD)</strong> — เลื่อนดูย้อนหลังได้ไม่จำกัด พร้อมเครื่องมือ TradingView ครบชุด
                            </span>
                            <span id="tv-tf-label" class="font-mono-num font-bold text-cyan-400">TF: 1H</span>
                        </div>
                        <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800" style="height:460px; width:100%;">
                            <div id="tradingview_studio_chart" style="height:100%; width:100%;"></div>
                        </div>
                    </div>

                    <!-- CHART CONTAINER 2: AI AUTO-PLOT FIBONACCI CHART (1,000 BARS HISTORY) -->
                    <div id="autofib-chart-section" class="space-y-2">
                        <div class="flex flex-wrap justify-between items-center text-[11px] bg-slate-950/80 px-3 py-2 rounded-xl border border-amber-500/30">
                            <span class="text-slate-200">
                                <i class="fa-solid fa-wand-magic-sparkles text-amber-400 mr-1"></i><strong>กราฟที่ 2: AI Auto-Plot Fibonacci (ดึงกราฟย้อนหลัง 1,000 แท่ง)</strong> — ตีเส้น Fib 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100% และ TP ให้อัตโนมัติ
                            </span>
                            <div class="flex items-center gap-2">
                                <span id="autofib-status-text" class="text-emerald-400 font-semibold">● คำนวณเส้น Fib ล่าสุดแล้ว</span>
                                <button onclick="resetSniperZoom()" class="btn-interactive px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 text-amber-400 font-bold">
                                    <i class="fa-solid fa-expand mr-1"></i>จัดกึ่งกลางเส้น Fib
                                </button>
                            </div>
                        </div>
                        <div id="sniper-lw-chart" class="w-full h-[460px] rounded-xl overflow-hidden border border-slate-800 bg-[#050912]"></div>
                    </div>

                </div>

                <!-- 3.2 FOREX FACTORY ECONOMIC CALENDAR (WITH EXACT DATES & FILTER TABS) -->
                <div class="pro-card rounded-2xl p-5 space-y-4">
                    <div class="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-slate-800/80 pb-3.5 gap-3">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 text-lg shrink-0">
                                <i class="fa-regular fa-calendar-days"></i>
                            </div>
                            <div>
                                <div class="flex flex-wrap items-center gap-2">
                                    <h2 class="text-base font-bold text-white">ปฏิทินข่าวเศรษฐกิจ Forex Factory (ระบุวัน-เวลาไทยชัดเจน)</h2>
                                    <span class="px-2 py-0.5 text-[10px] font-extrabold bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded-md">USD IMPACT</span>
                                </div>
                                <p class="text-[11px] text-slate-400">อ้างอิงตารางข่าวจริงจาก Forex Factory พร้อมคำนวณเวลานับถอยหลัง และล็อกสัญญาณอัตโนมัติเมื่อถึงวัน-เวลาข่าวแดง ±30 นาที</p>
                            </div>
                        </div>

                        <!-- Filter Buttons for News -->
                        <div class="flex flex-wrap items-center gap-1.5">
                            <button onclick="filterNews('ALL')" id="news-filter-ALL" class="btn-interactive px-3 py-1.5 rounded-xl text-xs font-extrabold bg-amber-500 text-slate-950">
                                ทั้งสัปดาห์นี้
                            </button>
                            <button onclick="filterNews('TODAY')" id="news-filter-TODAY" class="btn-interactive px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-950 text-slate-300 border border-slate-800">
                                เฉพาะวันนี้
                            </button>
                            <button onclick="filterNews('HIGH')" id="news-filter-HIGH" class="btn-interactive px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-950 text-rose-400 border border-slate-800">
                                🔴 เฉพาะข่าวแดง
                            </button>
                            <button onclick="document.getElementById('add-news-modal').classList.toggle('hidden')" class="btn-interactive px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs font-bold text-amber-400">
                                <i class="fa-solid fa-plus mr-1"></i>เพิ่มข่าวเอง
                            </button>
                        </div>
                    </div>

                    <!-- Form to Add Custom News Event with Date -->
                    <div id="add-news-modal" class="hidden bg-slate-950/90 p-3.5 rounded-xl border border-slate-800 grid grid-cols-1 sm:grid-cols-6 gap-2 text-xs">
                        <input type="date" id="new-news-date" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                        <input type="time" id="new-news-time" value="19:30" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                        <input type="text" id="new-news-Event" placeholder="ชื่อข่าว (เช่น Core CPI m/m)" class="sm:col-span-2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white">
                        <select id="new-news-impact" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-bold">
                            <option value="HIGH">🔴 ข่าวแดง (High)</option>
                            <option value="MEDIUM">🟠 ข่าวส้ม (Medium)</option>
                            <option value="LOW">🟡 ข่าวเหลือง (Low)</option>
                        </select>
                        <button onclick="addNewsItem()" class="btn-interactive bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold rounded-lg p-2">บันทึกข่าว</button>
                    </div>

                    <!-- Economic Calendar Table -->
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-slate-800/80 text-[11px] uppercase tracking-wider">
                                    <th class="py-2.5 px-2">วัน / วันที่</th>
                                    <th class="py-2.5 px-2">เวลา (ไทย)</th>
                                    <th class="py-2.5 px-2">ตัวเลขเศรษฐกิจ (Forex Factory)</th>
                                    <th class="py-2.5 px-2">ความรุนแรง</th>
                                    <th class="py-2.5 px-2">คาดการณ์ / ครั้งก่อน</th>
                                    <th class="py-2.5 px-2">สถานะเวลา (Countdown)</th>
                                    <th class="py-2.5 px-2 text-right">ระบบป้องกันพอร์ต</th>
                                </tr>
                            </thead>
                            <tbody id="economic-calendar-body" class="divide-y divide-slate-800/60"></tbody>
                        </table>
                    </div>
                </div>

            </div>

            <!-- ============================================================ -->
            <!-- RIGHT COLUMN (5 COLS): MTF + FIB LADDER + LOT CALC + LINE OA -->
            <!-- ============================================================ -->
            <div class="xl:col-span-5 space-y-5">
                
                <!-- 1. MULTI-TIMEFRAME SELECTOR & ONE-CLICK FIB CALCULATOR -->
                <div class="pro-card rounded-2xl p-5 space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-800/80 pb-3">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-amber-400 block">STEP 1 • SELECT TIMEFRAME & CALCULATE FIB</span>
                            <h2 class="text-base font-bold text-white">เลือกไทม์เฟรมและกดคำนวณ Fibonacci</h2>
                        </div>
                        <span id="active-tf-badge" class="px-3 py-1 rounded-xl text-xs font-black font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 shadow">
                            TF: 1H
                        </span>
                    </div>

                    <!-- 6 Timeframe Buttons with Micro-interactions -->
                    <div class="grid grid-cols-3 sm:grid-cols-6 gap-2">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border">1M</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border">5M</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border">15M</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border">1H</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border">4H</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num border">DAILY</button>
                    </div>

                    <!-- Market Structure Diagnostics -->
                    <div class="bg-slate-950/90 p-3.5 rounded-xl border border-slate-800/90 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">โครงสร้างสวิงล่าสุด</span>
                            <span id="tf-structure-badge" class="inline-block mt-1 px-2 py-0.5 rounded text-[11px] font-bold">--</span>
                        </div>
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">ระยะกรอบสวิง (Range)</span>
                            <span id="tf-volatility" class="block mt-1 font-bold font-mono-num text-slate-200 text-[11px]">--</span>
                        </div>
                        <div class="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                            <span class="text-[10px] text-slate-400 block">แผนหน้าเทรด (AI Bias)</span>
                            <span id="tf-bias-text" class="block mt-1 font-extrabold text-[11px]">--</span>
                        </div>
                    </div>
                </div>

                <!-- 2. GOLDEN ZONE SNIPER SETUP + COMPLETE FIBONACCI LADDER -->
                <div class="pro-card-gold rounded-2xl p-5 space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-800/80 pb-3 gap-2">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-amber-400 block">STEP 2 • AUTO FIBONACCI RETRACEMENT LEVELS</span>
                            <h2 class="text-lg font-black text-white">ตารางระดับ Fibonacci ทั้งหมด & จุดเข้า Golden Zone</h2>
                        </div>
                        <span id="setup-order-badge" class="px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num">--</span>
                    </div>

                    <!-- Button to Recalculate Fib Right Inside the Setup Card -->
                    <div class="flex flex-col sm:flex-row justify-between items-stretch sm:items-center bg-slate-950/90 p-3 rounded-xl border border-amber-500/30 gap-2 text-xs">
                        <div>
                            <span class="text-slate-400 block text-[10px]">กรอบสวิงที่ตรวจพบอัตโนมัติ (Swing High ➔ Swing Low):</span>
                            <span id="setup-swing-info" class="font-mono-num font-bold text-amber-300 text-sm">--</span>
                        </div>
                        <button onclick="triggerAutoFibonacciCalculation(true)" class="btn-fib-magic px-4 py-2 rounded-xl font-black text-slate-950 text-xs flex items-center justify-center gap-1.5">
                            <i class="fa-solid fa-calculator"></i> กดคำนวณ Fib ใหม่
                        </button>
                    </div>

                    <!-- VISUAL FIBONACCI LADDER (0% to 100%) -->
                    <div class="bg-slate-950/95 p-3.5 rounded-xl border border-slate-800 space-y-2">
                        <div class="flex justify-between items-center text-[11px] text-slate-400 pb-1 border-b border-slate-800">
                            <span class="font-bold text-amber-400"><i class="fa-solid fa-layer-group mr-1"></i>ระดับเส้น Fibonacci ทั้งหมดในรอบสวิงนี้ (คลิกเพื่อก๊อปปี้ราคา)</span>
                            <span id="fib-last-calc-time" class="font-mono-num text-[10px] text-emerald-400">--</span>
                        </div>
                        <div id="fib-ladder-container" class="space-y-1.5 text-xs font-mono-num">
                            <!-- สร้างอัตโนมัติด้วย JS: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100% -->
                        </div>
                    </div>

                    <!-- 4 Main Action Cards: ENTRY 61.8%, SL 78.6%, TP1, TP2 -->
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div onclick="copyPrice('val-entry')" class="price-card-interactive cursor-pointer bg-gradient-to-br from-cyan-950/60 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-cyan-500/50">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-cyan-300">🔵 ENTRY (Fib 61.8%)</span>
                                <span class="text-[10px] bg-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded font-bold">Golden Zone</span>
                            </div>
                            <div id="val-entry" class="text-2xl font-black font-mono-num text-cyan-400 mt-1">--</div>
                            <p class="text-[11px] text-slate-400 mt-0.5">คลิกเพื่อคัดลอกราคาจุดเข้า</p>
                        </div>

                        <div onclick="copyPrice('val-sl')" class="price-card-interactive cursor-pointer bg-gradient-to-br from-rose-950/60 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-rose-500/50">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-rose-300">🔴 STOP LOSS (78.6%)</span>
                                <span id="val-risk-pts" class="text-[10px] font-mono-num bg-rose-500/20 text-rose-300 px-2 py-0.5 rounded font-bold">Risk: --</span>
                            </div>
                            <div id="val-sl" class="text-2xl font-black font-mono-num text-rose-400 mt-1">--</div>
                            <p class="text-[11px] text-slate-400 mt-0.5">คลิกเพื่อคัดลอกราคาตัดขาดทุน</p>
                        </div>

                        <div onclick="copyPrice('val-tp1')" class="price-card-interactive cursor-pointer bg-gradient-to-br from-emerald-950/60 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-emerald-500/50">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-emerald-300">🟢 TAKE PROFIT 1 (1:2)</span>
                                <span id="val-tp1-pts" class="text-[10px] font-mono-num bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp1" class="text-2xl font-black font-mono-num text-emerald-400 mt-1">--</div>
                            <p class="text-[11px] text-slate-400 mt-0.5">แบ่งปิดทำกำไร 50% และบังหน้าทุน</p>
                        </div>

                        <div onclick="copyPrice('val-tp2')" class="price-card-interactive cursor-pointer bg-gradient-to-br from-amber-950/60 via-slate-950 to-slate-950 p-3.5 rounded-xl border border-amber-500/60">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-extrabold text-amber-300">🟡 TAKE PROFIT 2 (1:3)</span>
                                <span id="val-tp2-pts" class="text-[10px] font-mono-num bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold">+--</span>
                            </div>
                            <div id="val-tp2" class="text-2xl font-black font-mono-num text-amber-400 mt-1">--</div>
                            <p class="text-[11px] text-slate-400 mt-0.5">เป้าหมายหลัก (Sniper Target 1:3)</p>
                        </div>
                    </div>

                    <!-- AUTO LOT SIZE & RISK CALCULATOR -->
                    <div class="bg-slate-950/90 p-3.5 rounded-xl border border-slate-800 space-y-2.5 text-xs">
                        <div class="flex justify-between items-center">
                            <span class="font-bold text-cyan-400"><i class="fa-solid fa-calculator mr-1.5"></i>คำนวณขนาด Lot อัตโนมัติ (ตามระยะ SL 78.6% ของแผนนี้)</span>
                            <span id="calc-lot-result" class="px-2.5 py-1 rounded-lg bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 font-mono-num font-black text-sm">แนะนำ: 0.05 Lot</span>
                        </div>
                        <div class="grid grid-cols-2 gap-2.5">
                            <div>
                                <label class="text-[10px] text-slate-400 block mb-1">ทุนในพอร์ต (Account Balance $)</label>
                                <input type="number" id="acc-balance" value="1000" oninput="recalcLotSize()" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono-num font-bold">
                            </div>
                            <div>
                                <label class="text-[10px] text-slate-400 block mb-1">ความเสี่ยงที่รับได้ต่อไม้ (Risk %)</label>
                                <input type="number" id="acc-risk-pct" value="1.5" step="0.1" oninput="recalcLotSize()" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono-num font-bold">
                            </div>
                        </div>
                    </div>

                    <!-- AI Reasoning Box -->
                    <div class="space-y-1">
                        <span class="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                            <i class="fa-solid fa-microchip"></i> สรุปแผนการเทรดจาก AI (ส่งแนบไปกับ LINE OA):
                        </span>
                        <textarea id="setup-reason" rows="2" class="w-full text-xs text-slate-200 bg-slate-950/90 p-3 rounded-xl border border-slate-800 focus:border-amber-500 outline-none leading-relaxed"></textarea>
                    </div>

                    <!-- News Lock Alert Inside Dispatch Panel -->
                    <div id="dispatch-lock-warning" class="hidden p-3 rounded-xl bg-rose-500/20 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2.5">
                        <i class="fa-solid fa-ban text-rose-400 text-base"></i>
                        <span><strong>ระบบล็อกการส่งสัญญาณชั่วคราว!</strong> เนื่องจากอยู่ในช่วงเฝ้าระวังข่าวแรงตามตาราง Forex Factory</span>
                    </div>

                    <!-- Broadcast Signal Button -->
                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="btn-interactive w-full py-3.5 px-4 rounded-xl font-extrabold text-xs md:text-sm bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 text-slate-950 shadow-xl flex items-center justify-center gap-2">
                        <i class="fa-brands fa-line text-lg"></i>
                        <span>ส่งสัญญาณ Fibonacci ชุดนี้เข้า LINE OA แจ้งเตือนลูกค้าทันที</span>
                    </button>
                </div>

                <!-- 3. CUSTOM SWING TUNER (MANUAL OVERRIDE) -->
                <div class="pro-card rounded-2xl p-5 space-y-3">
                    <div class="flex justify-between items-center border-b border-slate-800/80 pb-2.5">
                        <div>
                            <h3 class="text-sm font-bold text-amber-400"><i class="fa-solid fa-sliders mr-1.5"></i>กำหนดจุด Swing High / Low เอง (Manual Fib Override)</h3>
                            <p class="text-[11px] text-slate-400">หากคุณมองเห็นยอด High หรือฐาน Low บนกราฟ TradingView แล้วอยากใส่ตัวเลขเอง กรอกแล้วกดคำนวณได้เลย</p>
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
                            <input type="number" id="custom-high" step="0.1" value="2750.00" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-slate-100 font-mono-num font-bold">
                        </div>
                        <div>
                            <label class="text-slate-400 block mb-1 text-[11px]">Swing Low ($)</label>
                            <input type="number" id="custom-low" step="0.1" value="2715.00" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-slate-100 font-mono-num font-bold">
                        </div>
                    </div>

                    <button onclick="applyCustomSwing()" class="btn-interactive w-full py-2.5 bg-slate-800 hover:bg-amber-500 hover:text-slate-950 text-amber-400 border border-amber-500/40 font-extrabold text-xs rounded-xl">
                        <i class="fa-solid fa-rotate mr-1"></i> คำนวณตาราง Fibonacci และตีเส้นตามค่าที่กรอกทันที
                    </button>
                </div>

                <!-- 4. LIVE SIGNAL FEED & MULTI-TIMEFRAME MATRIX TABS -->
                <div class="pro-card rounded-2xl p-5 space-y-3.5">
                    <div class="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
                        <div class="flex gap-2">
                            <button onclick="switchRightTab('feed')" id="tab-btn-feed" class="btn-interactive px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950">
                                <i class="fa-solid fa-bolt mr-1"></i>ประวัติสัญญาณ (Live Feed)
                            </button>
                            <button onclick="switchRightTab('matrix')" id="tab-btn-matrix" class="btn-interactive px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200">
                                <i class="fa-solid fa-table-cells mr-1"></i>สรุปจุดเข้าทุก TF
                            </button>
                        </div>
                        <span class="text-[11px] text-slate-400 font-mono-num" id="feed-counter-label">2 รายการล่าสุด</span>
                    </div>

                    <div id="right-tab-feed" class="space-y-2.5 max-h-[280px] overflow-y-auto pr-1"></div>
                    <div id="right-tab-matrix" class="hidden space-y-2 max-h-[280px] overflow-y-auto pr-1">
                        <div id="matrix-overview-list" class="space-y-2 text-xs"></div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-emerald-500 text-slate-950 px-4 py-3 rounded-xl font-extrabold text-xs shadow-2xl z-50 flex items-center gap-2">
        <i class="fa-solid fa-circle-check text-base"></i>
        <span id="toast-notify-text">ดำเนินการสำเร็จ!</span>
    </div>

    <!-- TradingView External Script -->
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>

    <script>
        // ==================================================================
        // 1. คณิตศาสตร์ Fibonacci ครบทุกระดับ (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%)
        // ==================================================================
        function calculateSniperMath(direction, swingHigh, swingLow) {
            const range = Math.max(0.5, swingHigh - swingLow);
            let entry, sl, risk, tp1, tp2;
            let fibLevels = [];

            if (direction === 'SELL') {
                // ขาลง: วัดจาก High (100%) ลงมาหา Low (0%) -> รอเด้งขึ้นไปที่ 61.8%
                const f0   = swingLow;
                const f236 = swingLow + (range * 0.236);
                const f382 = swingLow + (range * 0.382);
                const f500 = swingLow + (range * 0.500);
                const f618 = swingLow + (range * 0.618);
                const f786 = swingLow + (range * 0.786);
                const f100 = swingHigh;

                entry = f618;
                sl = f786;
                risk = Math.abs(sl - entry);
                tp1 = entry - (risk * 2);
                tp2 = entry - (risk * 3);

                fibLevels = [
                    { pct: '100.0% (Swing High)', price: f100, color: '#64748b', badge: 'จุดเริ่มต้นสวิงบน' },
                    { pct: '78.6% (Stop Loss)',   price: f786, color: '#f43f5e', badge: '🛑 จุดตัดขาดทุน (SL)', isSL: true },
                    { pct: '61.8% (Golden Zone)', price: f618, color: '#06b6d4', badge: '🔵 จุดเข้า SELL LIMIT', isEntry: true },
                    { pct: '50.0% (Equilibrium)', price: f500, color: '#a855f7', badge: 'กึ่งกลางสวิง' },
                    { pct: '38.2% (Retracement)', price: f382, color: '#3b82f6', badge: 'แนวต้านย่อยแรก' },
                    { pct: '23.6% (Shallow)',     price: f236, color: '#64748b', badge: 'เด้งตื้น' },
                    { pct: '0.0% (Swing Low)',    price: f0,   color: '#64748b', badge: 'ฐานสวิงล่าง' }
                ];
            } else {
                // ขาขึ้น: วัดจาก Low (100%) ขึ้นไปหา High (0%) -> รอย่อลงมาที่ 61.8%
                const f0   = swingHigh;
                const f236 = swingHigh - (range * 0.236);
                const f382 = swingHigh - (range * 0.382);
                const f500 = swingHigh - (range * 0.500);
                const f618 = swingHigh - (range * 0.618);
                const f786 = swingHigh - (range * 0.786);
                const f100 = swingLow;

                entry = f618;
                sl = f786;
                risk = Math.abs(entry - sl);
                tp1 = entry + (risk * 2);
                tp2 = entry + (risk * 3);

                fibLevels = [
                    { pct: '0.0% (Swing High)',   price: f0,   color: '#64748b', badge: 'ยอดสวิงบน' },
                    { pct: '23.6% (Shallow)',     price: f236, color: '#64748b', badge: 'ย่อตื้น' },
                    { pct: '38.2% (Retracement)', price: f382, color: '#3b82f6', badge: 'แนวรับย่อยแรก' },
                    { pct: '50.0% (Equilibrium)', price: f500, color: '#a855f7', badge: 'กึ่งกลางสวิง' },
                    { pct: '61.8% (Golden Zone)', price: f618, color: '#06b6d4', badge: '🔵 จุดเข้า BUY LIMIT', isEntry: true },
                    { pct: '78.6% (Stop Loss)',   price: f786, color: '#f43f5e', badge: '🛑 จุดตัดขาดทุน (SL)', isSL: true },
                    { pct: '100.0% (Swing Low)',  price: f100, color: '#64748b', badge: 'จุดเริ่มต้นสวิงล่าง' }
                ];
            }

            return {
                entryNum: entry, slNum: sl, tp1Num: tp1, tp2Num: tp2,
                entry: entry.toFixed(2), sl: sl.toFixed(2),
                tp1: tp1.toFixed(2), tp2: tp2.toFixed(2),
                riskNum: risk,
                riskDollar: risk.toFixed(2),
                reward1Dollar: (risk * 2).toFixed(2),
                reward2Dollar: (risk * 3).toFixed(2),
                fibLevels
            };
        }

        // ==================================================================
        // 2. ตั้งค่าการดึงข้อมูลแท่งเทียนย้อนหลัง 1,000 แท่งรายไทม์เฟรม
        // ==================================================================
        const timeframeMeta = {
            '1m':    { label: '1 นาที (1M)',    binanceInterval: '1m',  tvInterval: '1',   lookback: 90,  minRange: 1.5 },
            '5m':    { label: '5 นาที (5M)',    binanceInterval: '5m',  tvInterval: '5',   lookback: 96,  minRange: 3.5 },
            '15m':   { label: '15 นาที (15M)',  binanceInterval: '15m', tvInterval: '15',  lookback: 96,  minRange: 6.0 },
            '1h':    { label: '1 ชั่วโมง (1H)', binanceInterval: '1h',  tvInterval: '60',  lookback: 100, minRange: 12.0 },
            '4h':    { label: '4 ชั่วโมง (4H)', binanceInterval: '4h',  tvInterval: '240', lookback: 100, minRange: 22.0 },
            'daily': { label: 'รายวัน (Daily)', binanceInterval: '1d',  tvInterval: 'D',   lookback: 90,  minRange: 40.0 }
        };

        const liveTimeframeStore = {};
        let lwChart = null;
        let candleSeries = null;
        let activePriceLines = [];
        let currentChartMode = 'split';
        let currentTfKey = '1h';
        let currentTvLoadedInterval = null;
        let isNewsLocked = false;
        let currentRiskDollar = 6.50;
        let allCalendarEvents = [];
        let currentNewsFilter = 'ALL';

        function initLightweightChart() {
            const container = document.getElementById('sniper-lw-chart');
            container.innerHTML = '';

            lwChart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 460,
                layout: {
                    background: { type: 'solid', color: '#050912' },
                    textColor: '#cbd5e1',
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
                    scaleMargins: { top: 0.1, bottom: 0.1 }
                },
                timeScale: {
                    borderColor: '#1e293b',
                    timeVisible: true,
                    secondsVisible: false,
                    rightOffset: 12
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

        // ดึงข้อมูลแท่งเทียนจริง 1,000 แท่งย้อนหลัง (เลื่อนดูอดีตได้ไกลจุใจ)
        async function fetchRealGoldCandles(tfKey) {
            const meta = timeframeMeta[tfKey];
            const url = `https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=${meta.binanceInterval}&limit=1000`;
            const res = await fetch(url);
            const raw = await res.json();

            const candles = raw.map(k => ({
                time: Math.floor(k[0] / 1000),
                open: parseFloat(parseFloat(k[1]).toFixed(2)),
                high: parseFloat(parseFloat(k[2]).toFixed(2)),
                low: parseFloat(parseFloat(k[3]).toFixed(2)),
                close: parseFloat(parseFloat(k[4]).toFixed(2))
            }));

            // สแกนหาจุด Swing High และ Swing Low ในช่วงคลื่นล่าสุด (lookback)
            const recentSlice = candles.slice(-meta.lookback);
            let swingHigh = -Infinity, swingLow = Infinity;
            let highIdx = 0, lowIdx = 0;

            recentSlice.forEach((c, idx) => {
                if (c.high > swingHigh) { swingHigh = c.high; highIdx = idx; }
                if (c.low < swingLow) { swingLow = c.low; lowIdx = idx; }
            });

            const currentPrice = candles[candles.length - 1].close;
            const range = swingHigh - swingLow;
            const calcDir = (highIdx < lowIdx) ? 'SELL' : 'BUY';

            const structure = calcDir === 'SELL' ? 'ขาลง (Bearish Swing)' : 'ขาขึ้น (Bullish Swing)';
            const structureClass = calcDir === 'SELL'
                ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40';

            const biasText = calcDir === 'SELL' ? '🔴 ดัก SELL @ 61.8%' : '🟢 ดัก BUY @ 61.8%';
            const biasColor = calcDir === 'SELL' ? 'text-rose-400' : 'text-emerald-400';

            const mathRes = calculateSniperMath(calcDir, swingHigh, swingLow);
            const reason = `คำนวณ Fibonacci อัตโนมัติ (TF ${tfKey.toUpperCase()}): สวิง High $${swingHigh.toFixed(2)} ➔ Low $${swingLow.toFixed(2)} (ระยะ $${range.toFixed(2)}) แนะนำตั้ง ${calcDir} LIMIT ที่ Golden Zone 61.8% ($${mathRes.entry}) SL ที่ 78.6% ($${mathRes.sl}) เป้า TP1 $${mathRes.tp1} และ TP2 $${mathRes.tp2}`;

            liveTimeframeStore[tfKey] = {
                candles, swingHigh, swingLow, currentPrice, range,
                calcDir, structure, structureClass,
                volatility: `$${range.toFixed(2)} (${meta.lookback} แท่งล่าสุด)`,
                biasText, biasColor, reason
            };

            return liveTimeframeStore[tfKey];
        }

        // วาดเส้น Fibonacci ครบทุกระดับลงบนกราฟที่ 2 อัตโนมัติ
        function drawAllFibLinesOnChart(candles, calcDir, swingHigh, swingLow, mathRes) {
            if (!lwChart || !candleSeries) initLightweightChart();

            activePriceLines.forEach(line => {
                try { candleSeries.removePriceLine(line); } catch (e) {}
            });
            activePriceLines = [];

            candleSeries.setData(candles);

            // วาดเส้น Fib ทุกระดับ (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%)
            mathRes.fibLevels.forEach(lvl => {
                let width = 1;
                let style = LightweightCharts.LineStyle.Dotted;
                if (lvl.isEntry || lvl.isSL) {
                    width = 2;
                    style = LightweightCharts.LineStyle.Solid;
                } else if (lvl.pct.includes('50.0%') || lvl.pct.includes('38.2%')) {
                    width = 1;
                    style = LightweightCharts.LineStyle.Dashed;
                }

                const line = candleSeries.createPriceLine({
                    price: lvl.price,
                    color: lvl.color,
                    lineWidth: width,
                    lineStyle: style,
                    axisLabelVisible: true,
                    title: `Fib ${lvl.pct}`
                });
                activePriceLines.push(line);
            });

            // วาดเส้น TP1 (1:2) และ TP2 (1:3)
            activePriceLines.push(candleSeries.createPriceLine({
                price: mathRes.tp1Num, color: '#10b981', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true,
                title: `🟢 TP1 (RR 1:2)`
            }));

            activePriceLines.push(candleSeries.createPriceLine({
                price: mathRes.tp2Num, color: '#f59e0b', lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true,
                title: `🟡 TP2 (RR 1:3)`
            }));

            // ซูมไปที่ช่วง 110 แท่งล่าสุดเพื่อให้เห็นทรงกราฟสวยงามและเลื่อนถอยหลังไปดูอีก 900 แท่งได้อิสระ
            const total = candles.length;
            if (total > 110) {
                lwChart.timeScale().setVisibleLogicalRange({ from: total - 110, to: total + 8 });
            } else {
                lwChart.timeScale().fitContent();
            }
        }

        function resetSniperZoom() {
            const st = liveTimeframeStore[currentTfKey];
            if (lwChart && st && st.candles) {
                const total = st.candles.length;
                lwChart.timeScale().setVisibleLogicalRange({ from: Math.max(0, total - 110), to: total + 8 });
            }
        }

        // สร้างแถบ Visual Fibonacci Ladder แสดงทุกระดับราคา (0% - 100%)
        function renderFibLadderUI(mathRes, currentPrice) {
            const container = document.getElementById('fib-ladder-container');
            container.innerHTML = '';

            mathRes.fibLevels.forEach(lvl => {
                const pStr = lvl.price.toFixed(2);
                const isNear = Math.abs(currentPrice - lvl.price) < (mathRes.riskNum * 0.45);
                let rowBg = 'bg-slate-900/75 border-slate-800';
                if (lvl.isEntry) rowBg = 'bg-cyan-950/60 border-cyan-500/60 shadow-md shadow-cyan-500/10';
                else if (lvl.isSL) rowBg = 'bg-rose-950/60 border-rose-500/60';

                const div = document.createElement('div');
                div.className = `price-card-interactive cursor-pointer flex justify-between items-center px-3 py-2 rounded-lg border ${rowBg}`;
                div.onclick = () => {
                    navigator.clipboard.writeText(pStr);
                    showToast(`✅ คัดลอกราคา Fib ${lvl.pct}: $${pStr} เรียบร้อย!`);
                };
                div.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full" style="background:${lvl.color}"></span>
                        <span class="font-bold text-slate-200">${lvl.pct}</span>
                        <span class="text-[10px] px-2 py-0.5 rounded bg-slate-950 text-slate-300">${lvl.badge}</span>
                        ${isNear ? '<span class="px-1.5 py-0.5 rounded bg-amber-500 text-slate-950 text-[9px] font-black">ราคาใกล้โซนนี้</span>' : ''}
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="font-extrabold text-sm" style="color:${lvl.color}">$${pStr}</span>
                        <i class="fa-regular fa-copy text-slate-500 text-[10px]"></i>
                    </div>
                `;
                container.appendChild(div);
            });

            const now = new Date();
            document.getElementById('fib-last-calc-time').innerText = `คำนวณล่าสุด: ${now.toLocaleTimeString('th-TH')}`;
        }

        // คำนวณ Lot Size อัตโนมัติจากทุนพอร์ตและระยะ SL 78.6%
        function recalcLotSize() {
            const balance = parseFloat(document.getElementById('acc-balance').value) || 1000;
            const riskPct = parseFloat(document.getElementById('acc-risk-pct').value) || 1.5;
            const riskMoney = balance * (riskPct / 100);
            // สำหรับ XAUUSD 1.00 Standard Lot เคลื่อนที่ $1 = $100
            const lossPerOneLot = Math.max(0.5, currentRiskDollar) * 100;
            const rawLot = riskMoney / lossPerOneLot;
            const finalLot = Math.max(0.01, rawLot).toFixed(2);
            document.getElementById('calc-lot-result').innerText = `แนะนำ: ${finalLot} Lot (ความเสี่ยง $${riskMoney.toFixed(1)})`;
        }

        // ==================================================================
        // 3. ปุ่มกด "คำนวณ Fibonacci อัตโนมัติทันที" และการสลับไทม์เฟรม
        // ==================================================================
        async function triggerAutoFibonacciCalculation(showNotification = true) {
            const icon = document.getElementById('fib-spin-icon');
            if (icon) icon.className = "fa-solid fa-spinner fa-spin";
            document.getElementById('autofib-status-text').innerText = `⏳ กำลังสแกนจุด Swing High/Low และตีเส้น Fibonacci...`;

            try {
                const state = await fetchRealGoldCandles(currentTfKey);
                applyStateToUI(currentTfKey, state);
                document.getElementById('autofib-status-text').innerText = `● ตีเส้น Fibonacci อัตโนมัติครบทุกระดับแล้ว (${timeframeMeta[currentTfKey].label})`;
                if (showNotification) {
                    showToast(`⚡ คำนวณและตีเส้น Fibonacci อัตโนมัติ (TF ${currentTfKey.toUpperCase()}) สำเร็จ!`);
                }
            } catch (e) {
                console.error(e);
            } finally {
                if (icon) icon.className = "fa-solid fa-bolt";
            }
        }

        async function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const meta = timeframeMeta[tfKey];
            if (!meta) return;

            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-bold font-mono-num bg-slate-950 text-slate-400 border border-slate-800 hover:border-amber-500/50 hover:text-slate-200";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn btn-interactive py-2.5 px-2 rounded-xl text-xs font-extrabold font-mono-num bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 border border-amber-300 shadow-lg";
            }

            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            document.getElementById('tv-tf-label').innerText = 'TF: ' + tfKey.toUpperCase();

            loadTradingViewStudio(meta.tvInterval);
            await triggerAutoFibonacciCalculation(false);
        }

        function applyStateToUI(tfKey, state) {
            const mathRes = calculateSniperMath(state.calcDir, state.swingHigh, state.swingLow);
            currentRiskDollar = mathRes.riskNum;

            document.getElementById('live-ticker-price').innerText = '$' + state.currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

            const masterBias = document.getElementById('master-daily-bias');
            masterBias.innerText = `${state.calcDir} BIAS @ TF ${tfKey.toUpperCase()} (Entry 61.8%: $${mathRes.entry})`;
            masterBias.className = state.calcDir === 'SELL' ? 'font-extrabold text-rose-400' : 'font-extrabold text-emerald-400';

            const structEl = document.getElementById('tf-structure-badge');
            structEl.innerText = state.structure;
            structEl.className = 'inline-block mt-1 px-2 py-0.5 rounded text-[11px] font-bold ' + state.structureClass;

            document.getElementById('tf-volatility').innerText = state.volatility;

            const biasEl = document.getElementById('tf-bias-text');
            biasEl.innerText = state.biasText;
            biasEl.className = 'block mt-1 font-extrabold text-[11px] ' + state.biasColor;

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
            document.getElementById('setup-swing-info').innerText = `High $${state.swingHigh.toFixed(2)} ➔ Low $${state.swingLow.toFixed(2)}`;

            const orderBadge = document.getElementById('setup-order-badge');
            if (state.calcDir === 'SELL') {
                orderBadge.innerText = '🔻 SELL LIMIT @ 61.8%';
                orderBadge.className = 'px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num bg-rose-500 text-white shadow-lg';
            } else {
                orderBadge.innerText = '🟢 BUY LIMIT @ 61.8%';
                orderBadge.className = 'px-3.5 py-1.5 rounded-xl text-xs font-black font-mono-num bg-emerald-500 text-slate-950 shadow-lg';
            }

            document.getElementById('setup-reason').value = state.reason;
            document.getElementById('custom-dir').value = state.calcDir;
            document.getElementById('custom-high').value = state.swingHigh.toFixed(2);
            document.getElementById('custom-low').value = state.swingLow.toFixed(2);

            renderFibLadderUI(mathRes, state.currentPrice);
            recalcLotSize();
            drawAllFibLinesOnChart(state.candles, state.calcDir, state.swingHigh, state.swingLow, mathRes);
            renderMatrixTable(tfKey);
        }

        function applyCustomSwing() {
            const dir = document.getElementById('custom-dir').value;
            const high = parseFloat(document.getElementById('custom-high').value);
            const low = parseFloat(document.getElementById('custom-low').value);

            if (!high || !low || high <= low) {
                showToast('⚠️ กรุณากรอกราคา Swing High ให้มากกว่า Swing Low');
                return;
            }

            const curState = liveTimeframeStore[currentTfKey];
            if (!curState) return;

            const mathRes = calculateSniperMath(dir, high, low);
            currentRiskDollar = mathRes.riskNum;

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
            document.getElementById('setup-swing-info').innerText = `High $${high.toFixed(2)} ➔ Low $${low.toFixed(2)} (กำหนดเอง)`;

            document.getElementById('setup-reason').value = `กำหนดจุดสวิงเอง (${dir} @ TF ${currentTfKey.toUpperCase()}): High $${high.toFixed(2)} ➔ Low $${low.toFixed(2)} | จุดเข้า Fib 61.8% ($${mathRes.entry}) SL 78.6% ($${mathRes.sl}) TP2 ($${mathRes.tp2})`;

            renderFibLadderUI(mathRes, curState.currentPrice);
            recalcLotSize();
            drawAllFibLinesOnChart(curState.candles, dir, high, low, mathRes);
            showToast('✅ คำนวณตาราง Fibonacci และตีเส้นใหม่ตามค่าที่คุณกำหนดเรียบร้อย!');
        }

        // ==================================================================
        // 4. สลับโหมดการแสดงผลกราฟ (Split View / TradingView แท้ / AI Auto-Fib)
        // ==================================================================
        function switchChartMode(mode) {
            currentChartMode = mode;
            const tvSec = document.getElementById('tv-chart-section');
            const fibSec = document.getElementById('autofib-chart-section');
            const btnSplit = document.getElementById('mode-btn-split');
            const btnTv = document.getElementById('mode-btn-tv');
            const btnFib = document.getElementById('mode-btn-autofib');

            const inactiveClass = "btn-interactive py-2.5 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 bg-slate-950 text-slate-300 border border-slate-800 hover:border-amber-500/50";
            const activeClass = "btn-interactive py-2.5 px-3 rounded-xl text-xs font-extrabold flex items-center justify-center gap-1.5 bg-gradient-to-r from-amber-400 via-amber-500 to-yellow-500 text-slate-950 shadow-lg";

            btnSplit.className = mode === 'split' ? activeClass : inactiveClass;
            btnTv.className = mode === 'tv' ? activeClass : inactiveClass;
            btnFib.className = mode === 'autofib' ? activeClass : inactiveClass;

            if (mode === 'split') {
                tvSec.classList.remove('hidden');
                fibSec.classList.remove('hidden');
            } else if (mode === 'tv') {
                tvSec.classList.remove('hidden');
                fibSec.classList.add('hidden');
            } else {
                tvSec.classList.add('hidden');
                fibSec.classList.remove('hidden');
            }

            setTimeout(() => {
                if (lwChart) {
                    const container = document.getElementById('sniper-lw-chart');
                    if (container.clientWidth > 0) lwChart.applyOptions({ width: container.clientWidth });
                }
            }, 60);
        }

        function loadTradingViewStudio(intervalCode) {
            if (currentTvLoadedInterval === intervalCode) return;
            currentTvLoadedInterval = intervalCode;
            const container = document.getElementById('tradingview_studio_chart');
            container.innerHTML = '';
            new TradingView.widget({
                "width": "100%",
                "height": "460",
                "symbol": "OANDA:XAUUSD",
                "interval": intervalCode,
                "timezone": "Asia/Bangkok",
                "theme": "dark",
                "style": "1",
                "locale": "th",
                "toolbar_bg": "#050912",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "studies": [
                    "STD;Auto%1Fib%1Retracement",
                    "RSI@tv-basicstudies"
                ],
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
                btnFeed.className = "btn-interactive px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950";
                btnMatrix.className = "btn-interactive px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200";
            } else {
                feedBox.classList.add('hidden');
                matrixBox.classList.remove('hidden');
                btnMatrix.className = "btn-interactive px-3 py-1.5 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950";
                btnFeed.className = "btn-interactive px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200";
            }
        }

        function renderMatrixTable(activeKey) {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';

            Object.keys(timeframeMeta).forEach(key => {
                const st = liveTimeframeStore[key];
                if (!st) return;
                const lvls = calculateSniperMath(st.calcDir, st.swingHigh, st.swingLow);
                const isSelected = key === activeKey;

                const row = document.createElement('div');
                row.className = `price-card-interactive flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-xl border cursor-pointer gap-2 ${
                    isSelected ? 'bg-amber-500/15 border-amber-500/60' : 'bg-slate-950/90 border-slate-800 hover:border-slate-700'
                }`;
                row.onclick = () => selectTimeframe(key);
                row.innerHTML = `
                    <div class="flex items-center gap-2.5">
                        <span class="font-black font-mono-num text-amber-400 w-12 uppercase">${key}</span>
                        <span class="px-2 py-0.5 rounded text-[10px] font-bold ${st.structureClass}">${st.calcDir} • ${st.structure}</span>
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

        async function preloadAllTimeframes() {
            for (const k of Object.keys(timeframeMeta)) {
                if (k !== currentTfKey) {
                    try { await fetchRealGoldCandles(k); } catch (e) {}
                }
            }
            renderMatrixTable(currentTfKey);
        }

        // ==================================================================
        // 5. ระบบปฏิทินข่าว Forex Factory (ระบุวัน-เดือน-ปี + กรองข่าว + Auto-Lock)
        // ==================================================================
        async function loadSystemState() {
            try {
                const res = await fetch('/api/system-state');
                const data = await res.json();
                isNewsLocked = data.news_locked;
                allCalendarEvents = data.economic_calendar || [];
                updateNewsShieldUI(isNewsLocked, data.lock_reason);
                renderCalendarTable();
                renderSignalFeed(data.signal_history);
                updateNextHighNewsBanner();
            } catch (e) { console.error(e); }
        }

        function updateNextHighNewsBanner() {
            const badge = document.getElementById('next-high-news-badge');
            const upcomingHigh = allCalendarEvents.find(ev => ev.impact === 'HIGH' && ev.urgency !== 'PAST');
            if (upcomingHigh) {
                badge.innerText = `🔴 ${upcomingHigh.event.split('(')[0]} (${upcomingHigh.date_label} ${upcomingHigh.time_label})`;
            } else {
                badge.innerText = `✅ ไม่มีข่าวแดงค้างในสัปดาห์นี้`;
                badge.className = "px-2.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs";
            }
        }

        function filterNews(mode) {
            currentNewsFilter = mode;
            ['ALL', 'TODAY', 'HIGH'].forEach(m => {
                const btn = document.getElementById('news-filter-' + m);
                if (m === mode) {
                    btn.className = "btn-interactive px-3 py-1.5 rounded-xl text-xs font-extrabold bg-amber-500 text-slate-950";
                } else {
                    btn.className = "btn-interactive px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-950 text-slate-300 border border-slate-800";
                }
            });
            renderCalendarTable();
        }

        function renderCalendarTable() {
            const tbody = document.getElementById('economic-calendar-body');
            tbody.innerHTML = '';

            const filtered = allCalendarEvents.filter(item => {
                if (currentNewsFilter === 'TODAY') return item.urgency === 'TODAY' || item.urgency === 'NOW';
                if (currentNewsFilter === 'HIGH') return item.impact === 'HIGH';
                return true;
            });

            if (filtered.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-slate-400">ไม่มีรายการข่าวเศรษฐกิจในหมวดที่เลือก</td></tr>`;
                return;
            }

            filtered.forEach(item => {
                let badge = '', statusBadge = '', countdownStyle = 'text-slate-300';
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

                if (item.urgency === 'NOW') countdownStyle = 'text-rose-400 font-extrabold animate-pulse';
                else if (item.urgency === 'TODAY') countdownStyle = 'text-amber-400 font-bold';
                else if (item.urgency === 'PAST') countdownStyle = 'text-slate-500';

                const rowHighlight = (item.urgency === 'TODAY' || item.urgency === 'NOW')
                    ? 'bg-amber-500/5 hover:bg-amber-500/10'
                    : 'hover:bg-slate-900/50';

                const tr = document.createElement('tr');
                tr.className = `${rowHighlight} transition`;
                tr.innerHTML = `
                    <td class="py-3 px-2 font-bold text-amber-300 whitespace-nowrap">${item.date_label}</td>
                    <td class="py-3 px-2 font-mono-num font-bold text-white whitespace-nowrap">${item.time_label}</td>
                    <td class="py-3 px-2 font-semibold text-slate-100">${item.event}</td>
                    <td class="py-3 px-2 whitespace-nowrap">${badge}</td>
                    <td class="py-3 px-2 font-mono-num text-slate-300 whitespace-nowrap">${item.forecast} / <span class="text-slate-500">${item.previous}</span></td>
                    <td class="py-3 px-2 text-[11px] whitespace-nowrap ${countdownStyle}">${item.countdown}</td>
                    <td class="py-3 px-2 text-right font-mono-num text-[11px] whitespace-nowrap">${statusBadge}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        function updateNewsShieldUI(locked, reasonText) {
            const box = document.getElementById('news-shield-box');
            const dot = document.getElementById('shield-dot');
            const text = document.getElementById('shield-status-text');
            const warn = document.getElementById('dispatch-lock-warning');
            const btn = document.getElementById('broadcast-btn');

            if (locked) {
                box.className = "bg-rose-950/60 border border-rose-500/60 px-3.5 py-2 rounded-xl flex items-center gap-3 transition-all";
                dot.className = "w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping";
                text.className = "text-xs font-extrabold text-rose-400";
                text.innerText = reasonText || "NEWS LOCKED (งดส่งสัญญาณช่วงข่าวแดง)";
                warn.classList.remove('hidden');
                btn.disabled = true;
                btn.className = "w-full py-3.5 px-4 rounded-xl font-extrabold text-xs md:text-sm bg-slate-800 text-slate-500 cursor-not-allowed flex items-center justify-center gap-2";
            } else {
                box.className = "bg-emerald-950/40 border border-emerald-500/40 px-3.5 py-2 rounded-xl flex items-center gap-3 transition-all";
                dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping";
                text.className = "text-xs font-extrabold text-emerald-400";
                text.innerText = "SAFE MODE (เปิดส่งสัญญาณปกติ)";
                warn.classList.add('hidden');
                btn.disabled = false;
                btn.className = "btn-interactive w-full py-3.5 px-4 rounded-xl font-extrabold text-xs md:text-sm bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 text-slate-950 shadow-xl flex items-center justify-center gap-2";
            }
        }

        async function toggleNewsLock() {
            try {
                const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
                const data = await res.json();
                isNewsLocked = data.news_locked;
                updateNewsShieldUI(isNewsLocked, data.lock_reason);
                showToast(isNewsLocked ? '🛡️ เปิดโหมดล็อกสัญญาณช่วงข่าวแรงแล้ว!' : '✅ ปลดล็อกระบบ เปิดส่งสัญญาณตามปกติ');
            } catch (e) {}
        }

        async function addNewsItem() {
            const dateVal = document.getElementById('new-news-date').value;
            const timeVal = document.getElementById('new-news-time').value || '19:30';
            const eventVal = document.getElementById('new-news-Event').value;
            const impactVal = document.getElementById('new-news-impact').value;
            if (!eventVal) { showToast('⚠️ กรุณาระบุชื่อข่าวเศรษฐกิจ'); return; }

            const res = await fetch('/api/add-news', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: dateVal, time: timeVal, event: eventVal, impact: impactVal })
            });
            const data = await res.json();
            allCalendarEvents = data.economic_calendar;
            renderCalendarTable();
            updateNextHighNewsBanner();
            document.getElementById('add-news-modal').classList.add('hidden');
            document.getElementById('new-news-Event').value = '';
            showToast('✅ เพิ่มรายการข่าวพร้อมระบุวัน-เวลาเรียบร้อย!');
        }

        function renderSignalFeed(signals) {
            const container = document.getElementById('right-tab-feed');
            document.getElementById('feed-counter-label').innerText = `${signals.length} รายการล่าสุด`;
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
                        <span class="text-[10px] font-mono-num text-slate-400"><i class="fa-regular fa-clock mr-1"></i>${sig.date || ''} ${sig.time}</span>
                    </div>
                    <div class="grid grid-cols-4 gap-1.5 pt-1 text-[11px] font-mono-num">
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">ENTRY</span><span class="text-cyan-400 font-bold">$${sig.entry}</span></div>
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">SL (78.6%)</span><span class="text-rose-400 font-bold">$${sig.sl}</span></div>
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">TP1 (1:2)</span><span class="text-emerald-400 font-bold">$${sig.tp1}</span></div>
                        <div class="bg-slate-900 px-2 py-1 rounded"><span class="text-slate-500 block text-[9px]">TP2 (1:3)</span><span class="text-amber-400 font-bold">$${sig.tp2}</span></div>
                    </div>
                    <div class="flex justify-between items-center pt-1 text-[11px]">
                        <span class="text-slate-400 truncate max-w-[70%]">${sig.reason}</span>
                        <span class="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 font-mono-num text-[10px] font-bold">${sig.status}</span>
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
                lot_advice: document.getElementById('calc-lot-result').innerText,
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
                showToast('🚀 ส่งสัญญาณ Fibonacci เข้า LINE OA และบันทึกในระบบเรียบร้อย!');
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
            setTimeout(() => toast.classList.add('hidden'), 2800);
        }

        // อัปเดตเฉพาะราคาแท่งเทียนปัจจุบันเบาๆ โดยไม่รบกวนเส้น Fibonacci ที่คำนวณไว้แล้ว
        setInterval(async () => {
            try {
                const meta = timeframeMeta[currentTfKey];
                const res = await fetch(`https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=${meta.binanceInterval}&limit=1`);
                const data = await res.json();
                if (data && data.length > 0 && candleSeries) {
                    const k = data[0];
                    const liveCandle = {
                        time: Math.floor(k[0] / 1000),
                        open: parseFloat(parseFloat(k[1]).toFixed(2)),
                        high: parseFloat(parseFloat(k[2]).toFixed(2)),
                        low: parseFloat(parseFloat(k[3]).toFixed(2)),
                        close: parseFloat(parseFloat(k[4]).toFixed(2))
                    };
                    candleSeries.update(liveCandle);
                    document.getElementById('live-ticker-price').innerText = '$' + liveCandle.close.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                }
            } catch (e) {}
        }, 4000);

        window.addEventListener('DOMContentLoaded', async () => {
            const now = new Date();
            document.getElementById('current-date-label').innerText = 'วัน-เวลาปัจจุบัน: ' + now.toLocaleDateString('th-TH', {
                weekday: 'short', year: 'numeric', month: 'short', day: 'numeric'
            });
            document.getElementById('new-news-date').value = now.toISOString().split('T')[0];

            initLightweightChart();
            await selectTimeframe('1h');
            await loadSystemState();
            preloadAllTimeframes();
        });
    </script>
</body>
</html>
"""


# ==============================================================================
# BACKEND API ENDPOINTS (ดึงข่าวจริง Forex Factory + ส่ง LINE OA)
# ==============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/system-state', methods=['GET'])
def get_system_state():
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()

    # ตรวจสอบว่ามีข่าวแดงที่กำลังอยู่ในช่วงเวลา ±30 นาทีตอนนี้หรือไม่
    auto_locking_event = next((ev for ev in calendar_events if ev.get("is_locking_now")), None)
    is_locked = SYSTEM_STATE["manual_news_lock"] or (auto_locking_event is not None)

    if auto_locking_event:
        lock_reason = f"ล็อกอัตโนมัติ: ข่าวแดง {auto_locking_event['event']} ({auto_locking_event['time_label']})"
    elif SYSTEM_STATE["manual_news_lock"]:
        lock_reason = "NEWS LOCKED (เปิดโหมดล็อกข่าวด้วยตัวเอง)"
    else:
        lock_reason = "SAFE MODE (ตลาดปกติ)"

    return jsonify({
        "safe_to_trade": not is_locked,
        "news_locked": is_locked,
        "lock_reason": lock_reason,
        "latest_signal": SYSTEM_STATE["latest_signal"],
        "signal_history": SYSTEM_STATE["signal_history"],
        "economic_calendar": calendar_events,
        "server_time": now_dt.strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/api/toggle-news-lock', methods=['POST'])
def toggle_news_lock():
    SYSTEM_STATE["manual_news_lock"] = not SYSTEM_STATE["manual_news_lock"]
    lock_reason = (
        "NEWS LOCKED (ล็อกการส่งสัญญาณช่วงข่าวแดง)"
        if SYSTEM_STATE["manual_news_lock"]
        else "SAFE MODE (เปิดรับสัญญาณปกติ)"
    )
    return jsonify({
        "status": "ok",
        "news_locked": SYSTEM_STATE["manual_news_lock"],
        "lock_reason": lock_reason
    })


@app.route('/api/add-news', methods=['POST'])
def add_news():
    data = request.json or {}
    now_dt = datetime.now(TH_TZ)
    date_str = data.get("date") or now_dt.strftime("%Y-%m-%d")
    time_str = data.get("time") or "19:30"
    impact = data.get("impact", "HIGH").upper()

    try:
        dt_parsed = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=TH_TZ)
    except Exception:
        dt_parsed = now_dt

    countdown, urgency, is_locking = compute_countdown_and_lock(dt_parsed, now_dt, impact)
    lock_start = (dt_parsed - timedelta(minutes=30)).strftime("%H:%M")
    lock_end = (dt_parsed + timedelta(minutes=30)).strftime("%H:%M")

    new_item = {
        "timestamp": int(dt_parsed.timestamp()),
        "date_label": format_thai_date(dt_parsed),
        "iso_date": dt_parsed.strftime("%Y-%m-%d"),
        "time_label": dt_parsed.strftime("%H:%M น."),
        "currency": "USD",
        "event": data.get("event", "Custom Economic Event"),
        "impact": impact,
        "forecast": "-",
        "previous": "-",
        "countdown": countdown,
        "urgency": urgency,
        "is_locking_now": is_locking,
        "status": f"ล็อกอัตโนมัติ {lock_start}-{lock_end} น." if impact == "HIGH" else "ลดขนาด Lot 50%",
        "source": "Custom"
    }
    SYSTEM_STATE["custom_news"].insert(0, new_item)
    return jsonify({"status": "ok", "economic_calendar": fetch_forex_factory_calendar()})


@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()
    auto_locking_event = next((ev for ev in calendar_events if ev.get("is_locking_now")), None)

    if SYSTEM_STATE["manual_news_lock"] or auto_locking_event:
        return jsonify({
            "status": "blocked",
            "message": "ระบบล็อกการส่งสัญญาณเนื่องจากอยู่ในช่วงเฝ้าระวังข่าวแรง (News Shield Active)"
        }), 403

    data = request.json or {}
    sig = {
        "id": len(SYSTEM_STATE["signal_history"]) + 101,
        "date": format_thai_date(now_dt),
        "time": now_dt.strftime("%H:%M:%S"),
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

    SYSTEM_STATE["latest_signal"] = sig
    SYSTEM_STATE["signal_history"].insert(0, sig)

    icon = "🔻" if sig["direction"] == "SELL" else "🟢"
    lot_advice = data.get("lot_advice", "คุมความเสี่ยง 1-1.5% ต่อไม้")
    msg = (
        f"🎯 GOLD AI SNIPER PRO (FIB 61.8%)\n"
        f"📅 {sig['date']} เวลา {sig['time']} น.\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 สินทรัพย์: {sig['symbol']} (TF: {sig['tf']})\n"
        f"⚡ คำสั่ง: {icon} {sig['direction']} LIMIT\n"
        f"🔵 จุดเข้า (Entry 61.8%): ${sig['entry']}\n"
        f"🔴 ตัดขาดทุน (SL 78.6%): ${sig['sl']}\n"
        f"🟢 เป้าที่ 1 (TP1 1:2): ${sig['tp1']}\n"
        f"🟡 เป้าหลัก (TP2 1:3): ${sig['tp2']}\n"
        f"⚖️ ขนาดพอร์ต: {lot_advice}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧠 วิเคราะห์: {sig['reason']}"
    )

    notify_line(msg)

    return jsonify({
        "status": "success",
        "latest_signal": sig,
        "signal_history": SYSTEM_STATE["signal_history"]
    })


def notify_line(text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return
    try:
        payload = json.dumps({
            "messages": [{"type": "text", "text": text}]
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
