import os
import json
import time
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# ==============================================================================
# 1. ตั้งค่า TELEGRAM BOT API (ใส่ Token ของคุณซีไว้ให้พร้อมใช้งาน)
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN", 
    "8718020170:AAFj1pPh4HLi8iVaz12hi_qAD_J4Dnlz1g"
)
TELEGRAM_BOT_USERNAME = "gold_ai_sniper_pro_bot"

# เขตเวลาประเทศไทย (UTC+7)
TH_TZ = timezone(timedelta(hours=7))

# แคชข้อมูลข่าว Forex Factory
FF_CACHE = {
    "last_fetched": 0,
    "events": []
}

# ฐานข้อมูลจำลองสำหรับเก็บข้อมูลผู้ใช้และตั้งค่าการแจ้งเตือน (MVP)
USERS_DB = {}

# สถานะระบบหลัก
SYSTEM_STATE = {
    "manual_news_lock": False,
    "lock_reason": "ตลาดปกติ (Normal Market Conditions)",
    "latest_signal": None,
    "last_alert_ memory": {},  # ป้องกันการส่งแจ้งเตือนซ้ำในสวิงเดิม
    "signal_history": [
        {
            "id": 102,
            "date": "25 ต.ค. 2026",
            "time": "16:30:00",
            "symbol": "XAUUSD",
            "tf": "5M",
            "direction": "SELL",
            "fib_05": "2736.80",
            "entry": "2738.50",
            "sl": "2745.20",
            "tp1": "2725.10",
            "tp2": "2718.40",
            "rr": "1:3",
            "status": "TELEGRAM SENT",
            "reason": "ราคาแตะระดับเฝ้าระวัง 0.5 และเข้าโซนคำนวณทางเทคนิค 61.8%"
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
    day_name = THAI_DAYS[dt_obj.weekday()]
    month_name = THAI_MONTHS[dt_obj.month]
    return f"{day_name} {dt_obj.day} {month_name} {dt_obj.year}"


# ==============================================================================
# 2. ฟังก์ชันจัดการ TELEGRAM BOT & ค้นหา CHAT ID อัตโนมัติ
# ==============================================================================
def send_telegram_message(chat_id, text):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False, "Missing Bot Token or Chat ID"
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": str(chat_id).strip(),
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            return res_data.get("ok", False), "Sent"
    except Exception as e:
        print("Telegram Send Error:", e)
        return False, str(e)


def fetch_latest_telegram_chat_id():
    """ดึง Chat ID ล่าสุดจากคนที่เพิ่งกด /start ในบอท"""
    if not TELEGRAM_BOT_TOKEN:
        return None, None
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=10"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok") and data.get("result"):
                for item in reversed(data["result"]):
                    msg = item.get("message") or item.get("my_chat_member")
                    if msg and "chat" in msg:
                        chat_id = str(msg["chat"]["id"])
                        first_name = msg["chat"].get("first_name", "Trader")
                        return chat_id, first_name
    except Exception as e:
        print("Telegram getUpdates Error:", e)
    return None, None


# ==============================================================================
# 3. ฟังก์ชันคำนวณ FIBONACCI (รวมระดับ 0.5, 61.8%, 78.6%) & ดึงราคาหลังบ้าน
# ==============================================================================
def calculate_fib_levels(direction, swing_high, swing_low):
    rng = max(0.5, swing_high - swing_low)
    if direction == "SELL":
        fib_05 = swing_low + (rng * 0.500)
        entry = swing_low + (rng * 0.618)
        sl = swing_low + (rng * 0.786)
        risk = abs(sl - entry)
        tp1 = entry - (risk * 2)
        tp2 = entry - (risk * 3)
    else:
        fib_05 = swing_high - (rng * 0.500)
        entry = swing_high - (rng * 0.618)
        sl = swing_high - (rng * 0.786)
        risk = abs(entry - sl)
        tp1 = entry + (risk * 2)
        tp2 = entry + (risk * 3)

    return {
        "direction": direction,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "fib_05": round(fib_05, 2),
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "risk": round(risk, 2)
    }


def fetch_server_gold_candles(tf_key="5m"):
    tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "daily": "1d"}
    b_tf = tf_map.get(tf_key.lower(), "5m")
    url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={b_tf}&limit=100"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    swing_high = -1e9
    swing_low = 1e9
    high_idx = 0
    low_idx = 0

    for idx, k in enumerate(raw):
        h = float(k[2])
        l = float(k[3])
        if h > swing_high:
            swing_high = h
            high_idx = idx
        if l < swing_low:
            swing_low = l
            low_idx = idx

    current_price = float(raw[-1][4])
    direction = "SELL" if high_idx < low_idx else "BUY"
    levels = calculate_fib_levels(direction, swing_high, swing_low)
    levels["current_price"] = round(current_price, 2)
    return levels


def is_within_schedule(now_dt, start_str, end_str):
    try:
        cur_mins = now_dt.hour * 60 + now_dt.minute
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        if start_mins <= end_mins:
            return start_mins <= cur_mins <= end_mins
        else:
            return cur_mins >= start_mins or cur_mins <= end_mins
    except Exception:
        return True


def background_price_scanner():
    """รันหลังบ้านตลอด 24 ชม. เพื่อเช็กราคาแตะ 0.5 หรือ 61.8% แล้วส่งเข้า Telegram อัตโนมัติ"""
    while True:
        try:
            now_dt = datetime.now(TH_TZ)
            calendar_events = fetch_forex_factory_calendar()
            auto_locking = any(ev.get("is_locking_now") for ev in calendar_events)
            is_locked = SYSTEM_STATE["manual_news_lock"] or auto_locking

            if not is_locked and USERS_DB:
                # รวบรวม Timeframe ที่ผู้ใช้ตั้งค่าไว้
                active_tfs = set()
                for u in USERS_DB.values():
                    if u.get("chat_id") and u.get("auto_alert", True):
                        active_tfs.add(u.get("preferred_tf", "5m").lower())

                tf_data_cache = {}
                for tf in active_tfs:
                    try:
                        tf_data_cache[tf] = fetch_server_gold_candles(tf)
                    except Exception:
                        pass

                for email, user in list(USERS_DB.items()):
                    chat_id = user.get("chat_id")
                    if not chat_id or not user.get("auto_alert", True):
                        continue

                    if not is_within_schedule(now_dt, user.get("start_time", "08:00"), user.get("end_time", "23:59")):
                        continue

                    tf = user.get("preferred_tf", "5m").lower()
                    data = tf_data_cache.get(tf)
                    if not data:
                        continue

                    price = data["current_price"]
                    fib_05 = data["fib_05"]
                    entry_618 = data["entry"]
                    direction = data["direction"]
                    rng = max(1.0, data["swing_high"] - data["swing_low"])
                    tolerance = max(0.45, rng * 0.035)  # ระยะบัฟเฟอร์แตะโซน

                    swing_key = f"{email}_{tf}_{data['swing_high']}_{data['swing_low']}"
                    mem = SYSTEM_STATE["last_alert_ memory"].get(swing_key, {})

                    # 1. เช็กการแตะระดับ 0.5 (แจ้งเตือนล่วงหน้า)
                    if user.get("alert_05", True) and not mem.get("sent_05"):
                        if abs(price - fib_05) <= tolerance:
                            msg_05 = (
                                f"⚠️ <b>[เตรียมตัว] ราคาแตะระดับ 0.5 (50.0%)</b>\n"
                                f"📊 <b>XAUUSD ({tf.upper()})</b> • โครงสร้างฝั่ง <b>{direction}</b>\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"🟡 <b>ราคาปัจจุบัน:</b> ${price:.2f}\n"
                                f"🔔 <b>ระดับ 0.5 (เตรียมตัว):</b> ${fib_05:.2f}\n"
                                f"🔵 <b>โซน 61.8% ถัดไป:</b> ${entry_618:.2f}\n"
                                f"🔴 <b>ระยะอ้างอิง 78.6%:</b> ${data['sl']:.2f}\n"
                                f"🟢 <b>เป้าสถิติ TP1 / TP2:</b> ${data['tp1']:.2f} / ${data['tp2']:.2f}"
                            )
                            ok, _ = send_telegram_message(chat_id, msg_05)
                            if ok:
                                mem["sent_05"] = True
                                SYSTEM_STATE["last_alert_ memory"][swing_key] = mem

                    # 2. เช็กการแตะระดับ 61.8% (Golden Zone)
                    if user.get("alert_618", True) and not mem.get("sent_618"):
                        if abs(price - entry_618) <= tolerance:
                            msg_618 = (
                                f"🎯 <b>[เข้าโซน] ราคาแตะ Golden Zone 61.8%</b>\n"
                                f"📊 <b>XAUUSD ({tf.upper()})</b> • โครงสร้างฝั่ง <b>{direction}</b>\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"🔵 <b>ระดับ 61.8%:</b> ${entry_618:.2f}\n"
                                f"🔴 <b>ระดับ 78.6% (SL):</b> ${data['sl']:.2f}\n"
                                f"🟢 <b>TP1 (1:2):</b> ${data['tp1']:.2f}\n"
                                f"🟡 <b>TP2 (1:3):</b> ${data['tp2']:.2f}"
                            )
                            ok, _ = send_telegram_message(chat_id, msg_618)
                            if ok:
                                mem["sent_618"] = True
                                SYSTEM_STATE["last_alert_ memory"][swing_key] = mem

        except Exception as e:
            print("Background Scanner Error:", e)
        time.sleep(25)


# เริ่มรัน Background Scanner อัตโนมัติ
scanner_thread = threading.Thread(target=background_price_scanner, daemon=True)
scanner_thread.start()


# ==============================================================================
# 4. ฟังก์ชันจัดการตารางข่าว FOREX FACTORY
# ==============================================================================
def compute_countdown_and_lock(event_dt, now_dt, impact):
    diff_sec = (event_dt - now_dt).total_seconds()
    is_same_day = (event_dt.date() == now_dt.date())
    is_tomorrow = (event_dt.date() == (now_dt.date() + timedelta(days=1)))
    is_auto_locking_now = (impact == "HIGH" and -1800 <= diff_sec <= 1800)

    if -1800 <= diff_sec <= 1800:
        countdown = "🔥 กำลังประกาศข่าว! (เฝ้าระวัง ±30 นาที)"
        urgency = "NOW"
    elif diff_sec < -1800:
        countdown = "ประกาศผลแล้ว"
        urgency = "PAST"
    else:
        hours = int(diff_sec // 3600)
        mins = int((diff_sec % 3600) // 60)
        days = int(diff_sec // 86400)
        if is_same_day:
            countdown = f"วันนี้ • อีก {hours} ชม. {mins} นาที" if hours > 0 else f"⚠️ วันนี้ • อีก {mins} นาที!"
            urgency = "TODAY"
        elif is_tomorrow:
            countdown = f"พรุ่งนี้ • เวลา {event_dt.strftime('%H:%M')} น."
            urgency = "TOMORROW"
        else:
            countdown = f"อีก {days} วัน ({format_thai_date(event_dt)})"
            urgency = "FUTURE"

    return countdown, urgency, is_auto_locking_now


def get_fallback_forex_factory_schedule(now_dt):
    base_date = now_dt.date()
    monday = base_date + timedelta(days=1) if now_dt.weekday() == 6 else base_date - timedelta(days=now_dt.weekday())

    template_events = [
        (0, 21, 0, "USD", "CB Consumer Confidence (ดัชนีความเชื่อมั่นผู้บริโภค)", "MEDIUM", "99.5", "98.7"),
        (1, 19, 30, "USD", "Prelim GDP q/q (ตัวเลข GDP สหรัฐฯ)", "HIGH", "2.9%", "3.0%"),
        (2, 19, 15, "USD", "ADP Non-Farm Employment Change", "HIGH", "115K", "143K"),
        (2, 19, 30, "USD", "Core CPI / PCE Price Index m/m (เงินเฟ้อสหรัฐฯ)", "HIGH", "0.3%", "0.2%"),
        (3, 19, 30, "USD", "Unemployment Claims (ผู้ขอรับสวัสดิการว่างงาน)", "HIGH", "222K", "227K"),
        (4, 19, 30, "USD", "Non-Farm Employment Change - NFP", "HIGH", "148K", "254K"),
        (4, 21, 0, "USD", "ISM Manufacturing PMI (ดัชนีภาคการผลิต)", "HIGH", "47.6", "47.2"),
    ]

    results = []
    for day_offset, hr, mn, curr, title, impact, forecast, previous in template_events:
        ev_date = monday + timedelta(days=day_offset)
        ev_dt = datetime(ev_date.year, ev_date.month, ev_date.day, hr, mn, tzinfo=TH_TZ)
        countdown, urgency, is_locking = compute_countdown_and_lock(ev_dt, now_dt, impact)
        lock_start = (ev_dt - timedelta(minutes=30)).strftime("%H:%M")
        lock_end = (ev_dt + timedelta(minutes=30)).strftime("%H:%M")
        rule_text = f"ล็อกอัตโนมัติ {lock_start}-{lock_end} น." if impact == "HIGH" else "ลดขนาด Lot 50%"

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
            "status": rule_text
        })
    return results


def fetch_forex_factory_calendar():
    now_dt = datetime.now(TH_TZ)
    now_ts = now_dt.timestamp()

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
        except Exception:
            pass

    parsed_events = []
    if raw_list:
        for item in raw_list:
            if item.get("country") != "USD":
                continue
            impact_raw = item.get("impact", "Low").upper()
            if impact_raw not in ["HIGH", "MEDIUM", "LOW"]:
                continue
            try:
                ev_dt = datetime.fromisoformat(item.get("date", "")).astimezone(TH_TZ)
            except Exception:
                continue

            countdown, urgency, is_locking = compute_countdown_and_lock(ev_dt, now_dt, impact_raw)
            lock_start = (ev_dt - timedelta(minutes=30)).strftime("%H:%M")
            lock_end = (ev_dt + timedelta(minutes=30)).strftime("%H:%M")
            rule_text = f"ล็อกอัตโนมัติ {lock_start}-{lock_end} น." if impact_raw == "HIGH" else "ระวังความผันผวน"

            parsed_events.append({
                "timestamp": int(ev_dt.timestamp()),
                "date_label": format_thai_date(ev_dt),
                "iso_date": ev_dt.strftime("%Y-%m-%d"),
                "time_label": ev_dt.strftime("%H:%M น."),
                "currency": "USD",
                "event": item.get("title", "USD Event"),
                "impact": impact_raw,
                "forecast": item.get("forecast") or "-",
                "previous": item.get("previous") or "-",
                "countdown": countdown,
                "urgency": urgency,
                "is_locking_now": is_locking,
                "status": rule_text
            })

    if not parsed_events:
        parsed_events = get_fallback_forex_factory_schedule(now_dt)

    all_events = SYSTEM_STATE["custom_news"] + parsed_events
    all_events.sort(key=lambda x: x.get("timestamp", 0))
    return all_events


# ==============================================================================
# 5. FRONTEND HTML TEMPLATE (CLEAN UI + TELEGRAM BOT + 0.5 ALERT + LOGIN MVP)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — Auto Fibonacci Calculator & Telegram Alert</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #03060c;
            --bg-card: rgba(13, 20, 36, 0.88);
            --border-subtle: rgba(255, 255, 255, 0.08);
        }
        body {
            font-family: 'Prompt', sans-serif;
            background-color: var(--bg-deep);
            background-image: 
                radial-gradient(circle at 10% 5%, rgba(245, 158, 11, 0.08), transparent 35%),
                radial-gradient(circle at 90% 10%, rgba(6, 182, 212, 0.08), transparent 35%);
            color: #f1f5f9;
            overflow-x: hidden;
        }
        .font-mono-num { font-family: 'JetBrains Mono', monospace; }
        .pro-card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-subtle);
            box-shadow: 0 18px 40px -15px rgba(0, 0, 0, 0.7);
        }
        .pro-card-gold {
            background: linear-gradient(145deg, rgba(18, 27, 48, 0.95), rgba(9, 14, 26, 0.98));
            border: 1px solid rgba(245, 158, 11, 0.4);
        }
        .btn-interactive {
            transition: all 0.2s ease;
        }
        .btn-interactive:hover:not(:disabled) {
            transform: translateY(-2px);
        }
        .btn-interactive:active:not(:disabled) {
            transform: translateY(0px) scale(0.98);
        }
        .price-box {
            transition: all 0.2s ease;
        }
        .price-box:hover {
            transform: translateY(-2px);
            border-color: rgba(255,255,255,0.3);
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #03060c; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 9999px; }
    </style>
</head>
<body class="antialiased min-h-screen p-3 md:p-5">

    <!-- ==================================================================== -->
    <!-- MODAL 1: หน้าเข้าสู่ระบบด้วย Email + กดยอมรับเงื่อนไข (Disclaimer)   -->
    <!-- ==================================================================== -->
    <div id="auth-modal" class="fixed inset-0 bg-slate-950/90 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="pro-card pro-card-gold rounded-2xl max-w-md w-full p-6 space-y-5 border border-amber-500/40">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-400 to-yellow-600 flex items-center justify-center text-slate-950 font-black text-xl shadow-lg">
                    XAU
                </div>
                <div>
                    <h2 class="text-lg font-black text-white">เข้าสู่ระบบ GOLD AI SNIPER PRO</h2>
                    <p class="text-xs text-amber-300">ระบบคำนวณกรอบราคา Fibonacci & แจ้งเตือน Telegram</p>
                </div>
            </div>

            <div class="space-y-3 text-xs">
                <div>
                    <label class="text-slate-300 font-bold block mb-1">อีเมลผู้ใช้งาน (Email Address)</label>
                    <input type="email" id="login-email" placeholder="example@gmail.com" class="w-full bg-slate-900 border border-slate-700 focus:border-amber-400 rounded-xl p-3 text-white outline-none font-mono-num">
                </div>

                <div class="bg-slate-950/90 p-3.5 rounded-xl border border-slate-800 space-y-2 text-[11px] text-slate-300 leading-relaxed">
                    <div class="font-bold text-amber-400 flex items-center gap-1.5">
                        <i class="fa-solid fa-scale-balanced"></i> ข้อตกลงการใช้งานเครื่องมือทางคณิตศาสตร์ (Disclaimer)
                    </div>
                    <p>
                        เว็บแอปพลิเคชันนี้เป็นเพียง <strong>เครื่องมือช่วยคำนวณตัวเลขทางคณิตศาสตร์ (Fibonacci Retracement) และแสดงข้อมูลทางสถิติอัตโนมัติเท่านั้น</strong> มิใช่การให้คำแนะนำทางการเงินหรือการชักชวนลงทุน (Not Financial Advice) ผู้ใช้งานเป็นผู้ตัดสินใจและรับความเสี่ยงด้วยตนเอง 100%
                    </p>
                    <label class="flex items-start gap-2 pt-1 cursor-pointer select-none text-white font-semibold">
                        <input type="checkbox" id="login-disclaimer" class="mt-0.5 rounded accent-amber-500 w-4 h-4">
                        <span>ฉันอ่านและยอมรับว่านี่คือเครื่องมือคำนวณทางสถิติเท่านั้น</span>
                    </label>
                </div>
            </div>

            <button onclick="submitEmailLogin()" class="btn-interactive w-full py-3 rounded-xl bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 font-black text-sm shadow-lg">
                เข้าสู่ระบบและใช้งานเครื่องมือ
            </button>
        </div>
    </div>

    <!-- ==================================================================== -->
    <!-- MODAL 2: ตั้งค่าเชื่อมต่อ TELEGRAM BOT & เวลาแจ้งเตือนส่วนตัว          -->
    <!-- ==================================================================== -->
    <div id="settings-modal" class="fixed inset-0 bg-slate-950/85 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="pro-card rounded-2xl max-w-lg w-full p-6 space-y-4 border border-cyan-500/40 max-h-[92vh] overflow-y-auto">
            <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                <div class="flex items-center gap-2.5">
                    <i class="fa-brands fa-telegram text-2xl text-cyan-400"></i>
                    <div>
                        <h3 class="text-base font-black text-white">ตั้งค่าแจ้งเตือน Telegram Bot 24 ชม.</h3>
                        <p class="text-[11px] text-slate-400">ส่งตรงเข้ามือถือโดยไม่ต้องเปิดหน้าเว็บค้างไว้</p>
                    </div>
                </div>
                <button onclick="toggleSettingsModal()" class="text-slate-400 hover:text-white text-lg px-2">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>

            <!-- ขั้นตอนที่ 1: กด /start บอท -->
            <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2.5 text-xs">
                <div class="font-bold text-cyan-300">STEP 1: กดปุ่ม Start ในแอป Telegram ก่อน</div>
                <p class="text-slate-400 text-[11px]">คลิกลิงก์ด้านล่างเพื่อเปิดบอท <strong>@gold_ai_sniper_pro_bot</strong> แล้วกดปุ่ม <strong>Start (/start)</strong> 1 ครั้ง</p>
                <div class="flex flex-wrap gap-2 pt-1">
                    <a href="https://t.me/gold_ai_sniper_pro_bot" target="_blank" class="btn-interactive px-3.5 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-extrabold inline-flex items-center gap-1.5">
                        <i class="fa-brands fa-telegram text-sm"></i> 1. เปิดบอท @gold_ai_sniper_pro_bot
                    </a>
                    <button onclick="autoDetectTelegramChatId()" class="btn-interactive px-3.5 py-2 rounded-xl bg-amber-500/20 border border-amber-500/50 text-amber-300 font-bold inline-flex items-center gap-1.5">
                        <i class="fa-solid fa-wand-magic-sparkles"></i> 2. ดึงเลข Chat ID อัตโนมัติ
                    </button>
                </div>
            </div>

            <!-- ขั้นตอนที่ 2: กรอก Chat ID และเลือก Timeframe -->
            <div class="space-y-3 text-xs">
                <div>
                    <label class="text-slate-300 font-bold block mb-1">Telegram Chat ID ของคุณ</label>
                    <div class="flex gap-2">
                        <input type="text" id="set-chat-id" placeholder="เช่น 123456789 (กดปุ่มดึงอัตโนมัติด้านบนได้)" class="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white font-mono-num">
                        <button onclick="sendTestTelegram()" class="btn-interactive px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-500/30 font-bold shrink-0">
                            ทดสอบส่ง
                        </button>
                    </div>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">Timeframe ที่เฝ้าสแกน</label>
                        <select id="set-tf" class="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white font-bold">
                            <option value="1m">1 นาที (M1)</option>
                            <option value="5m" selected>5 นาที (M5 - แนะนำ)</option>
                            <option value="15m">15 นาที (M15)</option>
                            <option value="1h">1 ชั่วโมง (H1)</option>
                            <option value="4h">4 ชั่วโมง (H4)</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">เวลาเริ่มแจ้งเตือน</label>
                        <input type="time" id="set-start-time" value="08:00" class="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white font-mono-num">
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">เวลาหยุดแจ้งเตือน</label>
                        <input type="time" id="set-end-time" value="23:59" class="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white font-mono-num">
                    </div>
                </div>

                <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                    <div class="font-bold text-amber-400 text-[11px]">เงื่อนไขจุดแจ้งเตือนอัตโนมัติ (เลือกได้ทั้งคู่)</div>
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" id="set-alert-05" checked class="accent-amber-500 w-4 h-4">
                        <span>🔔 <strong>เตือนล่วงหน้าเมื่อแตะระดับ 0.5 (Fib 50.0%)</strong> เพื่อเตรียมตัว</span>
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" id="set-alert-618" checked class="accent-cyan-500 w-4 h-4">
                        <span>🎯 <strong>เตือนเมื่อราคาเข้า Golden Zone 61.8%</strong> พร้อมกรอบ SL/TP</span>
                    </label>
                </div>
            </div>

            <div class="flex justify-end gap-2 pt-2">
                <button onclick="toggleSettingsModal()" class="px-4 py-2.5 rounded-xl bg-slate-800 text-slate-300 text-xs font-bold">ปิด</button>
                <button onclick="saveUserSettings()" class="btn-interactive px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-400 to-emerald-400 text-slate-950 font-black text-xs">
                    <i class="fa-solid fa-floppy-disk mr-1"></i> บันทึกการตั้งค่าทั้งหมด
                </button>
            </div>
        </div>
    </div>

    <div class="max-w-[1680px] mx-auto space-y-4">

        <!-- ================================================================ -->
        <!-- 1. CLEAN TOP HEADER BAR                                          -->
        <!-- ================================================================ -->
        <header class="pro-card rounded-2xl p-4 lg:px-6 flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
            <div class="flex items-center gap-3.5">
                <div class="px-3.5 py-2 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 flex flex-col items-center justify-center shadow-lg font-black text-slate-950">
                    <span class="text-[9px] tracking-tighter leading-none">SNIPER</span>
                    <span class="text-base tracking-tight leading-none font-mono-num">XAU</span>
                </div>
                <div>
                    <div class="flex flex-wrap items-center gap-2">
                        <h1 class="text-lg md:text-xl font-black tracking-tight text-white">GOLD AI SNIPER PRO</h1>
                        <span class="px-2 py-0.5 text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-full">
                            AUTO FIB 0.5 & 61.8%
                        </span>
                    </div>
                    <p class="text-[11px] text-slate-400">เครื่องมือคำนวณกรอบราคาทางเทคนิคอัตโนมัติ & แจ้งเตือนผ่าน Telegram</p>
                </div>
            </div>

            <div class="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-between lg:justify-end">
                <!-- ราคาทองคำสด -->
                <div class="bg-slate-950 px-3.5 py-1.5 rounded-xl border border-slate-800 flex items-center gap-2.5">
                    <div>
                        <span class="block text-[9px] text-slate-400 font-bold uppercase">XAUUSD LIVE</span>
                        <span id="live-ticker-price" class="font-mono-num text-sm font-black text-emerald-400">--</span>
                    </div>
                    <span id="proximity-pill" class="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-300">รอคำนวณ...</span>
                </div>

                <!-- ป้องกันข่าวแรง -->
                <div id="news-shield-box" class="bg-emerald-950/40 border border-emerald-500/40 px-3 py-1.5 rounded-xl flex items-center gap-2">
                    <span id="shield-dot" class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    <span id="shield-status-text" class="text-[11px] font-bold text-emerald-400">ตลาดปกติ</span>
                    <button onclick="toggleNewsLock()" class="text-[10px] bg-slate-900 hover:bg-slate-800 px-2 py-0.5 rounded border border-slate-700 text-slate-300">สลับโหมด</button>
                </div>

                <!-- ปุ่มตั้งค่า Telegram & บัญชีผู้ใช้ -->
                <button onclick="toggleSettingsModal()" class="btn-interactive px-3.5 py-2 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/40 text-cyan-300 text-xs font-extrabold flex items-center gap-1.5">
                    <i class="fa-brands fa-telegram text-sm"></i>
                    <span id="telegram-status-btn">ตั้งค่า Telegram</span>
                </button>

                <button onclick="openAuthModal()" class="btn-interactive px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs font-bold text-amber-300 flex items-center gap-1.5">
                    <i class="fa-regular fa-user"></i>
                    <span id="user-email-badge">เข้าสู่ระบบ</span>
                </button>
            </div>
        </header>

        <!-- ================================================================ -->
        <!-- 2. MAIN WORKSPACE GRID (12 COLUMNS - CLEAN & ORGANIZED)          -->
        <!-- ================================================================ -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">

            <!-- LEFT COLUMN (7 COLS): TRADINGVIEW CHART + ECONOMIC CALENDAR -->
            <div class="xl:col-span-7 space-y-4">

                <!-- 2.1 กราฟ TradingView -->
                <div class="pro-card rounded-2xl p-4 space-y-3">
                    <div class="flex flex-wrap justify-between items-center gap-2">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-bold text-white"><i class="fa-solid fa-chart-line text-amber-400 mr-1.5"></i>กราฟราคาทองคำ (OANDA:XAUUSD)</span>
                            <span id="chart-tf-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">TF 5M</span>
                        </div>
                        <button onclick="triggerAutoFibonacciCalculation(true)" class="btn-interactive py-1.5 px-3.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black flex items-center gap-1.5">
                            <i id="fib-spin-icon" class="fa-solid fa-rotate"></i> คำนวณกรอบราคาใหม่
                        </button>
                    </div>

                    <div class="tradingview-widget-container rounded-xl overflow-hidden border border-slate-800" style="height:500px; width:100%;">
                        <div id="tradingview_advanced_chart" style="height:100%; width:100%;"></div>
                    </div>
                </div>

                <!-- 2.2 ตารางข่าว Forex Factory -->
                <div class="pro-card rounded-2xl p-4 space-y-3">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-2.5">
                        <div>
                            <h2 class="text-sm font-bold text-white"><i class="fa-regular fa-calendar-days text-rose-400 mr-1.5"></i>ปฏิทินข่าวเศรษฐกิจ Forex Factory (เวลาไทย)</h2>
                            <p class="text-[11px] text-slate-400">ระบบงดส่งแจ้งเตือนอัตโนมัติในช่วงข่าวแดง ±30 นาที</p>
                        </div>
                        <div class="flex gap-1.5">
                            <button onclick="filterNews('ALL')" id="news-filter-ALL" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-amber-500 text-slate-950">ทั้งหมด</button>
                            <button onclick="filterNews('TODAY')" id="news-filter-TODAY" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-900 text-slate-300 border border-slate-800">วันนี้</button>
                            <button onclick="filterNews('HIGH')" id="news-filter-HIGH" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-900 text-rose-400 border border-slate-800">🔴 ข่าวแดง</button>
                        </div>
                    </div>

                    <div class="overflow-x-auto max-h-[260px]">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-slate-800 text-[10px] uppercase">
                                    <th class="py-2 px-2">วัน / เวลา</th>
                                    <th class="py-2 px-2">ข่าวเศรษฐกิจ (USD)</th>
                                    <th class="py-2 px-2">ระดับ</th>
                                    <th class="py-2 px-2">สถานะเวลา</th>
                                </tr>
                            </thead>
                            <tbody id="economic-calendar-body" class="divide-y divide-slate-800/50"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- RIGHT COLUMN (5 COLS): TIMEFRAME + FIB LEVELS (0.5 & 61.8%) + TELEGRAM -->
            <div class="xl:col-span-5 space-y-4">

                <!-- 1. เลือก Timeframe (โฟกัส M5 เป็นค่าเริ่มต้น) -->
                <div class="pro-card rounded-2xl p-4 space-y-3">
                    <div class="flex justify-between items-center">
                        <span class="text-xs font-bold text-white">1. เลือก Timeframe ที่ใช้คำนวณ</span>
                        <span id="active-tf-badge" class="px-2.5 py-0.5 rounded-lg text-[11px] font-mono-num font-black bg-amber-500 text-slate-950">TF: 5M</span>
                    </div>
                    <div class="grid grid-cols-6 gap-1.5">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num border">1M</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num border">5M</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num border">15M</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num border">1H</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num border">4H</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num border">1D</button>
                    </div>
                </div>

                <!-- 2. กรอบราคา Fibonacci อัตโนมัติ (มีระดับ 0.5 เตือนล่วงหน้า + 61.8% Golden Zone) -->
                <div class="pro-card pro-card-gold rounded-2xl p-4 space-y-3.5">
                    <div id="right-card-direction-banner" class="p-3.5 rounded-xl border text-center space-y-0.5">
                        <div class="text-[10px] font-bold uppercase tracking-wider opacity-85">โครงสร้างกรอบราคาทางเทคนิคปัจจุบัน</div>
                        <div id="setup-order-badge" class="text-xl md:text-2xl font-black font-mono-num">--</div>
                        <div id="setup-order-subtext" class="text-[11px] opacity-90">--</div>
                    </div>

                    <!-- แถบแจ้งเตือนล่วงหน้า 0.5 (50.0%) -->
                    <div onclick="copyPrice('val-fib05')" class="price-box cursor-pointer bg-amber-500/10 border border-amber-500/50 p-3 rounded-xl flex justify-between items-center">
                        <div>
                            <span class="text-[10px] font-extrabold text-amber-300 uppercase block">
                                🔔 จุดแจ้งเตือนล่วงหน้า (FIBONACCI 0.5 / 50.0%)
                            </span>
                            <span class="text-[11px] text-slate-300">เมื่อราคาแตะจุดนี้ ระบบจะส่งเตือนให้เตรียมตัวก่อนถึงโซน 61.8%</span>
                        </div>
                        <div class="text-right shrink-0 ml-2">
                            <span id="val-fib05" class="font-mono-num text-xl font-black text-amber-400 block">--</span>
                            <span class="text-[9px] bg-amber-500/20 text-amber-200 px-1.5 py-0.5 rounded">คลิกคัดลอก</span>
                        </div>
                    </div>

                    <!-- กรอบราคาหลัก 4 จุด (คลิกคัดลอกได้ทันที) -->
                    <div class="grid grid-cols-2 gap-2.5">
                        <div onclick="copyPrice('val-entry')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-cyan-500/50">
                            <div class="flex justify-between items-center">
                                <span id="card-entry-title" class="text-[11px] font-extrabold text-cyan-300">🔵 GOLDEN ZONE (61.8%)</span>
                                <span class="text-[9px] text-cyan-400">คัดลอก</span>
                            </div>
                            <div id="val-entry" class="text-xl font-black font-mono-num text-cyan-400 mt-1">--</div>
                        </div>

                        <div onclick="copyPrice('val-sl')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-rose-500/50">
                            <div class="flex justify-between items-center">
                                <span class="text-[11px] font-extrabold text-rose-300">🔴 ระยะความเสี่ยง (78.6%)</span>
                                <span id="val-risk-pts" class="text-[9px] font-mono-num text-rose-300">--</span>
                            </div>
                            <div id="val-sl" class="text-xl font-black font-mono-num text-rose-400 mt-1">--</div>
                        </div>

                        <div onclick="copyPrice('val-tp1')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-emerald-500/40">
                            <div class="flex justify-between items-center">
                                <span class="text-[11px] font-extrabold text-emerald-300">🟢 เป้าสถิติ TP1 (1:2)</span>
                                <span id="val-tp1-pts" class="text-[9px] font-mono-num text-emerald-300">--</span>
                            </div>
                            <div id="val-tp1" class="text-xl font-black font-mono-num text-emerald-400 mt-1">--</div>
                        </div>

                        <div onclick="copyPrice('val-tp2')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-amber-500/40">
                            <div class="flex justify-between items-center">
                                <span class="text-[11px] font-extrabold text-amber-300">🟡 เป้าสถิติ TP2 (1:3)</span>
                                <span id="val-tp2-pts" class="text-[9px] font-mono-num text-amber-300">--</span>
                            </div>
                            <div id="val-tp2" class="text-xl font-black font-mono-num text-amber-400 mt-1">--</div>
                        </div>
                    </div>

                    <!-- กรอบ Swing High / Low & คำนวณ Lot -->
                    <div class="bg-slate-950/90 p-3 rounded-xl border border-slate-800 flex flex-wrap justify-between items-center gap-2 text-xs">
                        <div class="flex gap-3 font-mono-num">
                            <span>⬆️ High: <strong id="display-swing-high" class="text-white">--</strong></span>
                            <span>⬇️ Low: <strong id="display-swing-low" class="text-white">--</strong></span>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-[11px] text-slate-400">ทุน($):</span>
                            <input type="number" id="acc-balance" value="1000" oninput="recalcLotSize()" class="w-16 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-white font-mono-num text-xs">
                            <span id="calc-lot-result" class="text-[11px] font-mono-num font-bold text-cyan-300">0.05 Lot</span>
                        </div>
                    </div>

                    <!-- ปุ่มยิงเข้า Telegram ทันที -->
                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="btn-interactive w-full py-3 px-4 rounded-xl font-black text-xs md:text-sm bg-gradient-to-r from-cyan-400 via-teal-400 to-emerald-400 text-slate-950 shadow-lg flex items-center justify-center gap-2">
                        <i class="fa-brands fa-telegram text-base"></i>
                        <span>ส่งระดับราคาชุดนี้เข้า Telegram ทันที</span>
                    </button>
                </div>

                <!-- 3. ปรับกรอบ Swing High / Low เอง (ซ่อนพับได้ให้หน้าเว็บคลีน) -->
                <details class="pro-card rounded-2xl p-3.5 text-xs">
                    <summary class="font-bold text-amber-400 cursor-pointer select-none flex justify-between items-center">
                        <span><i class="fa-solid fa-sliders mr-1.5"></i>ปรับกรอบ Swing High / Low ด้วยตัวเอง</span>
                        <span class="text-[10px] text-slate-400">คลิกเพื่อเปิด/ปิด</span>
                    </summary>
                    <div class="grid grid-cols-3 gap-2 pt-3">
                        <select id="custom-dir" class="bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-bold">
                            <option value="SELL">🔴 ฝั่ง SELL</option>
                            <option value="BUY">🟢 ฝั่ง BUY</option>
                        </select>
                        <input type="number" id="custom-high" step="0.1" placeholder="Swing High" class="bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                        <input type="number" id="custom-low" step="0.1" placeholder="Swing Low" class="bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                    </div>
                    <button onclick="applyCustomSwing()" class="mt-2 w-full py-2 rounded-lg bg-slate-800 hover:bg-amber-500 hover:text-slate-950 text-amber-300 font-bold">
                        คำนวณจากกรอบที่กำหนดเอง
                    </button>
                </details>

                <!-- 4. ประวัติการแจ้งเตือน & ตารางสรุปทุก Timeframe -->
                <div class="pro-card rounded-2xl p-4 space-y-3">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-2">
                        <div class="flex gap-1.5">
                            <button onclick="switchRightTab('feed')" id="tab-btn-feed" class="px-2.5 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950">ประวัติแจ้งเตือนล่าสุด</button>
                            <button onclick="switchRightTab('matrix')" id="tab-btn-matrix" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800">สรุปทุก Timeframe</button>
                        </div>
                        <span class="text-[10px] text-slate-400 font-mono-num" id="feed-counter-label">--</span>
                    </div>
                    <div id="right-tab-feed" class="space-y-2 max-h-[210px] overflow-y-auto pr-1"></div>
                    <div id="right-tab-matrix" class="hidden space-y-1.5 max-h-[210px] overflow-y-auto pr-1">
                        <div id="matrix-overview-list" class="space-y-1.5 text-xs"></div>
                    </div>
                </div>

            </div>
        </div>

        <!-- FOOTER DISCLAIMER -->
        <footer class="text-center text-[11px] text-slate-500 py-2">
            ข้อมูลทั้งหมดเกิดจากการคำนวณสูตรคณิตศาสตร์ Fibonacci อัตโนมัติเพื่อประกอบการวิเคราะห์ทางเทคนิคเท่านั้น ไม่ใช่คำแนะนำในการลงทุน
        </footer>
    </div>

    <!-- Toast Notification -->
    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-emerald-400 text-slate-950 px-4 py-3 rounded-xl font-extrabold text-xs shadow-2xl z-50 flex items-center gap-2">
        <i class="fa-solid fa-bell"></i>
        <span id="toast-notify-text">ดำเนินการสำเร็จ!</span>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        const timeframeMeta = {
            '1m':    { label: '1 นาที (1M)',    tvInterval: '1',   lookback: 90 },
            '5m':    { label: '5 นาที (5M)',    tvInterval: '5',   lookback: 96 },
            '15m':   { label: '15 นาที (15M)',  tvInterval: '15',  lookback: 96 },
            '1h':    { label: '1 ชั่วโมง (1H)', tvInterval: '60',  lookback: 100 },
            '4h':    { label: '4 ชั่วโมง (4H)', tvInterval: '240', lookback: 100 },
            'daily': { label: 'รายวัน (1D)',    tvInterval: 'D',   lookback: 90 }
        };

        const liveTimeframeStore = {};
        let currentTfKey = '5m'; // โฟกัส M5 เป็นค่าเริ่มต้นตามกลยุทธ์หลัก
        let currentTvLoadedInterval = null;
        let isNewsLocked = false;
        let currentRiskDollar = 5.0;
        let allCalendarEvents = [];
        let currentNewsFilter = 'ALL';
        let localAlertMemory = {};

        // ====================================================================
        // 1. ระบบคำนวณ FIBONACCI (0.5 + 61.8% + 78.6%)
        // ====================================================================
        function calculateSniperMath(direction, swingHigh, swingLow) {
            const range = Math.max(0.5, swingHigh - swingLow);
            let fib05, entry, sl, risk, tp1, tp2;

            if (direction === 'SELL') {
                fib05 = swingLow + (range * 0.500);
                entry = swingLow + (range * 0.618);
                sl    = swingLow + (range * 0.786);
                risk  = Math.abs(sl - entry);
                tp1   = entry - (risk * 2);
                tp2   = entry - (risk * 3);
            } else {
                fib05 = swingHigh - (range * 0.500);
                entry = swingHigh - (range * 0.618);
                sl    = swingHigh - (range * 0.786);
                risk  = Math.abs(entry - sl);
                tp1   = entry + (risk * 2);
                tp2   = entry + (risk * 3);
            }

            return {
                fib05Num: fib05, entryNum: entry, slNum: sl, tp1Num: tp1, tp2Num: tp2,
                fib05: fib05.toFixed(2),
                entry: entry.toFixed(2),
                sl: sl.toFixed(2),
                tp1: tp1.toFixed(2),
                tp2: tp2.toFixed(2),
                riskNum: risk,
                riskDollar: risk.toFixed(2),
                reward1Dollar: (risk * 2).toFixed(2),
                reward2Dollar: (risk * 3).toFixed(2)
            };
        }

        // เสียงแจ้งเตือนเบาๆ บนเว็บเมื่อแตะ 0.5 หรือ 61.8%
        function playBeepSound() {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(880, ctx.currentTime);
                gain.gain.setValueAtTime(0.08, ctx.currentTime);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.18);
            } catch (e) {}
        }

        async function fetchRealGoldCandles(tfKey) {
            const meta = timeframeMeta[tfKey];
            const binanceTf = tfKey === 'daily' ? '1d' : tfKey;
            const url = `https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=${binanceTf}&limit=300`;
            const res = await fetch(url);
            const raw = await res.json();

            const candles = raw.map(k => ({
                time: Math.floor(k[0] / 1000),
                high: parseFloat(parseFloat(k[2]).toFixed(2)),
                low: parseFloat(parseFloat(k[3]).toFixed(2)),
                close: parseFloat(parseFloat(k[4]).toFixed(2))
            }));

            const recentSlice = candles.slice(-meta.lookback);
            let swingHigh = -Infinity, swingLow = Infinity;
            let highIdx = 0, lowIdx = 0;

            recentSlice.forEach((c, idx) => {
                if (c.high > swingHigh) { swingHigh = c.high; highIdx = idx; }
                if (c.low < swingLow) { swingLow = c.low; lowIdx = idx; }
            });

            const currentPrice = candles[candles.length - 1].close;
            const calcDir = (highIdx < lowIdx) ? 'SELL' : 'BUY';

            liveTimeframeStore[tfKey] = {
                swingHigh, swingLow, currentPrice, calcDir
            };
            return liveTimeframeStore[tfKey];
        }

        function checkProximityAndAlert(tfKey, state, mathRes) {
            const pill = document.getElementById('proximity-pill');
            const price = state.currentPrice;
            const rng = Math.max(1.0, state.swingHigh - state.swingLow);
            const tol = Math.max(0.45, rng * 0.035);
            const key = `${tfKey}_${state.swingHigh}_${state.swingLow}`;

            if (Math.abs(price - mathRes.entryNum) <= tol) {
                pill.className = "px-2 py-0.5 text-[10px] font-extrabold rounded bg-cyan-500 text-slate-950 animate-pulse";
                pill.innerText = "🎯 ราคาอยู่ในโซน 61.8%!";
                if (localAlertMemory[key] !== '618') {
                    localAlertMemory[key] = '618';
                    playBeepSound();
                    showToast(`🎯 [${tfKey.toUpperCase()}] ราคาแตะ Golden Zone 61.8% ($${mathRes.entry})`);
                }
            } else if (Math.abs(price - mathRes.fib05Num) <= tol) {
                pill.className = "px-2 py-0.5 text-[10px] font-extrabold rounded bg-amber-400 text-slate-950 animate-pulse";
                pill.innerText = "🔔 แตะระดับ 0.5 (เตรียมตัว!)";
                if (!localAlertMemory[key]) {
                    localAlertMemory[key] = '05';
                    playBeepSound();
                    showToast(`🔔 [${tfKey.toUpperCase()}] แจ้งเตือนล่วงหน้า! ราคาแตะระดับ 0.5 ($${mathRes.fib05})`);
                }
            } else {
                pill.className = "px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-300";
                pill.innerText = `รอแตะ 0.5 ($${mathRes.fib05})`;
            }
        }

        function applyStateToUI(tfKey, state) {
            const mathRes = calculateSniperMath(state.calcDir, state.swingHigh, state.swingLow);
            currentRiskDollar = mathRes.riskNum;

            document.getElementById('live-ticker-price').innerText = '$' + state.currentPrice.toFixed(2);
            document.getElementById('chart-tf-pill').innerText = 'TF ' + tfKey.toUpperCase();
            document.getElementById('display-swing-high').innerText = '$' + state.swingHigh.toFixed(2);
            document.getElementById('display-swing-low').innerText = '$' + state.swingLow.toFixed(2);

            document.getElementById('val-fib05').innerText = '$' + mathRes.fib05;
            document.getElementById('val-entry').innerText = '$' + mathRes.entry;
            document.getElementById('val-sl').innerText = '$' + mathRes.sl;
            document.getElementById('val-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('val-tp2').innerText = '$' + mathRes.tp2;

            document.getElementById('val-risk-pts').innerText = `-$${mathRes.riskDollar}`;
            document.getElementById('val-tp1-pts').innerText = `+$${mathRes.reward1Dollar}`;
            document.getElementById('val-tp2-pts').innerText = `+$${mathRes.reward2Dollar}`;

            document.getElementById('custom-dir').value = state.calcDir;
            document.getElementById('custom-high').value = state.swingHigh.toFixed(2);
            document.getElementById('custom-low').value = state.swingLow.toFixed(2);

            const rightBanner = document.getElementById('right-card-direction-banner');
            const rightBadge = document.getElementById('setup-order-badge');
            const rightSub = document.getElementById('setup-order-subtext');

            if (state.calcDir === 'SELL') {
                rightBanner.className = "p-3.5 rounded-xl border border-rose-500/70 bg-rose-950/40 text-center space-y-0.5";
                rightBadge.className = "text-xl md:text-2xl font-black font-mono-num text-rose-400";
                rightBadge.innerText = `🔴 โครงสร้างฝั่ง SELL (${tfKey.toUpperCase()})`;
                rightSub.innerText = `เตือนล่วงหน้า 0.5: $${mathRes.fib05} • โซน 61.8%: $${mathRes.entry}`;
            } else {
                rightBanner.className = "p-3.5 rounded-xl border border-emerald-500/70 bg-emerald-950/40 text-center space-y-0.5";
                rightBadge.className = "text-xl md:text-2xl font-black font-mono-num text-emerald-400";
                rightBadge.innerText = `🟢 โครงสร้างฝั่ง BUY (${tfKey.toUpperCase()})`;
                rightSub.innerText = `เตือนล่วงหน้า 0.5: $${mathRes.fib05} • โซน 61.8%: $${mathRes.entry}`;
            }

            checkProximityAndAlert(tfKey, state, mathRes);
            recalcLotSize();
            renderMatrixTable(tfKey);
        }

        function recalcLotSize() {
            const balance = parseFloat(document.getElementById('acc-balance').value) || 1000;
            const riskMoney = balance * 0.015; // ค่ามาตรฐาน 1.5%
            const lossPerOneLot = Math.max(0.5, currentRiskDollar) * 100;
            const finalLot = Math.max(0.01, riskMoney / lossPerOneLot).toFixed(2);
            document.getElementById('calc-lot-result').innerText = `${finalLot} Lot`;
        }

        async function triggerAutoFibonacciCalculation(showNotification = true) {
            const icon = document.getElementById('fib-spin-icon');
            if (icon) icon.className = "fa-solid fa-spinner fa-spin";
            try {
                const state = await fetchRealGoldCandles(currentTfKey);
                applyStateToUI(currentTfKey, state);
                if (showNotification) showToast(`⚡ อัปเดตกรอบราคา ${currentTfKey.toUpperCase()} เรียบร้อย`);
            } catch (e) {
                console.error(e);
            } finally {
                if (icon) icon.className = "fa-solid fa-rotate";
            }
        }

        async function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const meta = timeframeMeta[tfKey];
            if (!meta) return;

            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num bg-slate-950 text-slate-400 border border-slate-800";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn btn-interactive py-2 rounded-xl text-xs font-black font-mono-num bg-amber-500 text-slate-950 border border-amber-300 shadow";
            }

            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            loadTradingViewStudio(meta.tvInterval);
            await triggerAutoFibonacciCalculation(false);
        }

        function applyCustomSwing() {
            const dir = document.getElementById('custom-dir').value;
            const high = parseFloat(document.getElementById('custom-high').value);
            const low = parseFloat(document.getElementById('custom-low').value);
            if (!high || !low || high <= low) {
                showToast('⚠️ กรุณาระบุ Swing High ให้มากกว่า Swing Low');
                return;
            }
            const curPrice = liveTimeframeStore[currentTfKey]?.currentPrice || high;
            liveTimeframeStore[currentTfKey] = { swingHigh: high, swingLow: low, currentPrice: curPrice, calcDir: dir };
            applyStateToUI(currentTfKey, liveTimeframeStore[currentTfKey]);
            showToast('✅ คำนวณกรอบราคาจากค่าที่กำหนดเองเรียบร้อย');
        }

        function loadTradingViewStudio(intervalCode) {
            if (currentTvLoadedInterval === intervalCode) return;
            currentTvLoadedInterval = intervalCode;
            const container = document.getElementById('tradingview_advanced_chart');
            container.innerHTML = '';
            new TradingView.widget({
                "width": "100%",
                "height": "500",
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
                "container_id": "tradingview_advanced_chart"
            });
        }

        // ====================================================================
        // 2. ระบบ EMAIL LOGIN + เชื่อมต่อ TELEGRAM BOT
        // ====================================================================
        function checkAuthStatus() {
            const savedEmail = localStorage.getItem('gold_sniper_email');
            const savedChatId = localStorage.getItem('gold_sniper_chat_id');
            if (!savedEmail) {
                document.getElementById('auth-modal').classList.remove('hidden');
            } else {
                document.getElementById('user-email-badge').innerText = savedEmail.split('@')[0];
                document.getElementById('login-email').value = savedEmail;
            }
            if (savedChatId) {
                document.getElementById('set-chat-id').value = savedChatId;
                document.getElementById('telegram-status-btn').innerText = 'เชื่อม Telegram แล้ว';
            }
        }

        function openAuthModal() {
            document.getElementById('auth-modal').classList.remove('hidden');
        }

        async function submitEmailLogin() {
            const email = document.getElementById('login-email').value.trim();
            const accepted = document.getElementById('login-disclaimer').checked;
            if (!email || !email.includes('@')) {
                showToast('⚠️ กรุณากรอกอีเมลให้ถูกต้อง');
                return;
            }
            if (!accepted) {
                showToast('⚠️ กรุณาติ๊กยอมรับข้อตกลงการใช้งานเครื่องมือทางสถิติ');
                return;
            }

            localStorage.setItem('gold_sniper_email', email);
            document.getElementById('user-email-badge').innerText = email.split('@')[0];
            document.getElementById('auth-modal').classList.add('hidden');

            await fetch('/api/user-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    chat_id: localStorage.getItem('gold_sniper_chat_id') || '',
                    preferred_tf: currentTfKey
                })
            });
            showToast('✅ ยินดีต้อนรับเข้าสู่ GOLD AI SNIPER PRO');
        }

        function toggleSettingsModal() {
            document.getElementById('settings-modal').classList.toggle('hidden');
        }

        async function autoDetectTelegramChatId() {
            showToast('🔍 กำลังค้นหา Chat ID ล่าสุดที่กด /start...');
            try {
                const res = await fetch('/api/telegram-detect-chat');
                const data = await res.json();
                if (data.status === 'ok' && data.chat_id) {
                    document.getElementById('set-chat-id').value = data.chat_id;
                    localStorage.setItem('gold_sniper_chat_id', data.chat_id);
                    showToast(`✅ พบ Chat ID: ${data.chat_id} (${data.name})`);
                } else {
                    showToast('⚠️ ยังไม่พบข้อมูล กรุณาเปิดบอทแล้วกด /start อีกครั้ง');
                }
            } catch (e) {
                showToast('⚠️ ไม่สามารถดึงข้อมูลได้');
            }
        }

        async function saveUserSettings() {
            const email = localStorage.getItem('gold_sniper_email') || 'trader@gold.ai';
            const chatId = document.getElementById('set-chat-id').value.trim();
            const tf = document.getElementById('set-tf').value;
            const startT = document.getElementById('set-start-time').value;
            const endT = document.getElementById('set-end-time').value;
            const alert05 = document.getElementById('set-alert-05').checked;
            const alert618 = document.getElementById('set-alert-618').checked;

            localStorage.setItem('gold_sniper_chat_id', chatId);
            if (chatId) {
                document.getElementById('telegram-status-btn').innerText = 'เชื่อม Telegram แล้ว';
            }

            await fetch('/api/user-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    chat_id: chatId,
                    preferred_tf: tf,
                    start_time: startT,
                    end_time: endT,
                    alert_05: alert05,
                    alert_618: alert618
                })
            });

            selectTimeframe(tf);
            toggleSettingsModal();
            showToast('✅ บันทึกการตั้งค่าและเปิดสแกนหลังบ้าน 24 ชม. เรียบร้อย!');
        }

        async function sendTestTelegram() {
            const chatId = document.getElementById('set-chat-id').value.trim();
            if (!chatId) {
                showToast('⚠️ กรุณาใส่เลข Chat ID หรือกดปุ่มดึงอัตโนมัติก่อนครับ');
                return;
            }
            const res = await fetch('/api/test-telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId })
            });
            const data = await res.json();
            if (res.ok && data.status === 'ok') {
                showToast('🚀 ส่งข้อความทดสอบเข้า Telegram มือถือเรียบร้อย!');
            } else {
                showToast('⚠️ ส่งไม่สำเร็จ กรุณาเช็กว่ากด /start ในบอทหรือยัง');
            }
        }

        async function broadcastCurrentSignal() {
            if (isNewsLocked) {
                showToast('🛑 ระบบงดส่งแจ้งเตือนชั่วคราวเนื่องจากอยู่ในช่วงข่าวแดง');
                return;
            }
            const chatId = document.getElementById('set-chat-id').value.trim() || localStorage.getItem('gold_sniper_chat_id') || '';
            if (!chatId) {
                toggleSettingsModal();
                showToast('⚠️ กรุณาเชื่อมต่อ Telegram Chat ID ก่อนส่งแจ้งเตือนครับ');
                return;
            }

            const payload = {
                chat_id: chatId,
                symbol: 'XAUUSD',
                tf: currentTfKey.toUpperCase(),
                direction: document.getElementById('custom-dir').value,
                fib_05: document.getElementById('val-fib05').innerText.replace('$', ''),
                entry: document.getElementById('val-entry').innerText.replace('$', ''),
                sl: document.getElementById('val-sl').innerText.replace('$', ''),
                tp1: document.getElementById('val-tp1').innerText.replace('$', ''),
                tp2: document.getElementById('val-tp2').innerText.replace('$', '')
            };

            const res = await fetch('/api/send-signal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                const data = await res.json();
                renderSignalFeed(data.signal_history);
                showToast('🚀 ส่งระดับราคาเข้า Telegram เรียบร้อย!');
            } else {
                const err = await res.json();
                showToast('⚠️ ' + (err.message || 'ส่งไม่สำเร็จ'));
            }
        }

        // ====================================================================
        // 3. ตารางสรุป & ปฏิทินข่าว
        // ====================================================================
        function switchRightTab(tab) {
            document.getElementById('right-tab-feed').classList.toggle('hidden', tab !== 'feed');
            document.getElementById('right-tab-matrix').classList.toggle('hidden', tab !== 'matrix');
            document.getElementById('tab-btn-feed').className = tab === 'feed'
                ? "px-2.5 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950"
                : "px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800";
            document.getElementById('tab-btn-matrix').className = tab === 'matrix'
                ? "px-2.5 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950"
                : "px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800";
        }

        function renderMatrixTable(activeKey) {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';
            Object.keys(timeframeMeta).forEach(key => {
                const st = liveTimeframeStore[key];
                if (!st) return;
                const lvls = calculateSniperMath(st.calcDir, st.swingHigh, st.swingLow);
                const row = document.createElement('div');
                row.className = `flex items-center justify-between p-2.5 rounded-xl border cursor-pointer ${
                    key === activeKey ? 'bg-amber-500/15 border-amber-500/50' : 'bg-slate-950 border-slate-800'
                }`;
                row.onclick = () => selectTimeframe(key);
                row.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="font-black font-mono-num text-amber-400 w-10 uppercase">${key}</span>
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${st.calcDir === 'SELL' ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'}">${st.calcDir}</span>
                    </div>
                    <div class="flex gap-2.5 text-[11px] font-mono-num">
                        <span class="text-amber-300">0.5: $${lvls.fib05}</span>
                        <span class="text-cyan-400 font-bold">61.8%: $${lvls.entry}</span>
                    </div>
                `;
                list.appendChild(row);
            });
        }

        function renderSignalFeed(signals) {
            const container = document.getElementById('right-tab-feed');
            document.getElementById('feed-counter-label').innerText = `${signals.length} รายการ`;
            container.innerHTML = '';
            signals.forEach(sig => {
                const isSell = sig.direction === 'SELL';
                const card = document.createElement('div');
                card.className = `p-3 rounded-xl bg-slate-950 border border-slate-800 border-l-4 ${isSell ? 'border-l-rose-500' : 'border-l-emerald-500'} space-y-1 text-xs`;
                card.innerHTML = `
                    <div class="flex justify-between items-center">
                        <span class="font-bold text-white">${sig.symbol} • TF ${sig.tf} (${sig.direction})</span>
                        <span class="text-[10px] font-mono-num text-slate-400">${sig.time}</span>
                    </div>
                    <div class="flex flex-wrap gap-2 font-mono-num text-[11px] pt-0.5">
                        <span class="text-amber-300">0.5: $${sig.fib_05 || '-'}</span>
                        <span class="text-cyan-400 font-bold">61.8%: $${sig.entry}</span>
                        <span class="text-rose-400">SL: $${sig.sl}</span>
                        <span class="text-emerald-400">TP1: $${sig.tp1}</span>
                    </div>
                `;
                container.appendChild(card);
            });
        }

        async function loadSystemState() {
            try {
                const res = await fetch('/api/system-state');
                const data = await res.json();
                isNewsLocked = data.news_locked;
                allCalendarEvents = data.economic_calendar || [];
                updateNewsShieldUI(isNewsLocked, data.lock_reason);
                renderCalendarTable();
                renderSignalFeed(data.signal_history);
            } catch (e) {}
        }

        function filterNews(mode) {
            currentNewsFilter = mode;
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
            if (!filtered.length) {
                tbody.innerHTML = `<tr><td colspan="4" class="py-4 text-center text-slate-500">ไม่มีรายการข่าวในหมวดนี้</td></tr>`;
                return;
            }
            filtered.forEach(item => {
                const badge = item.impact === 'HIGH'
                    ? '<span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 font-bold text-[10px]">🔴 ข่าวแดง</span>'
                    : '<span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold text-[10px]">🟠 ปานกลาง</span>';
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="py-2 px-2 font-mono-num text-amber-300 whitespace-nowrap">${item.date_label} ${item.time_label}</td>
                    <td class="py-2 px-2 text-slate-200">${item.event}</td>
                    <td class="py-2 px-2 whitespace-nowrap">${badge}</td>
                    <td class="py-2 px-2 text-[11px] text-slate-400 whitespace-nowrap">${item.countdown}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        function updateNewsShieldUI(locked, reasonText) {
            const box = document.getElementById('news-shield-box');
            const dot = document.getElementById('shield-dot');
            const text = document.getElementById('shield-status-text');
            if (locked) {
                box.className = "bg-rose-950/60 border border-rose-500/60 px-3 py-1.5 rounded-xl flex items-center gap-2";
                dot.className = "w-2 h-2 rounded-full bg-rose-500 animate-ping";
                text.className = "text-[11px] font-bold text-rose-400";
                text.innerText = "ล็อกช่วงข่าวแดง";
            } else {
                box.className = "bg-emerald-950/40 border border-emerald-500/40 px-3 py-1.5 rounded-xl flex items-center gap-2";
                dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-ping";
                text.className = "text-[11px] font-bold text-emerald-400";
                text.innerText = "ตลาดปกติ";
            }
        }

        async function toggleNewsLock() {
            const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
            const data = await res.json();
            isNewsLocked = data.news_locked;
            updateNewsShieldUI(isNewsLocked, data.lock_reason);
        }

        function copyPrice(elementId) {
            const text = document.getElementById(elementId).innerText.replace('$', '');
            navigator.clipboard.writeText(text);
            showToast(`✅ คัดลอกราคา $${text} แล้ว`);
        }

        function showToast(msg) {
            const toast = document.getElementById('toast-notify');
            document.getElementById('toast-notify-text').innerText = msg;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 3200);
        }

        window.addEventListener('DOMContentLoaded', async () => {
            checkAuthStatus();
            await selectTimeframe('5m'); // เริ่มที่ M5 ทันที
            await loadSystemState();
            for (const k of Object.keys(timeframeMeta)) {
                if (k !== currentTfKey) { try { await fetchRealGoldCandles(k); } catch (e) {} }
            }
            renderMatrixTable(currentTfKey);

            // อัปเดตราคาบนหน้าเว็บอัตโนมัติทุก 20 วินาที
            setInterval(() => {
                triggerAutoFibonacciCalculation(false);
            }, 20000);
        });
    </script>
</body>
</html>
"""


# ==============================================================================
# 6. BACKEND API ENDPOINTS
# ==============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/system-state', methods=['GET'])
def get_system_state():
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()
    auto_locking_event = next((ev for ev in calendar_events if ev.get("is_locking_now")), None)
    is_locked = SYSTEM_STATE["manual_news_lock"] or (auto_locking_event is not None)

    return jsonify({
        "safe_to_trade": not is_locked,
        "news_locked": is_locked,
        "lock_reason": "ล็อกช่วงข่าวแดง" if is_locked else "ตลาดปกติ",
        "signal_history": SYSTEM_STATE["signal_history"],
        "economic_calendar": calendar_events,
        "server_time": now_dt.strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/api/user-config', methods=['POST'])
def save_user_config():
    data = request.json or {}
    email = data.get("email", "trader@gold.ai").strip().lower()
    USERS_DB[email] = {
        "email": email,
        "chat_id": str(data.get("chat_id", "")).strip(),
        "preferred_tf": data.get("preferred_tf", "5m").lower(),
        "start_time": data.get("start_time", "08:00"),
        "end_time": data.get("end_time", "23:59"),
        "alert_05": bool(data.get("alert_05", True)),
        "alert_618": bool(data.get("alert_618", True)),
        "auto_alert": True
    }
    return jsonify({"status": "ok", "user": USERS_DB[email]})


@app.route('/api/telegram-detect-chat', methods=['GET'])
def detect_telegram_chat():
    chat_id, first_name = fetch_latest_telegram_chat_id()
    if chat_id:
        return jsonify({"status": "ok", "chat_id": chat_id, "name": first_name})
    return jsonify({"status": "not_found"}), 404


@app.route('/api/test-telegram', methods=['POST'])
def test_telegram():
    data = request.json or {}
    chat_id = data.get("chat_id", "").strip()
    msg = (
        "✅ <b>เชื่อมต่อ GOLD AI SNIPER PRO สำเร็จ!</b>\n"
        "ระบบพร้อมส่งแจ้งเตือนอัตโนมัติเมื่อราคาทองคำแตะระดับ <b>0.5 (เตรียมตัว)</b> และ <b>61.8% (Golden Zone)</b> โดยไม่ต้องเปิดหน้าเว็บค้างไว้ครับ"
    )
    ok, err = send_telegram_message(chat_id, msg)
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": err}), 400


@app.route('/api/toggle-news-lock', methods=['POST'])
def toggle_news_lock():
    SYSTEM_STATE["manual_news_lock"] = not SYSTEM_STATE["manual_news_lock"]
    return jsonify({
        "status": "ok",
        "news_locked": SYSTEM_STATE["manual_news_lock"],
        "lock_reason": "ล็อกช่วงข่าวแดง" if SYSTEM_STATE["manual_news_lock"] else "ตลาดปกติ"
    })


@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()
    auto_locking_event = next((ev for ev in calendar_events if ev.get("is_locking_now")), None)

    if SYSTEM_STATE["manual_news_lock"] or auto_locking_event:
        return jsonify({
            "status": "blocked",
            "message": "ระบบล็อกการส่งเนื่องจากอยู่ในช่วงเฝ้าระวังข่าวแรง"
        }), 403

    data = request.json or {}
    chat_id = data.get("chat_id", "").strip()
    sig = {
        "id": len(SYSTEM_STATE["signal_history"]) + 101,
        "date": format_thai_date(now_dt),
        "time": now_dt.strftime("%H:%M:%S"),
        "symbol": data.get("symbol", "XAUUSD"),
        "tf": data.get("tf", "5M"),
        "direction": data.get("direction", "SELL"),
        "fib_05": data.get("fib_05", "0.00"),
        "entry": data.get("entry", "0.00"),
        "sl": data.get("sl", "0.00"),
        "tp1": data.get("tp1", "0.00"),
        "tp2": data.get("tp2", "0.00"),
        "status": "TELEGRAM SENT"
    }

    SYSTEM_STATE["latest_signal"] = sig
    SYSTEM_STATE["signal_history"].insert(0, sig)

    # ข้อความสั้น กระชับ เน้นตัวเลข ไม่รำคาญ
    msg = (
        f"🔔 <b>XAUUSD ({sig['tf']}) • โครงสร้าง {sig['direction']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🟡 <b>จุดเตรียมตัว (0.5):</b> ${sig['fib_05']}\n"
        f"🔵 <b>Golden Zone (61.8%):</b> ${sig['entry']}\n"
        f"🔴 <b>ระยะ 78.6% (SL):</b> ${sig['sl']}\n"
        f"🟢 <b>TP1 (1:2):</b> ${sig['tp1']}\n"
        f"🟡 <b>TP2 (1:3):</b> ${sig['tp2']}"
    )

    ok, err = send_telegram_message(chat_id, msg)
    if not ok:
        return jsonify({"status": "error", "message": f"ส่งเข้า Telegram ไม่สำเร็จ: {err}"}), 400

    return jsonify({
        "status": "success",
        "latest_signal": sig,
        "signal_history": SYSTEM_STATE["signal_history"]
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
