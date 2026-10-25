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
# 1. TELEGRAM BOT & SYSTEM CONFIGURATION
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "8718020170:AAFj1pPh4HLi8iVaz12hi_qAD_J4Dnlz1g"
).strip()
TELEGRAM_BOT_USERNAME = "gold_ai_sniper_pro_bot"

TH_TZ = timezone(timedelta(hours=7))
SIDEWAY_THRESHOLD_DOLLAR = 8.00

FF_CACHE = {
    "last_fetched": 0,
    "events": []
}

USERS_DB = {
    "default@gold.ai": {
        "email": "default@gold.ai",
        "chat_id": "8948986514",
        "preferred_tf": "5m",
        "auto_alert": True
    }
}

SYSTEM_STATE = {
    "manual_news_lock": False,
    "lock_reason": "NORMAL MARKET REGIME",
    "scanner_last_run": "-",
    "signal_history": [
        {
            "id": 102,
            "date": "25 ต.ค. 2026",
            "time": "16:30:00",
            "symbol": "XAUUSD",
            "tf": "5M",
            "direction": "SELL",
            "regime": "TRENDING",
            "range": "14.20",
            "fib_05": "2736.80",
            "entry": "2738.50",
            "sl": "2745.20",
            "tp1": "2725.10",
            "tp2": "2718.40",
            "status": "DISPATCHED"
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
# 2. TELEGRAM BOT ENGINE
# ==============================================================================
def send_telegram_message(chat_id, text):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False, "Missing Bot Token or Chat ID"
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": str(chat_id).strip(),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "GoldAISniperInstitutional/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if res_data.get("ok"):
                return True, "OK"
            return False, res_data.get("description", "Telegram API Error")
    except Exception as e:
        return False, str(e)


def fetch_latest_telegram_chat_id():
    if not TELEGRAM_BOT_TOKEN:
        return None, None
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=25"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok") and data.get("result"):
                for item in reversed(data["result"]):
                    msg = item.get("message") or item.get("edited_message") or item.get("my_chat_member")
                    if msg and "chat" in msg:
                        chat_id = str(msg["chat"]["id"])
                        first_name = msg["chat"].get("first_name") or "Trader"
                        return chat_id, first_name
    except Exception as e:
        print("Telegram getUpdates Error:", e)
    return None, None


# ==============================================================================
# 3. FIBONACCI & SIDEWAY ENGINE
# ==============================================================================
def calculate_fib_levels(direction, swing_high, swing_low):
    rng = max(0.50, swing_high - swing_low)
    is_sideway = rng < SIDEWAY_THRESHOLD_DOLLAR

    if direction == "SELL":
        fib_05 = swing_low + (rng * 0.500)
        entry = swing_low + (rng * 0.618)
        sl = swing_low + (rng * 0.786)
        risk = abs(sl - entry)
        tp1 = entry - (risk * 2.0)
        tp2 = entry - (risk * 3.0)
    else:
        fib_05 = swing_high - (rng * 0.500)
        entry = swing_high - (rng * 0.618)
        sl = swing_high - (rng * 0.786)
        risk = abs(entry - sl)
        tp1 = entry + (risk * 2.0)
        tp2 = entry + (risk * 3.0)

    return {
        "direction": "NO TRADE (SIDEWAY)" if is_sideway else direction,
        "raw_direction": direction,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "range": round(rng, 2),
        "is_sideway": is_sideway,
        "fib_05": round(fib_05, 2),
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2)
    }


def fetch_server_gold_candles(tf_key="5m"):
    tf_map = {"1m": ("1m", 90), "5m": ("5m", 96), "15m": ("15m", 96), "1h": ("1h", 100), "4h": ("4h", 100), "daily": ("1d", 90)}
    b_tf, lookback = tf_map.get(tf_key.lower(), ("5m", 96))
    url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={b_tf}&limit={lookback}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=6) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    swing_high = -1e9
    swing_low = 1e9
    high_idx, low_idx = 0, 0
    for idx, k in enumerate(raw):
        h, l = float(k[2]), float(k[3])
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
    levels["tf"] = tf_key.upper()
    return levels


# ==============================================================================
# 4. FOREX FACTORY CALENDAR & MORNING BRIEFING
# ==============================================================================
def compute_countdown_and_lock(event_dt, now_dt, impact):
    diff_sec = (event_dt - now_dt).total_seconds()
    is_same_day = (event_dt.date() == now_dt.date())
    is_tomorrow = (event_dt.date() == (now_dt.date() + timedelta(days=1)))
    is_auto_locking_now = (impact == "HIGH" and -1800 <= diff_sec <= 1800)

    if -1800 <= diff_sec <= 1800:
        countdown = "ACTIVE WINDOW (±30m)"
        urgency = "NOW"
    elif diff_sec < -1800:
        countdown = "COMPLETED"
        urgency = "PAST"
    else:
        hours = int(diff_sec // 3600)
        mins = int((diff_sec % 3600) // 60)
        days = int(diff_sec // 86400)
        if is_same_day:
            countdown = f"วันนี้ • อีก {hours}ชม. {mins}น." if hours > 0 else f"วันนี้ • อีก {mins} นาที!"
            urgency = "TODAY"
        elif is_tomorrow:
            countdown = f"พรุ่งนี้ • {event_dt.strftime('%H:%M')} น."
            urgency = "TOMORROW"
        else:
            countdown = f"อีก {days} วัน"
            urgency = "FUTURE"
    return countdown, urgency, is_auto_locking_now


def get_fallback_forex_factory_schedule(now_dt):
    base_date = now_dt.date()
    monday = base_date + timedelta(days=1) if now_dt.weekday() == 6 else base_date - timedelta(days=now_dt.weekday())
    template_events = [
        (0, 21, 0, "USD", "CB Consumer Confidence", "MEDIUM", "99.5", "98.7"),
        (1, 19, 30, "USD", "Prelim GDP q/q", "HIGH", "2.9%", "3.0%"),
        (2, 19, 15, "USD", "ADP Non-Farm Employment Change", "HIGH", "115K", "143K"),
        (2, 19, 30, "USD", "Core PCE / CPI Price Index m/m", "HIGH", "0.3%", "0.2%"),
        (3, 19, 30, "USD", "Initial Jobless Claims", "HIGH", "222K", "227K"),
        (4, 19, 30, "USD", "Non-Farm Employment Change (NFP)", "HIGH", "148K", "254K"),
    ]
    results = []
    for day_offset, hr, mn, curr, title, impact, forecast, previous in template_events:
        ev_date = monday + timedelta(days=day_offset)
        ev_dt = datetime(ev_date.year, ev_date.month, ev_date.day, hr, mn, tzinfo=TH_TZ)
        countdown, urgency, is_locking = compute_countdown_and_lock(ev_dt, now_dt, impact)
        lock_start = (ev_dt - timedelta(minutes=30)).strftime("%H:%M")
        lock_end = (ev_dt + timedelta(minutes=30)).strftime("%H:%M")
        rule_text = f"Auto-Lock {lock_start}–{lock_end}" if impact == "HIGH" else "Reduce Risk 50%"
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
            rule_text = f"Auto-Lock {lock_start}–{lock_end}" if impact_raw == "HIGH" else "Reduce Risk 50%"
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
                "status": rule_text
            })

    if not parsed_events:
        parsed_events = get_fallback_forex_factory_schedule(now_dt)

    all_events = SYSTEM_STATE["custom_news"] + parsed_events
    all_events.sort(key=lambda x: x.get("timestamp", 0))
    return all_events


def build_morning_news_brief_message(now_dt, calendar_events):
    today_iso = now_dt.strftime("%Y-%m-%d")
    today_high = [ev for ev in calendar_events if ev.get("iso_date") == today_iso and ev.get("impact") == "HIGH"]
    lines = [
        f"🌅 <b>GOLD AI SNIPER PRO — MORNING BRIEFING</b>",
        f"📅 <b>ประจำวัน:</b> {format_thai_date(now_dt)}",
        f"━━━━━━━━━━━━━━━━━━━━━━"
    ]
    if today_high:
        lines.append("🔴 <b>ข่าวแดง (HIGH IMPACT USD) วันนี้:</b>")
        for ev in today_high:
            lines.append(f"• <b>{ev['time_label']}</b> — {ev['event']}")
    else:
        lines.append("🟢 <b>ข่าวแดงวันนี้:</b> ไม่มีตารางข่าวแดงสหรัฐฯ")
    lines.append("🛡️ <b>ระบบป้องกัน:</b> ตรวจจับ Sideway และล็อกออเดอร์อัตโนมัติ")
    return "\n".join(lines)


# ==============================================================================
# 5. FRONTEND HTML TEMPLATE
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — Institutional Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Prompt:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-canvas: #06080E;
            --bg-surface: #0B0F17;
            --bg-elevated: #111726;
            --border-hairline: rgba(255, 255, 255, 0.07);
        }
        body { font-family: 'Inter', 'Prompt', sans-serif; background-color: var(--bg-canvas); color: #E2E8F0; margin: 0; }
        .font-mono-num { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
        .inst-panel { background-color: var(--bg-surface); border: 1px solid var(--border-hairline); }
        .inst-panel-gold { background: linear-gradient(180deg, rgba(17, 23, 38, 0.9) 0%, rgba(11, 15, 23, 0.98) 100%); border: 1px solid rgba(212, 175, 55, 0.28); }
        .inst-card-interactive { background-color: var(--bg-elevated); border: 1px solid var(--border-hairline); transition: all 0.15s ease; }
        .inst-card-interactive:hover { border-color: rgba(255, 255, 255, 0.2); transform: translateY(-1px); }
        .status-dot { width: 7px; height: 7px; border-radius: 9999px; display: inline-block; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: #06080E; }
        ::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 3px; }
    </style>
</head>
<body class="antialiased min-h-screen flex flex-col justify-between">

    <!-- MODAL 1: LOGIN -->
    <div id="auth-modal" class="fixed inset-0 bg-black/85 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="inst-panel-gold rounded-xl max-w-md w-full p-6 space-y-4">
            <h2 class="text-sm font-bold text-white uppercase">GOLD AI SNIPER PRO — Login</h2>
            <input type="email" id="login-email" placeholder="name@domain.com" class="w-full bg-[#06080E] border border-white/15 rounded-lg px-3 py-2 text-white font-mono-num text-xs outline-none">
            <label class="flex items-start gap-2 text-xs text-slate-300">
                <input type="checkbox" id="login-disclaimer" class="mt-0.5 accent-amber-500">
                <span>ยอมรับเงื่อนไขการเป็นเครื่องมือคำนวณทางสถิติเท่านั้น</span>
            </label>
            <button onclick="submitEmailLogin()" class="w-full py-2.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs">เข้าสู่ระบบ</button>
        </div>
    </div>

    <!-- MODAL 2: SETTINGS -->
    <div id="settings-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="inst-panel rounded-xl max-w-xl w-full p-6 space-y-4 max-h-[92vh] overflow-y-auto text-xs">
            <div class="flex justify-between items-center border-b border-white/10 pb-3">
                <h3 class="text-sm font-bold text-white uppercase">ตั้งค่า Telegram & ระบบสแกน</h3>
                <button onclick="toggleSettingsModal()" class="text-slate-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div class="bg-[#06080E] p-3.5 rounded-lg border border-white/10 space-y-2">
                <div class="font-bold text-amber-400 uppercase text-[10px]">STEP 1 • เชื่อมต่อบอท Telegram</div>
                <p class="text-slate-400">เปิดบอท @gold_ai_sniper_pro_bot แล้วพิมพ์ <code class="text-white bg-white/10 px-1 py-0.5 rounded">/start</code> จากนั้นกดปุ่มดึง Chat ID อัตโนมัติ</p>
                <div class="flex gap-2 pt-1">
                    <a href="https://t.me/gold_ai_sniper_pro_bot" target="_blank" class="px-3 py-2 rounded bg-sky-500 text-slate-950 font-bold">1. เปิดบอท</a>
                    <button onclick="autoDetectTelegramChatId()" class="px-3 py-2 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 font-bold">2. ดึง Chat ID อัตโนมัติ</button>
                </div>
            </div>
            <div>
                <label class="text-slate-300 font-semibold block mb-1">Telegram Chat ID</label>
                <div class="flex gap-2">
                    <input type="text" id="set-chat-id" value="8948986514" class="w-full bg-[#06080E] border border-white/15 rounded-lg px-3 py-2 text-white font-mono-num text-xs">
                    <button onclick="sendTestTelegram()" class="px-3 py-2 rounded bg-white/5 text-slate-200 border border-white/15 font-semibold shrink-0">ทดสอบส่ง</button>
                </div>
            </div>
            <div class="flex justify-end gap-2 pt-2 border-t border-white/10">
                <button onclick="toggleSettingsModal()" class="px-4 py-2 rounded bg-white/5 text-slate-300 font-semibold">ปิด</button>
                <button onclick="saveUserSettings()" class="px-5 py-2 rounded bg-amber-500 text-slate-950 font-bold">บันทึกการตั้งค่า</button>
            </div>
        </div>
    </div>

    <!-- HEADER -->
    <header class="inst-panel border-b border-white/10 px-4 py-2.5 sticky top-0 z-30 bg-[#0B0F17]/95">
        <div class="max-w-[1760px] mx-auto flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded bg-amber-500 flex items-center justify-center text-slate-950 font-mono-num font-black text-xs">XAU</div>
                <div>
                    <div class="flex items-center gap-2">
                        <span class="text-sm font-extrabold text-white">GOLD AI SNIPER</span>
                        <span class="text-[10px] font-mono-num font-bold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">PRO</span>
                    </div>
                    <span class="block text-[10px] text-slate-400">Institutional Fibonacci & Sideway Filter</span>
                </div>
            </div>
            <div class="flex flex-wrap items-center gap-2.5">
                <div id="top-regime-pill" class="px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-xs">
                    <span id="top-regime-dot" class="status-dot bg-emerald-400"></span>
                    <span id="top-regime-text" class="font-mono-num font-bold text-emerald-400 text-[11px]">REGIME: TRENDING</span>
                </div>
                <div class="bg-[#06080E] px-3 py-1 rounded border border-white/10 flex items-center gap-3">
                    <div>
                        <span class="text-[9px] font-mono-num uppercase text-slate-400 block">XAUUSD SPOT</span>
                        <span id="live-ticker-price" class="font-mono-num text-sm font-extrabold text-white">--</span>
                    </div>
                    <span id="proximity-pill" class="px-2 py-0.5 text-[10px] font-mono-num font-semibold rounded bg-white/5 text-slate-300 border border-white/10">SCANNING</span>
                </div>
                <button onclick="toggleSettingsModal()" class="px-3 py-1.5 rounded bg-sky-500/15 border border-sky-500/30 text-sky-300 text-xs font-semibold flex items-center gap-1.5">
                    <i class="fa-brands fa-telegram"></i> <span id="telegram-status-btn">TG: 8948986514</span>
                </button>
                <button onclick="openAuthModal()" class="px-3 py-1.5 rounded bg-white/5 border border-white/10 text-xs font-mono-num text-slate-300">
                    <span id="user-email-badge">Trader</span>
                </button>
            </div>
        </div>
    </header>

    <!-- MAIN -->
    <main class="max-w-[1760px] w-full mx-auto p-3 md:p-5 flex-1">
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">
            <!-- LEFT (7 COLS) -->
            <div class="xl:col-span-7 space-y-4">
                <section class="inst-panel rounded-xl p-3.5 space-y-3">
                    <div class="flex justify-between items-center border-b border-white/10 pb-2.5">
                        <span class="text-xs font-bold text-white uppercase">OANDA:XAUUSD • Real-Time Chart</span>
                        <button onclick="triggerAutoFibonacciCalculation(true)" class="py-1 px-3 rounded bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold">
                            <i id="fib-spin-icon" class="fa-solid fa-rotate mr-1"></i> Recalculate
                        </button>
                    </div>
                    <div class="tradingview-widget-container rounded-lg overflow-hidden border border-white/10" style="height:510px; width:100%;">
                        <div id="tradingview_advanced_chart" style="height:100%; width:100%;"></div>
                    </div>
                </section>

                <section class="inst-panel rounded-xl p-4 space-y-3">
                    <div class="flex justify-between items-center border-b border-white/10 pb-3">
                        <h2 class="text-xs font-bold text-white uppercase">Forex Factory Economic Calendar (UTC+7)</h2>
                        <button onclick="sendMorningBriefNow()" class="px-2.5 py-1 rounded text-[11px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30">
                            <i class="fa-brands fa-telegram mr-1"></i>ทดสอบส่งสรุปข่าวเช้า
                        </button>
                    </div>
                    <div class="overflow-x-auto max-h-[260px]">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-white/10 text-[10px] font-mono-num uppercase">
                                    <th class="py-2 px-2">วัน / เวลา</th>
                                    <th class="py-2 px-2">ข่าวเศรษฐกิจ (USD)</th>
                                    <th class="py-2 px-2">ระดับ</th>
                                    <th class="py-2 px-2 text-right">สถานะ</th>
                                </tr>
                            </thead>
                            <tbody id="economic-calendar-body" class="divide-y divide-white/5 font-mono-num text-[11px]"></tbody>
                        </table>
                    </div>
                </section>
            </div>

            <!-- RIGHT (5 COLS) -->
            <div class="xl:col-span-5 space-y-4">
                <section class="inst-panel rounded-xl p-4 space-y-3">
                    <div class="flex justify-between items-center">
                        <span class="text-xs font-bold text-white uppercase">1. Select Timeframe</span>
                        <span id="active-tf-badge" class="px-2 py-0.5 rounded text-[11px] font-mono-num font-bold bg-amber-500 text-slate-950">ACTIVE: 5M</span>
                    </div>
                    <div class="grid grid-cols-6 gap-1.5">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn py-2 rounded-lg text-xs font-mono-num font-bold border border-white/10 bg-[#06080E]">1M</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn py-2 rounded-lg text-xs font-mono-num font-bold border border-amber-400 bg-amber-500 text-slate-950">5M</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn py-2 rounded-lg text-xs font-mono-num font-bold border border-white/10 bg-[#06080E]">15M</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn py-2 rounded-lg text-xs font-mono-num font-bold border border-white/10 bg-[#06080E]">1H</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn py-2 rounded-lg text-xs font-mono-num font-bold border border-white/10 bg-[#06080E]">4H</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn py-2 rounded-lg text-xs font-mono-num font-bold border border-white/10 bg-[#06080E]">1D</button>
                    </div>
                </section>

                <!-- SIDEWAY FILTER BANNER -->
                <section id="regime-detector-card" class="inst-panel rounded-xl p-4 border-l-4 border-l-emerald-500">
                    <div class="flex justify-between items-start gap-3">
                        <div class="space-y-1">
                            <div class="flex items-center gap-2">
                                <span class="text-[10px] font-mono-num uppercase text-slate-400">SIDEWAY FILTER STATUS</span>
                                <span id="regime-badge-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400">TRENDING</span>
                            </div>
                            <h3 id="regime-headline" class="text-sm font-bold text-white">ตลาดมีทิศทางปกติ (พร้อมเทรดตาม Fibonacci)</h3>
                            <p id="regime-subtext" class="text-[11px] text-slate-400">กรอบสวิงกว้างกว่า $8.00 สามารถใช้ระดับ 0.5 และ 61.8% ตามระบบได้</p>
                        </div>
                        <div class="text-right shrink-0 bg-[#06080E] px-3 py-2 rounded-lg border border-white/10">
                            <span class="text-[9px] font-mono-num text-slate-400 block uppercase">RANGE</span>
                            <span id="regime-range-val" class="font-mono-num text-base font-extrabold text-emerald-400">$--</span>
                        </div>
                    </div>
                </section>

                <!-- MATRIX & MANUAL OVERRIDE -->
                <section class="inst-panel-gold rounded-xl p-4 space-y-3.5">
                    <div id="right-card-direction-banner" class="p-3.5 rounded-lg border flex justify-between items-center">
                        <div>
                            <span class="text-[10px] font-mono-num uppercase text-slate-400 block">TECHNICAL BIAS</span>
                            <div id="setup-order-badge" class="text-lg font-extrabold font-mono-num mt-0.5 text-white">--</div>
                        </div>
                        <div class="text-right font-mono-num text-xs space-y-0.5 bg-[#06080E]/80 px-3 py-1.5 rounded border border-white/10">
                            <div><span class="text-slate-400 text-[10px]">HIGH:</span> <strong id="display-swing-high" class="text-white">--</strong></div>
                            <div><span class="text-slate-400 text-[10px]">LOW:</span> <strong id="display-swing-low" class="text-white">--</strong></div>
                        </div>
                    </div>

                    <!-- 0.5 & 61.8% -->
                    <div onclick="copyPrice('val-fib05')" class="inst-card-interactive cursor-pointer p-3 rounded-lg border-l-4 border-l-amber-400 flex justify-between items-center text-xs">
                        <div>
                            <span class="font-bold text-amber-300 block">🔔 STAGE 1 • Fibonacci 0.5 (เตรียมตัว)</span>
                            <span class="text-[10px] text-slate-400">แจ้งเตือนล่วงหน้าก่อนเข้าโซน</span>
                        </div>
                        <span id="val-fib05" class="font-mono-num text-lg font-extrabold text-amber-400">--</span>
                    </div>

                    <div class="grid grid-cols-2 gap-2 text-xs">
                        <div onclick="copyPrice('val-entry')" class="inst-card-interactive cursor-pointer p-3 rounded-lg border-l-4 border-l-sky-400">
                            <span class="text-[10px] font-mono-num font-bold text-sky-400 block">🎯 STAGE 2 • 61.8% GOLDEN ZONE</span>
                            <div id="val-entry" class="text-lg font-extrabold font-mono-num text-white mt-1">--</div>
                        </div>
                        <div onclick="copyPrice('val-sl')" class="inst-card-interactive cursor-pointer p-3 rounded-lg border-l-4 border-l-rose-500">
                            <span class="text-[10px] font-mono-num font-bold text-rose-400 block">🔴 SL • 78.6%</span>
                            <div id="val-sl" class="text-lg font-extrabold font-mono-num text-rose-400 mt-1">--</div>
                        </div>
                        <div onclick="copyPrice('val-tp1')" class="inst-card-interactive cursor-pointer p-3 rounded-lg border-l-4 border-l-emerald-500">
                            <span class="text-[10px] font-mono-num font-bold text-emerald-400 block">🟢 TP1 (RR 1:2)</span>
                            <div id="val-tp1" class="text-lg font-extrabold font-mono-num text-emerald-400 mt-1">--</div>
                        </div>
                        <div onclick="copyPrice('val-tp2')" class="inst-card-interactive cursor-pointer p-3 rounded-lg border-l-4 border-l-amber-500">
                            <span class="text-[10px] font-mono-num font-bold text-amber-400 block">🟡 TP2 (RR 1:3)</span>
                            <div id="val-tp2" class="text-lg font-extrabold font-mono-num text-amber-400 mt-1">--</div>
                        </div>
                    </div>

                    <!-- MANUAL SWING OVERRIDE -->
                    <div class="bg-[#06080E] p-3 rounded-lg border border-white/10 space-y-2 text-xs">
                        <div class="font-bold text-amber-400 flex items-center justify-between">
                            <span><i class="fa-solid fa-sliders mr-1"></i> กรอกราคาจากกราฟ OANDA เอง (Manual Override)</span>
                        </div>
                        <p class="text-[10px] text-slate-400">นำตัวเลข High/Low ที่ตาเห็นจากกราฟ OANDA มากรอกตรงนี้เพื่อให้คำนวณเป๊ะ 100%</p>
                        <div class="grid grid-cols-3 gap-2">
                            <select id="custom-dir" class="bg-[#111726] border border-white/15 rounded p-1.5 text-white font-bold text-xs">
                                <option value="SELL">SELL BIAS</option>
                                <option value="BUY">BUY BIAS</option>
                            </select>
                            <input type="number" id="custom-high" step="0.1" placeholder="High จากกราฟ" class="bg-[#111726] border border-white/15 rounded p-1.5 text-white font-mono-num text-xs">
                            <input type="number" id="custom-low" step="0.1" placeholder="Low จากกราฟ" class="bg-[#111726] border border-white/15 rounded p-1.5 text-white font-mono-num text-xs">
                        </div>
                        <button onclick="applyCustomSwing()" class="w-full py-1.5 rounded bg-white/10 hover:bg-amber-500 hover:text-slate-950 text-slate-200 font-bold text-xs transition-all">
                            คำนวณ Fibonacci จากราคานี้ทันที
                        </button>
                    </div>

                    <button onclick="broadcastCurrentSignal()" class="w-full py-2.5 rounded-lg font-bold text-xs uppercase bg-amber-500 hover:bg-amber-400 text-slate-950 flex items-center justify-center gap-2 shadow-lg">
                        <i class="fa-brands fa-telegram"></i> <span>ส่งสัญญาณนี้เข้า Telegram ทันที</span>
                    </button>
                </section>
            </div>
        </div>
    </main>

    <footer class="border-t border-white/10 bg-[#0B0F17] py-3 text-center text-[11px] text-slate-500 mt-6">
        GOLD AI SNIPER PRO • Institutional Fibonacci Terminal
    </footer>

    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-[#111726] border border-amber-500/50 text-white px-4 py-2.5 rounded-lg font-medium text-xs shadow-2xl z-50">
        <span id="toast-notify-text">สำเร็จ</span>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        const SIDEWAY_THRESHOLD = 8.00;
        const timeframeMeta = {
            '1m': { label: '1M', tvInterval: '1', lookback: 90 },
            '5m': { label: '5M', tvInterval: '5', lookback: 96 },
            '15m': { label: '15M', tvInterval: '15', lookback: 96 },
            '1h': { label: '1H', tvInterval: '60', lookback: 100 },
            '4h': { label: '4H', tvInterval: '240', lookback: 100 },
            'daily': { label: '1D', tvInterval: 'D', lookback: 90 }
        };

        let liveTimeframeStore = {};
        let currentTfKey = '5m';
        let currentTvLoadedInterval = null;
        let allCalendarEvents = [];

        function calculateSniperMath(direction, swingHigh, swingLow) {
            const range = Math.max(0.5, swingHigh - swingLow);
            const isSideway = range < SIDEWAY_THRESHOLD;
            let fib05, entry, sl, risk, tp1, tp2;

            if (direction === 'SELL') {
                fib05 = swingLow + (range * 0.500);
                entry = swingLow + (range * 0.618);
                sl    = swingLow + (range * 0.786);
                risk  = Math.abs(sl - entry);
                tp1   = entry - (risk * 2.0);
                tp2   = entry - (risk * 3.0);
            } else {
                fib05 = swingHigh - (range * 0.500);
                entry = swingHigh - (range * 0.618);
                sl    = swingHigh - (range * 0.786);
                risk  = Math.abs(entry - sl);
                tp1   = entry + (risk * 2.0);
                tp2   = entry + (risk * 3.0);
            }

            return {
                rangeNum: range,
                range: range.toFixed(2),
                isSideway: isSideway,
                fib05Num: fib05, entryNum: entry, slNum: sl,
                fib05: fib05.toFixed(2),
                entry: entry.toFixed(2),
                sl: sl.toFixed(2),
                tp1: tp1.toFixed(2),
                tp2: tp2.toFixed(2)
            };
        }

        async function fetchRealGoldCandles(tfKey) {
            const meta = timeframeMeta[tfKey];
            const binanceTf = tfKey === 'daily' ? '1d' : tfKey;
            const url = `https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=${binanceTf}&limit=150`;
            const res = await fetch(url);
            const raw = await res.json();
            const candles = raw.map(k => ({ high: parseFloat(k[2]), low: parseFloat(k[3]), close: parseFloat(k[4]) }));
            const recentSlice = candles.slice(-meta.lookback);
            let swingHigh = -Infinity, swingLow = Infinity, highIdx = 0, lowIdx = 0;
            recentSlice.forEach((c, idx) => {
                if (c.high > swingHigh) { swingHigh = c.high; highIdx = idx; }
                if (c.low < swingLow) { swingLow = c.low; lowIdx = idx; }
            });
            const currentPrice = candles[candles.length - 1].close;
            const calcDir = (highIdx < lowIdx) ? 'SELL' : 'BUY';
            liveTimeframeStore[tfKey] = { swingHigh, swingLow, currentPrice, calcDir };
            return liveTimeframeStore[tfKey];
        }

        function updateRegimeBanners(mathRes) {
            const topPill = document.getElementById('top-regime-pill');
            const topText = document.getElementById('top-regime-text');
            const badge = document.getElementById('regime-badge-pill');
            const headline = document.getElementById('regime-headline');
            const subtext = document.getElementById('regime-subtext');
            const rangeVal = document.getElementById('regime-range-val');

            rangeVal.innerText = `$${mathRes.range}`;
            if (mathRes.isSideway) {
                topPill.className = "px-2.5 py-1 rounded bg-amber-500/15 border border-amber-500/40 flex items-center gap-2 text-xs";
                topText.className = "font-mono-num font-bold text-amber-400 text-[11px]";
                topText.innerText = `⚠️ SIDEWAY DETECTED ($${mathRes.range})`;
                badge.innerText = "NO TRADE / SIDEWAY";
                headline.className = "text-sm font-bold text-amber-300";
                headline.innerText = `⚠️ ตลาดเป็น SIDEWAY กรอบแคบ ($${mathRes.range} < $8.00)`;
                subtext.innerText = "ห้ามเข้าออเดอร์เด็ดขาด! Fibonacci ใช้ไม่ได้ผลในตลาดไร้ทิศทาง รอตลาดเลือกทางก่อน";
            } else {
                topPill.className = "px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-xs";
                topText.className = "font-mono-num font-bold text-emerald-400 text-[11px]";
                topText.innerText = "REGIME: TRENDING";
                badge.innerText = "TRENDING";
                headline.className = "text-sm font-bold text-white";
                headline.innerText = "ตลาดมีทิศทางปกติ (พร้อมเทรดตาม Fibonacci)";
                subtext.innerText = "กรอบสวิงกว้างกว่า $8.00 สามารถใช้ระดับ 0.5 และ 61.8% ตามระบบได้";
            }
        }

        function applyStateToUI(tfKey, state) {
            const mathRes = calculateSniperMath(state.calcDir, state.swingHigh, state.swingLow);
            document.getElementById('live-ticker-price').innerText = '$' + state.currentPrice.toFixed(2);
            document.getElementById('chart-tf-pill').innerText = 'TF ' + tfKey.toUpperCase();
            document.getElementById('display-swing-high').innerText = '$' + state.swingHigh.toFixed(2);
            document.getElementById('display-swing-low').innerText = '$' + state.swingLow.toFixed(2);

            document.getElementById('val-fib05').innerText = '$' + mathRes.fib05;
            document.getElementById('val-entry').innerText = '$' + mathRes.entry;
            document.getElementById('val-sl').innerText = '$' + mathRes.sl;
            document.getElementById('val-tp1').innerText = '$' + mathRes.tp1;
            document.getElementById('val-tp2').innerText = '$' + mathRes.tp2;

            document.getElementById('custom-dir').value = state.calcDir;
            document.getElementById('custom-high').value = state.swingHigh.toFixed(2);
            document.getElementById('custom-low').value = state.swingLow.toFixed(2);

            const rightBadge = document.getElementById('setup-order-badge');
            if (mathRes.isSideway) {
                rightBadge.className = "text-base font-extrabold font-mono-num text-amber-400";
                rightBadge.innerText = "⚠️ NO TRADE (ตลาดเป็น Sideway)";
            } else {
                rightBadge.className = `text-lg font-extrabold font-mono-num ${state.calcDir === 'SELL' ? 'text-rose-400' : 'text-emerald-400'}`;
                rightBadge.innerText = `${state.calcDir} BIAS • ${tfKey.toUpperCase()}`;
            }

            updateRegimeBanners(mathRes);
        }

        async function triggerAutoFibonacciCalculation(showNotification = true) {
            const icon = document.getElementById('fib-spin-icon');
            if (icon) icon.className = "fa-solid fa-spinner fa-spin mr-1";
            try {
                const state = await fetchRealGoldCandles(currentTfKey);
                applyStateToUI(currentTfKey, state);
                if (showNotification) showToast('คำนวณกรอบราคาเรียบร้อย');
            } catch (e) {
            } finally {
                if (icon) icon.className = "fa-solid fa-rotate mr-1";
            }
        }

        async function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const meta = timeframeMeta[tfKey];
            if (!meta) return;
            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn py-2 rounded-lg text-xs font-mono-num font-bold border border-white/10 bg-[#06080E] text-slate-400";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn py-2 rounded-lg text-xs font-mono-num font-extrabold bg-amber-500 text-slate-950 border border-amber-400";
            }
            document.getElementById('active-tf-badge').innerText = 'ACTIVE: ' + tfKey.toUpperCase();
            loadTradingViewStudio(meta.tvInterval);
            await triggerAutoFibonacciCalculation(false);
        }

        function applyCustomSwing() {
            const dir = document.getElementById('custom-dir').value;
            const high = parseFloat(document.getElementById('custom-high').value);
            const low = parseFloat(document.getElementById('custom-low').value);
            if (!high || !low || high <= low) {
                showToast('กรุณาระบุ Swing High ให้มากกว่า Swing Low');
                return;
            }
            const curPrice = liveTimeframeStore[currentTfKey]?.currentPrice || high;
            liveTimeframeStore[currentTfKey] = { swingHigh: high, swingLow: low, currentPrice: curPrice, calcDir: dir };
            applyStateToUI(currentTfKey, liveTimeframeStore[currentTfKey]);
            showToast('อัปเดตราคาจากกราฟ OANDA เรียบร้อย!');
        }

        function loadTradingViewStudio(intervalCode) {
            if (currentTvLoadedInterval === intervalCode) return;
            currentTvLoadedInterval = intervalCode;
            document.getElementById('tradingview_advanced_chart').innerHTML = '';
            new TradingView.widget({
                "width": "100%", "height": "510", "symbol": "OANDA:XAUUSD", "interval": intervalCode,
                "timezone": "Asia/Bangkok", "theme": "dark", "style": "1", "locale": "th",
                "toolbar_bg": "#0B0F17", "container_id": "tradingview_advanced_chart"
            });
        }

        function checkAuthStatus() {
            const savedEmail = localStorage.getItem('gold_sniper_email');
            const savedChatId = localStorage.getItem('gold_sniper_chat_id') || '8948986514';
            document.getElementById('set-chat-id').value = savedChatId;
            document.getElementById('telegram-status-btn').innerText = `TG: ${savedChatId}`;
            if (!savedEmail) {
                document.getElementById('auth-modal').classList.remove('hidden');
            } else {
                document.getElementById('user-email-badge').innerText = savedEmail.split('@')[0];
            }
        }

        function openAuthModal() { document.getElementById('auth-modal').classList.remove('hidden'); }

        async function submitEmailLogin() {
            const email = document.getElementById('login-email').value.trim();
            const accepted = document.getElementById('login-disclaimer').checked;
            if (!email || !accepted) { showToast('กรุณากรอกอีเมลและยอมรับเงื่อนไข'); return; }
            localStorage.setItem('gold_sniper_email', email);
            document.getElementById('user-email-badge').innerText = email.split('@')[0];
            document.getElementById('auth-modal').classList.add('hidden');
            showToast('เข้าสู่ระบบสำเร็จ');
        }

        function toggleSettingsModal() { document.getElementById('settings-modal').classList.toggle('hidden'); }

        async function autoDetectTelegramChatId() {
            try {
                const res = await fetch('/api/telegram-detect-chat');
                const data = await res.json();
                if (data.status === 'ok' && data.chat_id) {
                    document.getElementById('set-chat-id').value = data.chat_id;
                    localStorage.setItem('gold_sniper_chat_id', data.chat_id);
                    document.getElementById('telegram-status-btn').innerText = `TG: ${data.chat_id}`;
                    showToast(`พบ Chat ID: ${data.chat_id}`);
                } else { showToast('กรุณาทัก /start ในบอทก่อน'); }
            } catch (e) { showToast('ดึงข้อมูลไม่สำเร็จ'); }
        }

        async function saveUserSettings() {
            const chatId = document.getElementById('set-chat-id').value.trim();
            localStorage.setItem('gold_sniper_chat_id', chatId);
            document.getElementById('telegram-status-btn').innerText = `TG: ${chatId}`;
            await fetch('/api/user-config', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: localStorage.getItem('gold_sniper_email') || 'user@gold.ai', chat_id: chatId })
            });
            toggleSettingsModal();
            showToast('บันทึกการตั้งค่า Telegram เรียบร้อย');
        }

        async function sendTestTelegram() {
            const chatId = document.getElementById('set-chat-id').value.trim();
            const res = await fetch('/api/test-telegram', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId })
            });
            const data = await res.json();
            showToast(res.ok ? 'ส่งข้อความทดสอบสำเร็จ!' : 'ส่งไม่สำเร็จ: ' + data.message);
        }

        async function sendMorningBriefNow() {
            const chatId = document.getElementById('set-chat-id').value.trim() || '8948986514';
            const res = await fetch('/api/send-morning-brief', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId })
            });
            showToast(res.ok ? 'ส่งสรุปข่าวเข้า Telegram เรียบร้อย!' : 'ส่งไม่สำเร็จ');
        }

        async function broadcastCurrentSignal() {
            const chatId = document.getElementById('set-chat-id').value.trim() || localStorage.getItem('gold_sniper_chat_id');
            const mathRes = calculateSniperMath(
                document.getElementById('custom-dir').value,
                parseFloat(document.getElementById('display-swing-high').innerText.replace('$', '')),
                parseFloat(document.getElementById('display-swing-low').innerText.replace('$', ''))
            );
            if (mathRes.isSideway) {
                showToast('⚠️ ตลาดเป็น Sideway ห้ามเทรด ระบบไม่อนุญาตให้ส่งสัญญาณ!');
                return;
            }
            const res = await fetch('/api/send-signal', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: chatId, symbol: 'XAUUSD', tf: currentTfKey.toUpperCase(),
                    direction: document.getElementById('custom-dir').value,
                    fib_05: mathRes.fib05, entry: mathRes.entry, sl: mathRes.sl, tp1: mathRes.tp1, tp2: mathRes.tp2
                })
            });
            showToast(res.ok ? 'ส่งสัญญาณเข้า Telegram เรียบร้อย!' : 'ส่งไม่สำเร็จ');
        }

        async function loadSystemState() {
            try {
                const res = await fetch('/api/system-state');
                const data = await res.json();
                allCalendarEvents = data.economic_calendar || [];
                renderCalendarTable();
            } catch (e) {}
        }

        function renderCalendarTable() {
            const tbody = document.getElementById('economic-calendar-body');
            tbody.innerHTML = '';
            allCalendarEvents.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="py-2 px-2 text-amber-300 whitespace-nowrap">${item.date_label} • ${item.time_label}</td>
                    <td class="py-2 px-2 text-slate-200 font-sans">${item.event}</td>
                    <td class="py-2 px-2">${item.impact === 'HIGH' ? '<span class="text-rose-400 font-bold">HIGH</span>' : 'MED'}</td>
                    <td class="py-2 px-2 text-right text-slate-400">${item.status}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        function showToast(msg) {
            const toast = document.getElementById('toast-notify');
            document.getElementById('toast-notify-text').innerText = msg;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 3000);
        }

        window.addEventListener('DOMContentLoaded', async () => {
            checkAuthStatus();
            await selectTimeframe('5m');
            await loadSystemState();
            setInterval(() => triggerAutoFibonacciCalculation(false), 20000);
        });
    </script>
</body>
</html>
"""


# ==============================================================================
# 7. FLASK API ENDPOINTS
# ==============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/system-state', methods=['GET'])
def get_system_state():
    return jsonify({
        "economic_calendar": fetch_forex_factory_calendar(),
        "server_time": datetime.now(TH_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/api/user-config', methods=['POST'])
def save_user_config():
    data = request.json or {}
    email = data.get("email", "user@gold.ai").strip().lower()
    chat_id = str(data.get("chat_id", "8948986514")).strip()
    USERS_DB[email] = {"email": email, "chat_id": chat_id, "auto_alert": True}
    return jsonify({"status": "ok"})


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
    ok, err = send_telegram_message(chat_id, "✅ <b>GOLD AI SNIPER PRO — ทดสอบระบบสำเร็จ!</b> บอทพร้อมส่งแจ้งเตือนและฟิลเตอร์ Sideway แล้วครับ")
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": err}), 400


@app.route('/api/send-morning-brief', methods=['POST'])
def trigger_morning_brief():
    data = request.json or {}
    chat_id = data.get("chat_id", "8948986514").strip()
    now_dt = datetime.now(TH_TZ)
    msg = build_morning_news_brief_message(now_dt, fetch_forex_factory_calendar())
    ok, err = send_telegram_message(chat_id, msg)
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": err}), 400


@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    data = request.json or {}
    chat_id = data.get("chat_id", "").strip()
    msg = (
        f"🎯 <b>XAUUSD ({data.get('tf', '5M')}) • {data.get('direction')} SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 <b>0.5 (เตรียมตัว):</b> ${data.get('fib_05')}\n"
        f"🎯 <b>Golden Zone (61.8%):</b> ${data.get('entry')}\n"
        f"🔴 <b>SL (78.6%):</b> ${data.get('sl')}\n"
        f"🟢 <b>TP1:</b> ${data.get('tp1')} | <b>TP2:</b> ${data.get('tp2')}"
    )
    ok, err = send_telegram_message(chat_id, msg)
    if not ok:
        return jsonify({"status": "error", "message": err}), 400
    return jsonify({"status": "success"})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
