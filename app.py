import os
import json
import time
import html
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from flask import Flask, Response, request, jsonify

app = Flask(__name__)

# ==============================================================================
# 1. CONFIG (ทุกอย่างอ่านจาก Environment Variables บน Render — ห้าม hardcode Token)
# ==============================================================================
def _clean_token(t):
    t = (t or "").strip().strip('"').strip("'").strip()
    if t.lower().startswith("bot"):
        t = t[3:]
    return t


TELEGRAM_BOT_TOKEN = _clean_token(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "gold_ai_sniper_pro_bot")
OWNER_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8948986514").strip()

OANDA_API_KEY = os.environ.get("OANDA_API_KEY", "").strip()
OANDA_ENV = os.environ.get("OANDA_ENV", "practice").strip().lower()   # practice | live
OANDA_PRICE = os.environ.get("OANDA_PRICE", "B").strip().upper()      # B=Bid (ค่าเริ่มต้นของกราฟ TradingView), M=Mid, A=Ask
OANDA_HOST = "https://api-fxtrade.oanda.com" if OANDA_ENV == "live" else "https://api-fxpractice.oanda.com"
OANDA_KEY_MAP = {"B": "bid", "M": "mid", "A": "ask"}

USERS_FILE = os.environ.get("USERS_FILE", "/tmp/gold_sniper_users.json")

TH_TZ = timezone(timedelta(hours=7))

# เกณฑ์ตรวจ Sideway (ปรับได้ — ใช้หลายปัจจัยร่วมกัน ไม่ใช่ threshold เดียว)
ER_MIN = 0.25           # Efficiency Ratio ของขาแรง (ต่ำ = ราคาแกว่งไปมา)
RANGE_ATR_MIN = 6.0     # กรอบ Swing ต้องกว้างอย่างน้อยกี่เท่าของ ATR(14)
ATR_RATIO_MIN = 0.70    # ATR(14) / ค่าเฉลี่ย TR 100 แท่ง (ต่ำ = ความผันผวนหด)
MIN_LEG_BARS = 4
SIDEWAY_FAIL_COUNT = 2  # ตกเกณฑ์ตั้งแต่กี่ข้อถือเป็น Sideway

TF_CFG = {
    "1m":    {"oanda": "M1",  "binance": "1m",  "lookback": 90,  "secs": 60},
    "5m":    {"oanda": "M5",  "binance": "5m",  "lookback": 96,  "secs": 300},
    "15m":   {"oanda": "M15", "binance": "15m", "lookback": 96,  "secs": 900},
    "1h":    {"oanda": "H1",  "binance": "1h",  "lookback": 100, "secs": 3600},
    "4h":    {"oanda": "H4",  "binance": "4h",  "lookback": 100, "secs": 14400},
    "daily": {"oanda": "D",   "binance": "1d",  "lookback": 90,  "secs": 86400},
}

FF_CACHE = {"last_fetched": 0, "last_try": 0, "events": []}
LEVELS_CACHE = {}
LEVELS_LOCK = threading.Lock()
OVERRIDES = {}          # tf -> {"direction","high","low"}  (Manual override sync กับกราฟ)
USERS_DB = {}           # key = chat_id (หรืออีเมลถ้ายังไม่มี chat_id)
BRIEFING_SENT = {}      # chat_id -> "YYYY-MM-DD"
ALERT_MEMORY = {}       # กันส่งซ้ำในสวิงเดิม

STATE = {
    "manual_news_lock": False,
    "oanda_error": None,
    "signal_history": [],
}

THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
THAI_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def format_thai_date(dt_obj):
    return f"{THAI_DAYS[dt_obj.weekday()]} {dt_obj.day} {THAI_MONTHS[dt_obj.month]} {dt_obj.year}"


def http_json(url, headers=None, data=None, timeout=8):
    h = {"User-Agent": "Mozilla/5.0"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ==============================================================================
# 2. USERS (บันทึกลงไฟล์แบบ best-effort + Owner จาก ENV เพื่อให้ทำงานแม้ restart)
# ==============================================================================
def default_user(chat_id="", email=""):
    return {
        "email": email, "chat_id": chat_id, "preferred_tf": "5m",
        "start_time": "08:00", "end_time": "23:59",
        "alert_05": True, "alert_618": True, "auto_alert": True,
        "briefing": True, "briefing_time": "07:30",
    }


def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(USERS_DB, f, ensure_ascii=False)
    except Exception as e:
        print("save_users:", e)


def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                USERS_DB.update(data)
    except Exception:
        pass
    if OWNER_CHAT_ID and OWNER_CHAT_ID not in USERS_DB:
        USERS_DB[OWNER_CHAT_ID] = default_user(OWNER_CHAT_ID, "owner")


# ==============================================================================
# 3. TELEGRAM (อ่าน Token จาก ENV, แปลง error ให้อ่านง่าย)
# ==============================================================================
def tg_call(method, payload=None, timeout=8):
    """คืนค่า (ok, result_or_message)"""
    if not TELEGRAM_BOT_TOKEN:
        return False, "ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN ใน Render Environment"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        body = http_json(url, headers=headers, data=data, timeout=timeout)
        if body.get("ok"):
            return True, body.get("result")
        return False, body.get("description", "Telegram returned ok=false")
    except urllib.error.HTTPError as e:
        desc = ""
        try:
            desc = json.loads(e.read().decode("utf-8")).get("description", "")
        except Exception:
            pass
        if e.code in (401, 404):
            msg = "Token ไม่ถูกต้อง/ถูกเพิกถอน/ไม่ครบ (HTTP %d) — ตรวจ TELEGRAM_BOT_TOKEN บน Render" % e.code
        elif e.code == 403:
            msg = "บอทถูกบล็อก หรือผู้ใช้ยังไม่ได้กด /start (403)"
        elif e.code == 400 and "chat not found" in desc.lower():
            msg = "ไม่พบ Chat ID นี้ — เปิดบอทแล้วกด /start ก่อน"
        else:
            msg = f"HTTP {e.code}: {desc}" if desc else f"HTTP {e.code}"
        print("Telegram error:", method, msg)
        return False, msg
    except Exception as e:
        print("Telegram error:", method, type(e).__name__)
        return False, f"เชื่อมต่อ Telegram ไม่ได้: {type(e).__name__}"


def send_telegram_message(chat_id, text):
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return False, "ไม่มี Chat ID"
    return tg_call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def fetch_latest_telegram_chat_id():
    ok, res = tg_call("getUpdates?limit=10", None, timeout=6)
    if ok and res:
        for item in reversed(res):
            msg = item.get("message") or item.get("my_chat_member")
            if msg and "chat" in msg:
                return str(msg["chat"]["id"]), msg["chat"].get("first_name", "Trader")
    return None, None


# ==============================================================================
# 4. ข้อมูลราคา: OANDA (ตรงกับกราฟ OANDA:XAUUSD) + ตัวสำรอง Binance PAXG
# ==============================================================================
def _fetch_oanda(cfg):
    key = OANDA_KEY_MAP.get(OANDA_PRICE, "bid")
    url = (f"{OANDA_HOST}/v3/instruments/XAU_USD/candles"
           f"?granularity={cfg['oanda']}&count=300&price={OANDA_PRICE if OANDA_PRICE in OANDA_KEY_MAP else 'B'}")
    raw = http_json(url, headers={"Authorization": f"Bearer {OANDA_API_KEY}"}, timeout=8)
    out = []
    for c in raw.get("candles", []):
        p = c.get(key)
        if not p:
            continue
        t = datetime.strptime(c["time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        out.append({"t": t, "h": float(p["h"]), "l": float(p["l"]), "c": float(p["c"])})
    if not out:
        raise RuntimeError("OANDA returned no candles")
    return out


def _fetch_binance(cfg):
    url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={cfg['binance']}&limit=300"
    raw = http_json(url, timeout=8)
    return [{"t": k[0] / 1000.0, "h": float(k[2]), "l": float(k[3]), "c": float(k[4])} for k in raw]


def fetch_candles(tf):
    cfg = TF_CFG[tf]
    if OANDA_API_KEY:
        try:
            candles = _fetch_oanda(cfg)
            STATE["oanda_error"] = None
            return candles, "OANDA"
        except Exception as e:
            STATE["oanda_error"] = f"OANDA: {str(e)[:120]}"
            print("OANDA fetch failed:", STATE["oanda_error"])
    else:
        STATE["oanda_error"] = "ยังไม่ได้ตั้งค่า OANDA_API_KEY"
    return _fetch_binance(cfg), "BINANCE_PAXG"


# ==============================================================================
# 5. FIBONACCI + ตัวกรอง SIDEWAY (ATR + Swing compression + Leg efficiency)
# ==============================================================================
def calculate_fib_levels(direction, swing_high, swing_low):
    rng = max(0.5, swing_high - swing_low)
    if direction == "SELL":
        fib_05 = swing_low + rng * 0.500
        entry = swing_low + rng * 0.618
        sl = swing_low + rng * 0.786
        risk = abs(sl - entry)
        tp1, tp2 = entry - risk * 2, entry - risk * 3
    else:
        fib_05 = swing_high - rng * 0.500
        entry = swing_high - rng * 0.618
        sl = swing_high - rng * 0.786
        risk = abs(entry - sl)
        tp1, tp2 = entry + risk * 2, entry + risk * 3
    return {"fib_05": round(fib_05, 2), "entry": round(entry, 2), "sl": round(sl, 2),
            "tp1": round(tp1, 2), "tp2": round(tp2, 2), "risk": round(risk, 2)}


def analyze(candles, lookback):
    n = len(candles)
    if n < 30:
        return None
    trs = []
    for i in range(1, n):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs[-14:]) / min(14, len(trs))
    long_trs = trs[-100:]
    atr_long = sum(long_trs) / len(long_trs)

    window = candles[-lookback:]
    hi, lo, hi_i, lo_i = -1e18, 1e18, 0, 0
    for i, c in enumerate(window):
        if c["h"] > hi:
            hi, hi_i = c["h"], i
        if c["l"] < lo:
            lo, lo_i = c["l"], i

    a, b = sorted((hi_i, lo_i))
    leg_bars = b - a
    path = sum(abs(window[i]["c"] - window[i - 1]["c"]) for i in range(a + 1, b + 1))
    net = abs(window[b]["c"] - window[a]["c"])
    er = net / path if path > 0 else 0.0
    range_atr = (hi - lo) / atr if atr > 0 else 0.0
    atr_ratio = atr / atr_long if atr_long > 0 else 0.0

    fails = []
    if leg_bars < MIN_LEG_BARS:
        fails.append(f"ขาแรงสั้นเกินไป ({leg_bars} แท่ง)")
    if er < ER_MIN:
        fails.append(f"ราคาแกว่งไปมา (Efficiency {er:.2f} < {ER_MIN})")
    if range_atr < RANGE_ATR_MIN:
        fails.append(f"กรอบ Swing แคบ ({range_atr:.1f}×ATR < {RANGE_ATR_MIN:g})")
    if atr_ratio < ATR_RATIO_MIN:
        fails.append(f"ความผันผวนหดตัว (ATR ratio {atr_ratio:.2f} < {ATR_RATIO_MIN})")

    sideway = atr <= 0 or leg_bars < MIN_LEG_BARS or len(fails) >= SIDEWAY_FAIL_COUNT
    direction = "SELL" if hi_i < lo_i else "BUY"
    if sideway:
        status = "SIDEWAY"
    else:
        status = "TREND_DOWN" if direction == "SELL" else "TREND_UP"

    return {
        "swing_high": round(hi, 2), "swing_low": round(lo, 2), "direction": direction,
        "current_price": round(candles[-1]["c"], 2),
        "market": {
            "status": status, "reasons": fails,
            "metrics": {"atr": round(atr, 2), "range_atr": round(range_atr, 2),
                        "leg_er": round(er, 2), "atr_ratio": round(atr_ratio, 2), "leg_bars": leg_bars},
        },
    }


def build_base(tf):
    cfg = TF_CFG[tf]
    candles, source = fetch_candles(tf)
    a = analyze(candles, cfg["lookback"])
    if not a:
        raise RuntimeError("ข้อมูลแท่งเทียนไม่พอ")
    last_t = candles[-1]["t"]
    a["source"] = source
    a["last_candle_ts"] = int(last_t)
    a["closed"] = (time.time() - last_t) > (2 * cfg["secs"] + 1800)
    return a


def get_levels(tf):
    tf = (tf or "5m").lower()
    if tf not in TF_CFG:
        tf = "5m"
    now = time.time()
    with LEVELS_LOCK:
        cached = LEVELS_CACHE.get(tf)
        if cached and now - cached[0] < 12:
            base = cached[1]
        else:
            try:
                base = build_base(tf)
                LEVELS_CACHE[tf] = (now, base)
            except Exception:
                if cached and now - cached[0] < 180:
                    base = cached[1]
                else:
                    raise
    d = json.loads(json.dumps(base))
    ov = OVERRIDES.get(tf)
    d["manual"] = bool(ov)
    if ov:
        d["swing_high"], d["swing_low"], d["direction"] = ov["high"], ov["low"], ov["direction"]
    d["blocked"] = d["market"]["status"] == "SIDEWAY"
    d["levels"] = None if d["blocked"] else calculate_fib_levels(d["direction"], d["swing_high"], d["swing_low"])
    d["tf"] = tf
    d["oanda_error"] = STATE["oanda_error"] if d["source"] != "OANDA" else None
    d["as_of"] = datetime.now(TH_TZ).strftime("%H:%M:%S")
    return d


# ==============================================================================
# 6. FOREX FACTORY CALENDAR (ไม่มีข้อมูลปลอม — ถ้าดึงไม่ได้จะแสดงว่าไม่พร้อมใช้งาน)
# ==============================================================================
def compute_countdown_and_lock(event_dt, now_dt, impact):
    diff_sec = (event_dt - now_dt).total_seconds()
    is_same_day = event_dt.date() == now_dt.date()
    is_tomorrow = event_dt.date() == (now_dt.date() + timedelta(days=1))
    is_locking = impact == "HIGH" and -1800 <= diff_sec <= 1800

    if -1800 <= diff_sec <= 1800:
        return "🔥 กำลังประกาศข่าว! (เฝ้าระวัง ±30 นาที)", "NOW", is_locking
    if diff_sec < -1800:
        return "ประกาศผลแล้ว", "PAST", False
    hours = int(diff_sec // 3600)
    mins = int((diff_sec % 3600) // 60)
    days = int(diff_sec // 86400)
    if is_same_day:
        text = f"วันนี้ • อีก {hours} ชม. {mins} นาที" if hours > 0 else f"⚠️ วันนี้ • อีก {mins} นาที!"
        return text, "TODAY", False
    if is_tomorrow:
        return f"พรุ่งนี้ • เวลา {event_dt.strftime('%H:%M')} น.", "TOMORROW", False
    return f"อีก {days} วัน ({format_thai_date(event_dt)})", "FUTURE", False


def fetch_forex_factory_calendar():
    now_dt = datetime.now(TH_TZ)
    now_ts = now_dt.timestamp()

    if not FF_CACHE["events"] or now_ts - FF_CACHE["last_fetched"] >= 900:
        if now_ts - FF_CACHE["last_try"] >= 120:      # backoff กันยิงถี่เมื่อ FF ล่ม/ rate limit
            FF_CACHE["last_try"] = now_ts
            try:
                data = http_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=6)
                if isinstance(data, list) and data:
                    FF_CACHE["events"] = data
                    FF_CACHE["last_fetched"] = now_ts
            except Exception as e:
                print("FF fetch failed:", type(e).__name__)

    parsed = []
    for item in FF_CACHE["events"]:
        if item.get("country") != "USD":
            continue
        impact = str(item.get("impact", "")).upper()
        if impact not in ("HIGH", "MEDIUM"):
            continue
        try:
            ev_dt = datetime.fromisoformat(item.get("date", "")).astimezone(TH_TZ)
        except Exception:
            continue
        countdown, urgency, locking = compute_countdown_and_lock(ev_dt, now_dt, impact)
        ls = (ev_dt - timedelta(minutes=30)).strftime("%H:%M")
        le = (ev_dt + timedelta(minutes=30)).strftime("%H:%M")
        parsed.append({
            "timestamp": int(ev_dt.timestamp()),
            "date_label": format_thai_date(ev_dt),
            "iso_date": ev_dt.strftime("%Y-%m-%d"),
            "time_label": ev_dt.strftime("%H:%M น."),
            "time_short": ev_dt.strftime("%H:%M"),
            "currency": "USD",
            "event": item.get("title", "USD Event"),
            "impact": impact,
            "forecast": item.get("forecast") or "-",
            "previous": item.get("previous") or "-",
            "countdown": countdown, "urgency": urgency, "is_locking_now": locking,
            "lock_window": f"{ls}-{le}" if impact == "HIGH" else "",
            "status": f"ล็อกอัตโนมัติ {ls}-{le} น." if impact == "HIGH" else "ระวังความผันผวน",
        })
    parsed.sort(key=lambda x: x["timestamp"])
    return parsed


def is_news_locked(events=None):
    events = events if events is not None else fetch_forex_factory_calendar()
    return STATE["manual_news_lock"] or any(ev.get("is_locking_now") for ev in events)


# ==============================================================================
# 7. BACKGROUND WORKERS: Price scanner + Morning briefing
# ==============================================================================
def parse_hhmm(s, default=(7, 30)):
    try:
        h, m = map(int, str(s).split(":"))
        return h, m
    except Exception:
        return default


def is_within_schedule(now_dt, start_str, end_str):
    try:
        cur = now_dt.hour * 60 + now_dt.minute
        sh, sm = parse_hhmm(start_str, (8, 0))
        eh, em = parse_hhmm(end_str, (23, 59))
        s, e = sh * 60 + sm, eh * 60 + em
        return s <= cur <= e if s <= e else (cur >= s or cur <= e)
    except Exception:
        return True


def scan_once():
    now_dt = datetime.now(TH_TZ)
    if is_news_locked() or not USERS_DB:
        return

    tf_data = {}
    for u in list(USERS_DB.values()):
        if u.get("chat_id") and u.get("auto_alert", True):
            tf = str(u.get("preferred_tf", "5m")).lower()
            if tf not in tf_data:
                try:
                    tf_data[tf] = get_levels(tf)
                except Exception as e:
                    print("scan get_levels:", tf, type(e).__name__)
                    tf_data[tf] = None

    for user in list(USERS_DB.values()):
        chat_id = user.get("chat_id")
        if not chat_id or not user.get("auto_alert", True):
            continue
        if not is_within_schedule(now_dt, user.get("start_time", "08:00"), user.get("end_time", "23:59")):
            continue
        tf = str(user.get("preferred_tf", "5m")).lower()
        d = tf_data.get(tf)
        if not d or d["blocked"] or d["closed"] or not d["levels"]:
            continue   # SIDEWAY / ตลาดปิด => ไม่ส่งสัญญาณ

        L = d["levels"]
        price = d["current_price"]
        rng = max(1.0, d["swing_high"] - d["swing_low"])
        tol = max(0.45, rng * 0.035)
        key = f"{chat_id}_{tf}_{d['swing_high']}_{d['swing_low']}"
        mem = ALERT_MEMORY.get(key, {})

        if user.get("alert_05", True) and not mem.get("sent_05") and abs(price - L["fib_05"]) <= tol:
            msg = (f"⚠️ <b>[เตรียมตัว] ราคาแตะระดับ 0.5 (50.0%)</b>\n"
                   f"📊 <b>XAUUSD ({tf.upper()})</b> • โครงสร้างฝั่ง <b>{d['direction']}</b>\n"
                   f"━━━━━━━━━━━━━━━━━━\n"
                   f"🟡 <b>ราคาปัจจุบัน:</b> ${price:.2f}\n"
                   f"🔔 <b>ระดับ 0.5:</b> ${L['fib_05']:.2f}\n"
                   f"🔵 <b>โซน 61.8% ถัดไป:</b> ${L['entry']:.2f}\n"
                   f"🔴 <b>78.6% (SL):</b> ${L['sl']:.2f}\n"
                   f"🟢 <b>TP1 / TP2:</b> ${L['tp1']:.2f} / ${L['tp2']:.2f}")
            ok, _ = send_telegram_message(chat_id, msg)
            if ok:
                mem["sent_05"] = True
                ALERT_MEMORY[key] = mem

        if user.get("alert_618", True) and not mem.get("sent_618") and abs(price - L["entry"]) <= tol:
            msg = (f"🎯 <b>[เข้าโซน] ราคาแตะ Golden Zone 61.8%</b>\n"
                   f"📊 <b>XAUUSD ({tf.upper()})</b> • โครงสร้างฝั่ง <b>{d['direction']}</b>\n"
                   f"━━━━━━━━━━━━━━━━━━\n"
                   f"🔵 <b>61.8%:</b> ${L['entry']:.2f}\n"
                   f"🔴 <b>78.6% (SL):</b> ${L['sl']:.2f}\n"
                   f"🟢 <b>TP1 (1:2):</b> ${L['tp1']:.2f}\n"
                   f"🟡 <b>TP2 (1:3):</b> ${L['tp2']:.2f}")
            ok, _ = send_telegram_message(chat_id, msg)
            if ok:
                mem["sent_618"] = True
                ALERT_MEMORY[key] = mem

    if len(ALERT_MEMORY) > 500:
        for k in list(ALERT_MEMORY.keys())[:250]:
            ALERT_MEMORY.pop(k, None)


def scanner_loop():
    while True:
        try:
            scan_once()
        except Exception as e:
            print("Scanner error:", type(e).__name__, e)
        time.sleep(25)


def build_morning_briefing(user, now_dt):
    events = fetch_forex_factory_calendar()
    today = now_dt.strftime("%Y-%m-%d")
    lines = [f"☀️ <b>Morning Briefing — {format_thai_date(now_dt)}</b>",
             "━━━━━━━━━━━━━━━━━━"]
    if not FF_CACHE["events"]:
        lines.append("⚠️ ดึงปฏิทินข่าว Forex Factory ไม่ได้ในขณะนี้ — โปรดตรวจข่าวด้วยตนเอง")
    else:
        highs = [e for e in events if e["iso_date"] == today and e["impact"] == "HIGH"]
        if not highs:
            lines.append("✅ วันนี้ไม่มีข่าวแดง (High Impact) ของ USD")
        else:
            lines.append(f"🔴 <b>ข่าวแดง USD วันนี้ ({len(highs)} รายการ) — เวลาไทย</b>")
            for e in highs:
                lines.append(
                    f"\n🕒 <b>{e['time_short']} น.</b> — {html.escape(e['event'])}\n"
                    f"     คาดการณ์: {html.escape(str(e['forecast']))} • ก่อนหน้า: {html.escape(str(e['previous']))}\n"
                    f"     🛑 ระบบงดแจ้งเตือน {e['lock_window']} น.")
    try:
        d = get_levels(user.get("preferred_tf", "5m"))
        st = d["market"]["status"]
        label = {"SIDEWAY": "⛔ SIDEWAY (งดสัญญาณ)", "TREND_DOWN": "🔴 แนวโน้มขาลง (SELL)",
                 "TREND_UP": "🟢 แนวโน้มขาขึ้น (BUY)"}.get(st, st)
        lines.append(f"\n📊 <b>XAUUSD {d['tf'].upper()}:</b> ${d['current_price']:.2f} • {label}")
    except Exception:
        pass
    lines.append("\n<i>เครื่องมือคำนวณทางสถิติ ไม่ใช่คำแนะนำการลงทุน</i>")
    return "\n".join(lines)


def briefing_loop():
    while True:
        try:
            now_dt = datetime.now(TH_TZ)
            today = now_dt.strftime("%Y-%m-%d")
            if now_dt.weekday() < 5:
                for user in list(USERS_DB.values()):
                    chat_id = user.get("chat_id")
                    if not chat_id or not user.get("briefing", True) or BRIEFING_SENT.get(chat_id) == today:
                        continue
                    hh, mm = parse_hhmm(user.get("briefing_time", "07:30"))
                    target = now_dt.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    if target <= now_dt <= target + timedelta(minutes=90):
                        ok, _ = send_telegram_message(chat_id, build_morning_briefing(user, now_dt))
                        if ok:
                            BRIEFING_SENT[chat_id] = today
        except Exception as e:
            print("Briefing error:", type(e).__name__, e)
        time.sleep(30)


_workers_started = False


def start_background_workers():
    global _workers_started
    if _workers_started:
        return
    _workers_started = True
    load_users()
    for fn in (scanner_loop, briefing_loop):
        threading.Thread(target=fn, daemon=True).start()


start_background_workers()


# ==============================================================================
# 8. FRONTEND
# ==============================================================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — Auto Fibonacci & Telegram Alert</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root { --bg-deep:#03060c; --bg-card:rgba(13,20,36,.88); --border-subtle:rgba(255,255,255,.08); }
        body { font-family:'Prompt',sans-serif; background-color:var(--bg-deep);
               background-image:radial-gradient(circle at 10% 5%,rgba(245,158,11,.08),transparent 35%),radial-gradient(circle at 90% 10%,rgba(6,182,212,.08),transparent 35%);
               color:#f1f5f9; overflow-x:hidden; }
        .font-mono-num { font-family:'JetBrains Mono',monospace; }
        .pro-card { background:var(--bg-card); backdrop-filter:blur(16px); border:1px solid var(--border-subtle); box-shadow:0 18px 40px -15px rgba(0,0,0,.7); }
        .pro-card-gold { background:linear-gradient(145deg,rgba(18,27,48,.95),rgba(9,14,26,.98)); border:1px solid rgba(245,158,11,.4); }
        .btn-interactive { transition:all .2s ease; }
        .btn-interactive:hover:not(:disabled) { transform:translateY(-2px); }
        .btn-interactive:active:not(:disabled) { transform:translateY(0) scale(.98); }
        .btn-interactive:disabled { opacity:.45; cursor:not-allowed; }
        .price-box { transition:all .2s ease; }
        .price-box:hover { transform:translateY(-2px); border-color:rgba(255,255,255,.3); }
        .dim-levels { opacity:.35; }
        #chart-wrapper { position:relative; height:500px; width:100%; }
        #chart-wrapper:fullscreen { height:100vh !important; width:100vw !important; border-radius:0; background:#03060c; }
        #chart-wrapper.fs-fallback { position:fixed; inset:0; z-index:9999; height:100vh !important; width:100vw !important; border-radius:0; background:#03060c; }
        ::-webkit-scrollbar { width:6px; height:6px; }
        ::-webkit-scrollbar-track { background:#03060c; }
        ::-webkit-scrollbar-thumb { background:#1e293b; border-radius:9999px; }
    </style>
</head>
<body class="antialiased min-h-screen p-3 md:p-5">

    <!-- MODAL: LOGIN -->
    <div id="auth-modal" class="fixed inset-0 bg-slate-950/90 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="pro-card pro-card-gold rounded-2xl max-w-md w-full p-6 space-y-5 border border-amber-500/40">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-400 to-yellow-600 flex items-center justify-center text-slate-950 font-black text-xl shadow-lg">XAU</div>
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
                    <div class="font-bold text-amber-400 flex items-center gap-1.5"><i class="fa-solid fa-scale-balanced"></i> ข้อตกลงการใช้งาน (Disclaimer)</div>
                    <p>เว็บแอปพลิเคชันนี้เป็นเพียง <strong>เครื่องมือช่วยคำนวณตัวเลขทางคณิตศาสตร์ (Fibonacci Retracement) และแสดงข้อมูลทางสถิติอัตโนมัติเท่านั้น</strong> มิใช่การให้คำแนะนำทางการเงินหรือการชักชวนลงทุน (Not Financial Advice) ผู้ใช้งานเป็นผู้ตัดสินใจและรับความเสี่ยงด้วยตนเอง 100%</p>
                    <label class="flex items-start gap-2 pt-1 cursor-pointer select-none text-white font-semibold">
                        <input type="checkbox" id="login-disclaimer" class="mt-0.5 rounded accent-amber-500 w-4 h-4">
                        <span>ฉันอ่านและยอมรับว่านี่คือเครื่องมือคำนวณทางสถิติเท่านั้น</span>
                    </label>
                </div>
            </div>
            <button onclick="submitEmailLogin()" class="btn-interactive w-full py-3 rounded-xl bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 font-black text-sm shadow-lg">เข้าสู่ระบบและใช้งานเครื่องมือ</button>
        </div>
    </div>

    <!-- MODAL: TELEGRAM SETTINGS -->
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
                <button onclick="toggleSettingsModal()" class="text-slate-400 hover:text-white text-lg px-2"><i class="fa-solid fa-xmark"></i></button>
            </div>

            <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2.5 text-xs">
                <div class="font-bold text-cyan-300">STEP 1: กดปุ่ม Start ในแอป Telegram ก่อน</div>
                <p class="text-slate-400 text-[11px]">เปิดบอท <strong>@gold_ai_sniper_pro_bot</strong> แล้วกด <strong>Start (/start)</strong> 1 ครั้ง</p>
                <div class="flex flex-wrap gap-2 pt-1">
                    <a href="https://t.me/gold_ai_sniper_pro_bot" target="_blank" class="btn-interactive px-3.5 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-extrabold inline-flex items-center gap-1.5"><i class="fa-brands fa-telegram text-sm"></i> 1. เปิดบอท</a>
                    <button onclick="autoDetectTelegramChatId()" class="btn-interactive px-3.5 py-2 rounded-xl bg-amber-500/20 border border-amber-500/50 text-amber-300 font-bold inline-flex items-center gap-1.5"><i class="fa-solid fa-wand-magic-sparkles"></i> 2. ดึง Chat ID อัตโนมัติ</button>
                </div>
            </div>

            <div class="space-y-3 text-xs">
                <div>
                    <label class="text-slate-300 font-bold block mb-1">Telegram Chat ID ของคุณ</label>
                    <div class="flex gap-2">
                        <input type="text" id="set-chat-id" placeholder="เช่น 123456789" class="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white font-mono-num">
                        <button onclick="sendTestTelegram()" class="btn-interactive px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-500/30 font-bold shrink-0">ทดสอบส่ง</button>
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
                    <div class="font-bold text-amber-400 text-[11px]">เงื่อนไขจุดแจ้งเตือนอัตโนมัติ</div>
                    <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" id="set-alert-05" checked class="accent-amber-500 w-4 h-4"><span>🔔 <strong>เตือนล่วงหน้าเมื่อแตะ 0.5 (50.0%)</strong></span></label>
                    <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" id="set-alert-618" checked class="accent-cyan-500 w-4 h-4"><span>🎯 <strong>เตือนเมื่อเข้า Golden Zone 61.8%</strong> พร้อมกรอบ SL/TP</span></label>
                    <div class="text-[10px] text-slate-500">* ตลาด Sideway / ช่วงข่าวแดง / ตลาดปิด ระบบจะงดส่งทุกการแจ้งเตือนอัตโนมัติ</div>
                </div>

                <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
                    <div class="font-bold text-amber-400 text-[11px]">☀️ Morning Briefing (สรุปข่าวแดง USD ทุกเช้า จันทร์-ศุกร์)</div>
                    <div class="flex items-center gap-3 flex-wrap">
                        <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" id="set-briefing" checked class="accent-amber-500 w-4 h-4"><span>เปิดใช้งาน</span></label>
                        <input type="time" id="set-briefing-time" value="07:30" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                        <button onclick="sendTestBriefing()" class="btn-interactive px-3 py-2 rounded-lg bg-slate-800 text-cyan-300 border border-cyan-500/30 font-bold">ทดสอบส่งเดี๋ยวนี้</button>
                    </div>
                </div>
            </div>

            <div class="flex justify-end gap-2 pt-2">
                <button onclick="toggleSettingsModal()" class="px-4 py-2.5 rounded-xl bg-slate-800 text-slate-300 text-xs font-bold">ปิด</button>
                <button onclick="saveUserSettings()" class="btn-interactive px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-400 to-emerald-400 text-slate-950 font-black text-xs"><i class="fa-solid fa-floppy-disk mr-1"></i> บันทึกการตั้งค่าทั้งหมด</button>
            </div>
        </div>
    </div>

    <div class="max-w-[1680px] mx-auto space-y-4">

        <!-- HEADER -->
        <header class="pro-card rounded-2xl p-4 lg:px-6 flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
            <div class="flex items-center gap-3.5">
                <div class="px-3.5 py-2 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 flex flex-col items-center justify-center shadow-lg font-black text-slate-950">
                    <span class="text-[9px] tracking-tighter leading-none">SNIPER</span>
                    <span class="text-base tracking-tight leading-none font-mono-num">XAU</span>
                </div>
                <div>
                    <div class="flex flex-wrap items-center gap-2">
                        <h1 class="text-lg md:text-xl font-black tracking-tight text-white">GOLD AI SNIPER PRO</h1>
                        <span class="px-2 py-0.5 text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-full">AUTO FIB 0.5 & 61.8%</span>
                    </div>
                    <p class="text-[11px] text-slate-400">เครื่องมือคำนวณกรอบราคาทางเทคนิคอัตโนมัติ & แจ้งเตือนผ่าน Telegram</p>
                </div>
            </div>

            <div class="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-between lg:justify-end">
                <div class="bg-slate-950 px-3.5 py-1.5 rounded-xl border border-slate-800 flex items-center gap-2.5">
                    <div>
                        <span class="block text-[9px] text-slate-400 font-bold uppercase">XAUUSD <span id="source-pill" class="ml-1 px-1 rounded bg-slate-800 text-slate-300">--</span></span>
                        <span id="live-ticker-price" class="font-mono-num text-sm font-black text-emerald-400">--</span>
                    </div>
                    <span id="proximity-pill" class="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-300">รอคำนวณ...</span>
                </div>

                <div id="news-shield-box" class="bg-emerald-950/40 border border-emerald-500/40 px-3 py-1.5 rounded-xl flex items-center gap-2">
                    <span id="shield-dot" class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    <span id="shield-status-text" class="text-[11px] font-bold text-emerald-400">ตลาดปกติ</span>
                    <button onclick="toggleNewsLock()" class="text-[10px] bg-slate-900 hover:bg-slate-800 px-2 py-0.5 rounded border border-slate-700 text-slate-300">สลับโหมด</button>
                </div>

                <button onclick="toggleSettingsModal()" class="btn-interactive px-3.5 py-2 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/40 text-cyan-300 text-xs font-extrabold flex items-center gap-1.5">
                    <i class="fa-brands fa-telegram text-sm"></i><span id="telegram-status-btn">ตั้งค่า Telegram</span>
                </button>
                <button onclick="openAuthModal()" class="btn-interactive px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs font-bold text-amber-300 flex items-center gap-1.5">
                    <i class="fa-regular fa-user"></i><span id="user-email-badge">เข้าสู่ระบบ</span>
                </button>
            </div>
        </header>

        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">

            <!-- LEFT -->
            <div class="xl:col-span-7 space-y-4">
                <div class="pro-card rounded-2xl p-4 space-y-3">
                    <div class="flex flex-wrap justify-between items-center gap-2">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-bold text-white"><i class="fa-solid fa-chart-line text-amber-400 mr-1.5"></i>กราฟราคาทองคำ (OANDA:XAUUSD)</span>
                            <span id="chart-tf-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">TF 5M</span>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="toggleChartFullscreen()" class="btn-interactive py-1.5 px-3.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-100 text-xs font-bold flex items-center gap-1.5">
                                <i class="fa-solid fa-expand"></i> ขยายเต็มจอ
                            </button>
                            <button onclick="refreshNow(true)" class="btn-interactive py-1.5 px-3.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black flex items-center gap-1.5">
                                <i id="fib-spin-icon" class="fa-solid fa-rotate"></i> คำนวณกรอบราคาใหม่
                            </button>
                        </div>
                    </div>

                    <div id="chart-wrapper" class="rounded-xl overflow-hidden border border-slate-800">
                        <button id="fs-exit" onclick="toggleChartFullscreen()" class="hidden absolute top-16 right-20 z-20 px-3 py-2 rounded-xl bg-slate-900/90 border border-slate-600 text-white text-xs font-bold items-center gap-1.5">
                            <i class="fa-solid fa-compress"></i> ออกจากเต็มจอ (Esc)
                        </button>
                        <div id="tradingview_advanced_chart" style="height:100%; width:100%;"></div>
                    </div>
                </div>

                <div class="pro-card rounded-2xl p-4 space-y-3">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-2.5">
                        <div>
                            <h2 class="text-sm font-bold text-white"><i class="fa-regular fa-calendar-days text-rose-400 mr-1.5"></i>ปฏิทินข่าวเศรษฐกิจ Forex Factory (เวลาไทย)</h2>
                            <p class="text-[11px] text-slate-400">ระบบงดส่งแจ้งเตือนอัตโนมัติในช่วงข่าวแดง ±30 นาที</p>
                        </div>
                        <div class="flex gap-1.5">
                            <button onclick="filterNews('ALL')" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-amber-500 text-slate-950">ทั้งหมด</button>
                            <button onclick="filterNews('TODAY')" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-900 text-slate-300 border border-slate-800">วันนี้</button>
                            <button onclick="filterNews('HIGH')" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-900 text-rose-400 border border-slate-800">🔴 ข่าวแดง</button>
                        </div>
                    </div>
                    <div class="overflow-x-auto max-h-[260px]">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-slate-800 text-[10px] uppercase">
                                    <th class="py-2 px-2">วัน / เวลา</th><th class="py-2 px-2">ข่าวเศรษฐกิจ (USD)</th>
                                    <th class="py-2 px-2">ระดับ</th><th class="py-2 px-2">สถานะเวลา</th>
                                </tr>
                            </thead>
                            <tbody id="economic-calendar-body" class="divide-y divide-slate-800/50"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- RIGHT -->
            <div class="xl:col-span-5 space-y-4">

                <!-- NO TRADE BANNER -->
                <div id="no-trade-banner" class="hidden rounded-2xl border-2 border-rose-500 bg-rose-950/70 p-4 text-center space-y-1 animate-pulse">
                    <div class="text-2xl font-black text-rose-400 tracking-wide">⛔ NO TRADE / SIDEWAY ZONE</div>
                    <div class="text-[12px] text-rose-200 font-bold">ตลาดไม่มีเทรนด์ชัดเจน — ระบบปิดการคำนวณระดับราคาและงดส่งสัญญาณทั้งหมด</div>
                    <div id="no-trade-reasons" class="text-[11px] text-rose-300/90"></div>
                </div>

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

                <div class="pro-card pro-card-gold rounded-2xl p-4 space-y-3.5">
                    <div id="right-card-direction-banner" class="p-3.5 rounded-xl border text-center space-y-0.5">
                        <div class="text-[10px] font-bold uppercase tracking-wider opacity-85">โครงสร้างกรอบราคาทางเทคนิคปัจจุบัน</div>
                        <div id="setup-order-badge" class="text-xl md:text-2xl font-black font-mono-num">--</div>
                        <div id="setup-order-subtext" class="text-[11px] opacity-90">--</div>
                    </div>

                    <div id="levels-wrap" class="space-y-3.5">
                        <div onclick="copyPrice('val-fib05')" class="price-box cursor-pointer bg-amber-500/10 border border-amber-500/50 p-3 rounded-xl flex justify-between items-center">
                            <div>
                                <span class="text-[10px] font-extrabold text-amber-300 uppercase block">🔔 จุดแจ้งเตือนล่วงหน้า (FIBONACCI 0.5 / 50.0%)</span>
                                <span class="text-[11px] text-slate-300">แตะจุดนี้ ระบบเตือนให้เตรียมตัวก่อนถึงโซน 61.8%</span>
                            </div>
                            <div class="text-right shrink-0 ml-2">
                                <span id="val-fib05" class="font-mono-num text-xl font-black text-amber-400 block">--</span>
                                <span class="text-[9px] bg-amber-500/20 text-amber-200 px-1.5 py-0.5 rounded">คลิกคัดลอก</span>
                            </div>
                        </div>

                        <div class="grid grid-cols-2 gap-2.5">
                            <div onclick="copyPrice('val-entry')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-cyan-500/50">
                                <div class="flex justify-between items-center"><span class="text-[11px] font-extrabold text-cyan-300">🔵 GOLDEN ZONE (61.8%)</span><span class="text-[9px] text-cyan-400">คัดลอก</span></div>
                                <div id="val-entry" class="text-xl font-black font-mono-num text-cyan-400 mt-1">--</div>
                            </div>
                            <div onclick="copyPrice('val-sl')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-rose-500/50">
                                <div class="flex justify-between items-center"><span class="text-[11px] font-extrabold text-rose-300">🔴 ระยะความเสี่ยง (78.6%)</span><span id="val-risk-pts" class="text-[9px] font-mono-num text-rose-300">--</span></div>
                                <div id="val-sl" class="text-xl font-black font-mono-num text-rose-400 mt-1">--</div>
                            </div>
                            <div onclick="copyPrice('val-tp1')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-emerald-500/40">
                                <div class="flex justify-between items-center"><span class="text-[11px] font-extrabold text-emerald-300">🟢 เป้าสถิติ TP1 (1:2)</span><span id="val-tp1-pts" class="text-[9px] font-mono-num text-emerald-300">--</span></div>
                                <div id="val-tp1" class="text-xl font-black font-mono-num text-emerald-400 mt-1">--</div>
                            </div>
                            <div onclick="copyPrice('val-tp2')" class="price-box cursor-pointer bg-slate-950/90 p-3 rounded-xl border border-amber-500/40">
                                <div class="flex justify-between items-center"><span class="text-[11px] font-extrabold text-amber-300">🟡 เป้าสถิติ TP2 (1:3)</span><span id="val-tp2-pts" class="text-[9px] font-mono-num text-amber-300">--</span></div>
                                <div id="val-tp2" class="text-xl font-black font-mono-num text-amber-400 mt-1">--</div>
                            </div>
                        </div>
                    </div>

                    <div class="bg-slate-950/90 p-3 rounded-xl border border-slate-800 flex flex-wrap justify-between items-center gap-2 text-xs">
                        <div class="flex gap-3 font-mono-num">
                            <span>⬆️ High: <strong id="display-swing-high" class="text-white">--</strong></span>
                            <span>⬇️ Low: <strong id="display-swing-low" class="text-white">--</strong></span>
                            <span id="manual-pill" class="hidden px-1.5 rounded bg-fuchsia-500/20 text-fuchsia-300 text-[10px] font-bold">MANUAL</span>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-[11px] text-slate-400">ทุน($):</span>
                            <input type="number" id="acc-balance" value="1000" oninput="recalcLotSize()" class="w-16 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-white font-mono-num text-xs">
                            <span id="calc-lot-result" class="text-[11px] font-mono-num font-bold text-cyan-300">0.05 Lot</span>
                        </div>
                    </div>

                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="btn-interactive w-full py-3 px-4 rounded-xl font-black text-xs md:text-sm bg-gradient-to-r from-cyan-400 via-teal-400 to-emerald-400 text-slate-950 shadow-lg flex items-center justify-center gap-2">
                        <i class="fa-brands fa-telegram text-base"></i><span>ส่งระดับราคาชุดนี้เข้า Telegram ทันที</span>
                    </button>
                </div>

                <details class="pro-card rounded-2xl p-3.5 text-xs">
                    <summary class="font-bold text-amber-400 cursor-pointer select-none flex justify-between items-center">
                        <span><i class="fa-solid fa-sliders mr-1.5"></i>Manual Override: ซิงก์ Swing High / Low ให้ตรงกับกราฟ</span>
                        <span class="text-[10px] text-slate-400">คลิกเพื่อเปิด/ปิด</span>
                    </summary>
                    <div class="grid grid-cols-3 gap-2 pt-3">
                        <select id="custom-dir" class="bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-bold">
                            <option value="SELL">🔴 ฝั่ง SELL</option><option value="BUY">🟢 ฝั่ง BUY</option>
                        </select>
                        <input type="number" id="custom-high" step="0.01" placeholder="Swing High" class="bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                        <input type="number" id="custom-low" step="0.01" placeholder="Swing Low" class="bg-slate-950 border border-slate-700 rounded-lg p-2 text-white font-mono-num">
                    </div>
                    <div class="grid grid-cols-2 gap-2 mt-2">
                        <button onclick="applyCustomSwing()" class="py-2 rounded-lg bg-slate-800 hover:bg-amber-500 hover:text-slate-950 text-amber-300 font-bold">ใช้ค่านี้ (ซิงก์ทั้งเว็บ+Telegram)</button>
                        <button onclick="clearCustomSwing()" class="py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold">ล้างค่า → ใช้อัตโนมัติ</button>
                    </div>
                    <p class="text-[10px] text-slate-500 pt-2">* ตัวกรอง Sideway ยังทำงานตามข้อมูลตลาดจริง แม้ใช้ Manual</p>
                </details>

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

        <footer class="text-center text-[11px] text-slate-500 py-2">
            ข้อมูลทั้งหมดเกิดจากการคำนวณสูตรคณิตศาสตร์ Fibonacci อัตโนมัติเพื่อประกอบการวิเคราะห์ทางเทคนิคเท่านั้น ไม่ใช่คำแนะนำในการลงทุน
        </footer>
    </div>

    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-emerald-400 text-slate-950 px-4 py-3 rounded-xl font-extrabold text-xs shadow-2xl z-[10000] flex items-center gap-2 max-w-[90vw]">
        <i class="fa-solid fa-bell"></i><span id="toast-notify-text">ดำเนินการสำเร็จ!</span>
    </div>

    <script src="https://s3.tradingview.com/tv.js"></script>
    <script>
        const timeframeMeta = {
            '1m': { tv: '1' }, '5m': { tv: '5' }, '15m': { tv: '15' },
            '1h': { tv: '60' }, '4h': { tv: '240' }, 'daily': { tv: 'D' }
        };
        const liveTimeframeStore = {};
        let currentTfKey = '5m';
        let currentTvLoadedInterval = null;
        let isNewsLocked = false;
        let currentRiskDollar = 5.0;
        let allCalendarEvents = [];
        let currentNewsFilter = 'ALL';
        let localAlertMemory = {};
        let tgWarned = false;

        const money = v => (v === null || v === undefined) ? '--' : '$' + Number(v).toFixed(2);

        function playBeepSound() {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator(); const gain = ctx.createGain();
                osc.type = 'sine'; osc.frequency.setValueAtTime(880, ctx.currentTime);
                gain.gain.setValueAtTime(0.08, ctx.currentTime);
                osc.connect(gain); gain.connect(ctx.destination);
                osc.start(); osc.stop(ctx.currentTime + 0.18);
            } catch (e) {}
        }

        // ---------------- DATA (ทุกตัวเลขมาจาก backend ชุดเดียวกับ Telegram) ----------------
        async function fetchLevels(tfKey) {
            const res = await fetch('/api/levels?tf=' + tfKey);
            const d = await res.json();
            if (!res.ok) throw new Error(d.message || 'levels error');
            liveTimeframeStore[tfKey] = d;
            return d;
        }

        function updateSourcePill(d) {
            const el = document.getElementById('source-pill');
            if (d.source === 'OANDA') {
                el.className = 'ml-1 px-1 rounded bg-emerald-500/20 text-emerald-300';
                el.innerText = 'OANDA ✓'; el.title = 'ข้อมูลจาก OANDA API ตรงกับกราฟ';
            } else {
                el.className = 'ml-1 px-1 rounded bg-rose-500/30 text-rose-200';
                el.innerText = '⚠ PAXG สำรอง';
                el.title = 'ไม่ใช่ราคา OANDA — ' + (d.oanda_error || 'ตั้งค่า OANDA_API_KEY บน Render');
            }
        }

        function checkProximityAndAlert(tfKey, d) {
            const pill = document.getElementById('proximity-pill');
            if (d.blocked) {
                pill.className = 'px-2 py-0.5 text-[10px] font-extrabold rounded bg-rose-500/30 text-rose-200';
                pill.innerText = '⛔ SIDEWAY — งดสัญญาณ'; return;
            }
            if (d.closed) {
                pill.className = 'px-2 py-0.5 text-[10px] font-bold rounded bg-slate-700 text-slate-200';
                pill.innerText = '💤 ตลาดปิด (ราคาล่าสุด)'; return;
            }
            const L = d.levels, price = d.current_price;
            const rng = Math.max(1.0, d.swing_high - d.swing_low);
            const tol = Math.max(0.45, rng * 0.035);
            const key = `${tfKey}_${d.swing_high}_${d.swing_low}`;
            if (Math.abs(price - L.entry) <= tol) {
                pill.className = 'px-2 py-0.5 text-[10px] font-extrabold rounded bg-cyan-500 text-slate-950 animate-pulse';
                pill.innerText = '🎯 ราคาอยู่ในโซน 61.8%!';
                if (localAlertMemory[key] !== '618') { localAlertMemory[key] = '618'; playBeepSound(); showToast(`🎯 [${tfKey.toUpperCase()}] ราคาแตะ Golden Zone 61.8% (${money(L.entry)})`); }
            } else if (Math.abs(price - L.fib_05) <= tol) {
                pill.className = 'px-2 py-0.5 text-[10px] font-extrabold rounded bg-amber-400 text-slate-950 animate-pulse';
                pill.innerText = '🔔 แตะระดับ 0.5 (เตรียมตัว!)';
                if (!localAlertMemory[key]) { localAlertMemory[key] = '05'; playBeepSound(); showToast(`🔔 [${tfKey.toUpperCase()}] ราคาแตะระดับ 0.5 (${money(L.fib_05)})`); }
            } else {
                pill.className = 'px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-300';
                pill.innerText = `รอแตะ 0.5 (${money(L.fib_05)})`;
            }
        }

        function applyStateToUI(tfKey, d) {
            const L = d.levels;
            currentRiskDollar = L ? L.risk : 0;
            document.getElementById('live-ticker-price').innerText = money(d.current_price);
            document.getElementById('chart-tf-pill').innerText = 'TF ' + tfKey.toUpperCase();
            document.getElementById('display-swing-high').innerText = money(d.swing_high);
            document.getElementById('display-swing-low').innerText = money(d.swing_low);
            document.getElementById('manual-pill').classList.toggle('hidden', !d.manual);
            updateSourcePill(d);

            document.getElementById('val-fib05').innerText = money(L && L.fib_05);
            document.getElementById('val-entry').innerText = money(L && L.entry);
            document.getElementById('val-sl').innerText = money(L && L.sl);
            document.getElementById('val-tp1').innerText = money(L && L.tp1);
            document.getElementById('val-tp2').innerText = money(L && L.tp2);
            document.getElementById('val-risk-pts').innerText = L ? `-$${L.risk.toFixed(2)}` : '--';
            document.getElementById('val-tp1-pts').innerText = L ? `+$${(L.risk * 2).toFixed(2)}` : '--';
            document.getElementById('val-tp2-pts').innerText = L ? `+$${(L.risk * 3).toFixed(2)}` : '--';
            document.getElementById('levels-wrap').classList.toggle('dim-levels', d.blocked);

            const active = document.activeElement ? document.activeElement.id : '';
            if (!['custom-dir', 'custom-high', 'custom-low'].includes(active)) {
                document.getElementById('custom-dir').value = d.direction;
                document.getElementById('custom-high').value = d.swing_high.toFixed(2);
                document.getElementById('custom-low').value = d.swing_low.toFixed(2);
            }

            const banner = document.getElementById('right-card-direction-banner');
            const badge = document.getElementById('setup-order-badge');
            const sub = document.getElementById('setup-order-subtext');
            const nt = document.getElementById('no-trade-banner');
            const btn = document.getElementById('broadcast-btn');

            nt.classList.toggle('hidden', !d.blocked);
            btn.disabled = d.blocked;

            if (d.blocked) {
                document.getElementById('no-trade-reasons').innerText = (d.market.reasons || []).join(' • ');
                banner.className = 'p-3.5 rounded-xl border border-slate-600 bg-slate-900/60 text-center space-y-0.5';
                badge.className = 'text-xl md:text-2xl font-black font-mono-num text-slate-300';
                badge.innerText = `⛔ SIDEWAY (${tfKey.toUpperCase()})`;
                sub.innerText = 'ยังไม่ยืนยันเทรนด์ — ไม่คำนวณ Fibonacci / ไม่ส่งสัญญาณ';
            } else if (d.direction === 'SELL') {
                banner.className = 'p-3.5 rounded-xl border border-rose-500/70 bg-rose-950/40 text-center space-y-0.5';
                badge.className = 'text-xl md:text-2xl font-black font-mono-num text-rose-400';
                badge.innerText = `🔴 เทรนด์ขาลง • ฝั่ง SELL (${tfKey.toUpperCase()})`;
                sub.innerText = `เตือนล่วงหน้า 0.5: ${money(L.fib_05)} • โซน 61.8%: ${money(L.entry)}`;
            } else {
                banner.className = 'p-3.5 rounded-xl border border-emerald-500/70 bg-emerald-950/40 text-center space-y-0.5';
                badge.className = 'text-xl md:text-2xl font-black font-mono-num text-emerald-400';
                badge.innerText = `🟢 เทรนด์ขาขึ้น • ฝั่ง BUY (${tfKey.toUpperCase()})`;
                sub.innerText = `เตือนล่วงหน้า 0.5: ${money(L.fib_05)} • โซน 61.8%: ${money(L.entry)}`;
            }

            checkProximityAndAlert(tfKey, d);
            recalcLotSize();
            renderMatrixTable(tfKey);
        }

        function recalcLotSize() {
            const balance = parseFloat(document.getElementById('acc-balance').value) || 1000;
            const riskMoney = balance * 0.015;
            const lossPerOneLot = Math.max(0.5, currentRiskDollar) * 100;
            document.getElementById('calc-lot-result').innerText = `${Math.max(0.01, riskMoney / lossPerOneLot).toFixed(2)} Lot`;
        }

        async function refreshNow(notify) {
            const icon = document.getElementById('fib-spin-icon');
            if (icon) icon.className = 'fa-solid fa-spinner fa-spin';
            try {
                const d = await fetchLevels(currentTfKey);
                applyStateToUI(currentTfKey, d);
                if (notify) showToast(`⚡ อัปเดตกรอบราคา ${currentTfKey.toUpperCase()} เรียบร้อย`);
            } catch (e) {
                console.error(e);
                if (notify) showToast('⚠️ ดึงข้อมูลราคาไม่สำเร็จ ลองใหม่อีกครั้ง');
            } finally {
                if (icon) icon.className = 'fa-solid fa-rotate';
            }
        }

        async function selectTimeframe(tfKey) {
            if (!timeframeMeta[tfKey]) return;
            currentTfKey = tfKey;
            document.querySelectorAll('.tf-btn').forEach(b => {
                b.className = 'tf-btn btn-interactive py-2 rounded-xl text-xs font-bold font-mono-num bg-slate-950 text-slate-400 border border-slate-800';
            });
            const ab = document.getElementById('btn-' + tfKey);
            if (ab) ab.className = 'tf-btn btn-interactive py-2 rounded-xl text-xs font-black font-mono-num bg-amber-500 text-slate-950 border border-amber-300 shadow';
            document.getElementById('active-tf-badge').innerText = 'TF: ' + tfKey.toUpperCase();
            loadTradingViewStudio(timeframeMeta[tfKey].tv);
            await refreshNow(false);
        }

        // ---------------- MANUAL OVERRIDE (sync ทั้งเว็บและ Telegram ผ่าน backend) ----------------
        async function applyCustomSwing() {
            const dir = document.getElementById('custom-dir').value;
            const high = parseFloat(document.getElementById('custom-high').value);
            const low = parseFloat(document.getElementById('custom-low').value);
            if (!high || !low || high <= low) { showToast('⚠️ กรุณาระบุ Swing High ให้มากกว่า Swing Low'); return; }
            const res = await fetch('/api/override', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tf: currentTfKey, direction: dir, high: high, low: low }) });
            if (res.ok) { await refreshNow(false); showToast('✅ ซิงก์ Swing ที่กำหนดเองแล้ว (เว็บ + Telegram ใช้ค่าเดียวกัน)'); }
            else showToast('⚠️ บันทึกค่าไม่สำเร็จ');
        }

        async function clearCustomSwing() {
            await fetch('/api/override', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tf: currentTfKey, clear: true }) });
            await refreshNow(false);
            showToast('↩️ กลับไปใช้ค่าอัตโนมัติจาก OANDA');
        }

        // ---------------- TRADINGVIEW + FULLSCREEN ----------------
        function loadTradingViewStudio(intervalCode) {
            if (currentTvLoadedInterval === intervalCode) return;
            currentTvLoadedInterval = intervalCode;
            document.getElementById('tradingview_advanced_chart').innerHTML = '';
            new TradingView.widget({
                autosize: true, symbol: 'OANDA:XAUUSD', interval: intervalCode, timezone: 'Asia/Bangkok',
                theme: 'dark', style: '1', locale: 'th', toolbar_bg: '#03060c', enable_publishing: false,
                hide_side_toolbar: false, allow_symbol_change: true, container_id: 'tradingview_advanced_chart'
            });
        }

        const chartWrap = () => document.getElementById('chart-wrapper');
        const isChartFs = () => document.fullscreenElement === chartWrap() || chartWrap().classList.contains('fs-fallback');

        function syncFsUi() {
            const ex = document.getElementById('fs-exit');
            if (isChartFs()) { ex.classList.remove('hidden'); ex.classList.add('flex'); }
            else { ex.classList.add('hidden'); ex.classList.remove('flex'); }
        }

        async function toggleChartFullscreen() {
            const el = chartWrap();
            if (isChartFs()) {
                if (document.fullscreenElement) { try { await document.exitFullscreen(); } catch (e) {} }
                el.classList.remove('fs-fallback'); document.body.style.overflow = '';
            } else if (el.requestFullscreen) {
                try { await el.requestFullscreen(); }
                catch (e) { el.classList.add('fs-fallback'); document.body.style.overflow = 'hidden'; }
            } else {
                el.classList.add('fs-fallback'); document.body.style.overflow = 'hidden';   // iOS Safari
            }
            syncFsUi();
        }
        document.addEventListener('fullscreenchange', syncFsUi);
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && chartWrap().classList.contains('fs-fallback')) toggleChartFullscreen();
        });

        // ---------------- LOGIN + TELEGRAM ----------------
        function checkAuthStatus() {
            const savedEmail = localStorage.getItem('gold_sniper_email');
            const savedChatId = localStorage.getItem('gold_sniper_chat_id');
            if (!savedEmail) document.getElementById('auth-modal').classList.remove('hidden');
            else { document.getElementById('user-email-badge').innerText = savedEmail.split('@')[0]; document.getElementById('login-email').value = savedEmail; }
            if (savedChatId) { document.getElementById('set-chat-id').value = savedChatId; document.getElementById('telegram-status-btn').innerText = 'เชื่อม Telegram แล้ว'; }
        }
        function openAuthModal() { document.getElementById('auth-modal').classList.remove('hidden'); }

        async function submitEmailLogin() {
            const email = document.getElementById('login-email').value.trim();
            if (!email || !email.includes('@')) { showToast('⚠️ กรุณากรอกอีเมลให้ถูกต้อง'); return; }
            if (!document.getElementById('login-disclaimer').checked) { showToast('⚠️ กรุณาติ๊กยอมรับข้อตกลง'); return; }
            localStorage.setItem('gold_sniper_email', email);
            document.getElementById('user-email-badge').innerText = email.split('@')[0];
            document.getElementById('auth-modal').classList.add('hidden');
            await fetch('/api/user-config', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email, chat_id: localStorage.getItem('gold_sniper_chat_id') || '' }) });
            showToast('✅ ยินดีต้อนรับเข้าสู่ GOLD AI SNIPER PRO');
        }

        function toggleSettingsModal() { document.getElementById('settings-modal').classList.toggle('hidden'); }

        async function autoDetectTelegramChatId() {
            showToast('🔍 กำลังค้นหา Chat ID ล่าสุดที่กด /start...');
            try {
                const res = await fetch('/api/telegram-detect-chat'); const data = await res.json();
                if (data.status === 'ok' && data.chat_id) {
                    document.getElementById('set-chat-id').value = data.chat_id;
                    localStorage.setItem('gold_sniper_chat_id', data.chat_id);
                    showToast(`✅ พบ Chat ID: ${data.chat_id} (${data.name})`);
                } else showToast('⚠️ ' + (data.message || 'ยังไม่พบข้อมูล กรุณากด /start ในบอทอีกครั้ง'));
            } catch (e) { showToast('⚠️ ไม่สามารถดึงข้อมูลได้'); }
        }

        async function saveUserSettings() {
            const email = localStorage.getItem('gold_sniper_email') || 'trader@gold.ai';
            const chatId = document.getElementById('set-chat-id').value.trim();
            const tf = document.getElementById('set-tf').value;
            localStorage.setItem('gold_sniper_chat_id', chatId);
            if (chatId) document.getElementById('telegram-status-btn').innerText = 'เชื่อม Telegram แล้ว';
            await fetch('/api/user-config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
                email: email, chat_id: chatId, preferred_tf: tf,
                start_time: document.getElementById('set-start-time').value, end_time: document.getElementById('set-end-time').value,
                alert_05: document.getElementById('set-alert-05').checked, alert_618: document.getElementById('set-alert-618').checked,
                briefing: document.getElementById('set-briefing').checked, briefing_time: document.getElementById('set-briefing-time').value
            }) });
            selectTimeframe(tf); toggleSettingsModal();
            showToast('✅ บันทึกการตั้งค่าและเปิดสแกนหลังบ้าน 24 ชม. เรียบร้อย!');
        }

        async function postJson(url, body) {
            const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            let data = {}; try { data = await res.json(); } catch (e) {}
            return { ok: res.ok, data };
        }

        async function sendTestTelegram() {
            const chatId = document.getElementById('set-chat-id').value.trim();
            if (!chatId) { showToast('⚠️ กรุณาใส่ Chat ID หรือกดดึงอัตโนมัติก่อน'); return; }
            const r = await postJson('/api/test-telegram', { chat_id: chatId });
            showToast(r.ok ? '🚀 ส่งข้อความทดสอบเข้า Telegram เรียบร้อย!' : '⚠️ ' + (r.data.message || 'ส่งไม่สำเร็จ'));
        }

        async function sendTestBriefing() {
            const chatId = document.getElementById('set-chat-id').value.trim();
            if (!chatId) { showToast('⚠️ กรุณาใส่ Chat ID ก่อน'); return; }
            const r = await postJson('/api/test-briefing', { chat_id: chatId, preferred_tf: document.getElementById('set-tf').value });
            showToast(r.ok ? '☀️ ส่ง Morning Briefing ทดสอบแล้ว' : '⚠️ ' + (r.data.message || 'ส่งไม่สำเร็จ'));
        }

        async function broadcastCurrentSignal() {
            const chatId = document.getElementById('set-chat-id').value.trim() || localStorage.getItem('gold_sniper_chat_id') || '';
            if (!chatId) { toggleSettingsModal(); showToast('⚠️ กรุณาเชื่อมต่อ Telegram Chat ID ก่อน'); return; }
            const r = await postJson('/api/send-signal', { chat_id: chatId, tf: currentTfKey });
            if (r.ok) { renderSignalFeed(r.data.signal_history); showToast('🚀 ส่งระดับราคาเข้า Telegram เรียบร้อย!'); }
            else showToast('⚠️ ' + (r.data.message || 'ส่งไม่สำเร็จ'));
        }

        // ---------------- PANELS ----------------
        function switchRightTab(tab) {
            document.getElementById('right-tab-feed').classList.toggle('hidden', tab !== 'feed');
            document.getElementById('right-tab-matrix').classList.toggle('hidden', tab !== 'matrix');
            const on = 'px-2.5 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950';
            const off = 'px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-950 text-slate-400 border border-slate-800';
            document.getElementById('tab-btn-feed').className = tab === 'feed' ? on : off;
            document.getElementById('tab-btn-matrix').className = tab === 'matrix' ? on : off;
        }

        function renderMatrixTable(activeKey) {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';
            Object.keys(timeframeMeta).forEach(key => {
                const st = liveTimeframeStore[key];
                if (!st) return;
                const row = document.createElement('div');
                row.className = `flex items-center justify-between p-2.5 rounded-xl border cursor-pointer ${key === activeKey ? 'bg-amber-500/15 border-amber-500/50' : 'bg-slate-950 border-slate-800'}`;
                row.onclick = () => selectTimeframe(key);
                const tag = st.blocked
                    ? '<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-300">SIDEWAY</span>'
                    : `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${st.direction === 'SELL' ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'}">${st.direction}</span>`;
                const nums = st.levels
                    ? `<span class="text-amber-300">0.5: ${money(st.levels.fib_05)}</span><span class="text-cyan-400 font-bold">61.8%: ${money(st.levels.entry)}</span>`
                    : '<span class="text-slate-500">ไม่มีสัญญาณ</span>';
                row.innerHTML = `<div class="flex items-center gap-2"><span class="font-black font-mono-num text-amber-400 w-10 uppercase">${key}</span>${tag}</div><div class="flex gap-2.5 text-[11px] font-mono-num">${nums}</div>`;
                list.appendChild(row);
            });
        }

        function renderSignalFeed(signals) {
            const container = document.getElementById('right-tab-feed');
            document.getElementById('feed-counter-label').innerText = `${signals.length} รายการ`;
            container.innerHTML = signals.length ? '' : '<div class="text-[11px] text-slate-500 text-center py-3">ยังไม่มีประวัติการส่ง</div>';
            signals.forEach(sig => {
                const isSell = sig.direction === 'SELL';
                const card = document.createElement('div');
                card.className = `p-3 rounded-xl bg-slate-950 border border-slate-800 border-l-4 ${isSell ? 'border-l-rose-500' : 'border-l-emerald-500'} space-y-1 text-xs`;
                card.innerHTML = `
                    <div class="flex justify-between items-center"><span class="font-bold text-white">${sig.symbol} • TF ${sig.tf} (${sig.direction})</span><span class="text-[10px] font-mono-num text-slate-400">${sig.date} ${sig.time}</span></div>
                    <div class="flex flex-wrap gap-2 font-mono-num text-[11px] pt-0.5">
                        <span class="text-amber-300">0.5: $${sig.fib_05}</span><span class="text-cyan-400 font-bold">61.8%: $${sig.entry}</span>
                        <span class="text-rose-400">SL: $${sig.sl}</span><span class="text-emerald-400">TP1: $${sig.tp1}</span>
                    </div>`;
                container.appendChild(card);
            });
        }

        async function loadSystemState() {
            try {
                const res = await fetch('/api/system-state'); const data = await res.json();
                isNewsLocked = data.news_locked;
                allCalendarEvents = data.economic_calendar || [];
                updateNewsShieldUI(isNewsLocked);
                renderCalendarTable(data.calendar_available);
                renderSignalFeed(data.signal_history);
                if (!data.telegram_configured && !tgWarned) { tgWarned = true; showToast('⚠️ ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN บน Render'); }
            } catch (e) {}
        }

        function filterNews(mode) { currentNewsFilter = mode; renderCalendarTable(true); }

        function renderCalendarTable(available) {
            const tbody = document.getElementById('economic-calendar-body');
            tbody.innerHTML = '';
            const filtered = allCalendarEvents.filter(item => {
                if (currentNewsFilter === 'TODAY') return item.urgency === 'TODAY' || item.urgency === 'NOW';
                if (currentNewsFilter === 'HIGH') return item.impact === 'HIGH';
                return true;
            });
            if (!filtered.length) {
                tbody.innerHTML = `<tr><td colspan="4" class="py-4 text-center text-slate-500">${available === false ? '⚠️ ดึงปฏิทิน Forex Factory ไม่ได้ชั่วคราว (ระบบจะลองใหม่อัตโนมัติ)' : 'ไม่มีรายการข่าวในหมวดนี้'}</td></tr>`;
                return;
            }
            filtered.forEach(item => {
                const badge = item.impact === 'HIGH'
                    ? '<span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 font-bold text-[10px]">🔴 ข่าวแดง</span>'
                    : '<span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold text-[10px]">🟠 ปานกลาง</span>';
                const tr = document.createElement('tr');
                const td1 = document.createElement('td'); td1.className = 'py-2 px-2 font-mono-num text-amber-300 whitespace-nowrap'; td1.textContent = `${item.date_label} ${item.time_label}`;
                const td2 = document.createElement('td'); td2.className = 'py-2 px-2 text-slate-200'; td2.textContent = item.event;
                const td3 = document.createElement('td'); td3.className = 'py-2 px-2 whitespace-nowrap'; td3.innerHTML = badge;
                const td4 = document.createElement('td'); td4.className = 'py-2 px-2 text-[11px] text-slate-400 whitespace-nowrap'; td4.textContent = item.countdown;
                tr.append(td1, td2, td3, td4); tbody.appendChild(tr);
            });
        }

        function updateNewsShieldUI(locked) {
            const box = document.getElementById('news-shield-box'), dot = document.getElementById('shield-dot'), text = document.getElementById('shield-status-text');
            if (locked) {
                box.className = 'bg-rose-950/60 border border-rose-500/60 px-3 py-1.5 rounded-xl flex items-center gap-2';
                dot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
                text.className = 'text-[11px] font-bold text-rose-400'; text.innerText = 'ล็อกช่วงข่าวแดง';
            } else {
                box.className = 'bg-emerald-950/40 border border-emerald-500/40 px-3 py-1.5 rounded-xl flex items-center gap-2';
                dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-ping';
                text.className = 'text-[11px] font-bold text-emerald-400'; text.innerText = 'ตลาดปกติ';
            }
        }

        async function toggleNewsLock() {
            const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
            const data = await res.json();
            isNewsLocked = data.news_locked; updateNewsShieldUI(isNewsLocked);
        }

        function copyPrice(elementId) {
            const text = document.getElementById(elementId).innerText.replace('$', '');
            if (!text || text === '--') return;
            navigator.clipboard.writeText(text);
            showToast(`✅ คัดลอกราคา $${text} แล้ว`);
        }

        function showToast(msg) {
            const toast = document.getElementById('toast-notify');
            document.getElementById('toast-notify-text').innerText = msg;
            toast.classList.remove('hidden');
            clearTimeout(window.__toastT);
            window.__toastT = setTimeout(() => toast.classList.add('hidden'), 3800);
        }

        async function loadAllTimeframes() {
            try {
                const res = await fetch('/api/levels-all'); const all = await res.json();
                Object.keys(all).forEach(k => { if (!all[k].error) liveTimeframeStore[k] = all[k]; });
                renderMatrixTable(currentTfKey);
            } catch (e) {}
        }

        window.addEventListener('DOMContentLoaded', async () => {
            checkAuthStatus();
            await selectTimeframe('5m');
            await loadSystemState();
            loadAllTimeframes();
            setInterval(() => refreshNow(false), 20000);
            setInterval(loadSystemState, 60000);
            setInterval(loadAllTimeframes, 90000);
        });
    </script>
</body>
</html>
"""


# ==============================================================================
# 9. API ENDPOINTS
# ==============================================================================
@app.route("/")
def index():
    return Response(HTML_TEMPLATE, mimetype="text/html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/api/levels", methods=["GET"])
def api_levels():
    try:
        return jsonify(get_levels(request.args.get("tf", "5m")))
    except Exception as e:
        print("api_levels:", type(e).__name__, e)
        return jsonify({"status": "error", "message": "ดึงข้อมูลราคาไม่สำเร็จ"}), 502


@app.route("/api/levels-all", methods=["GET"])
def api_levels_all():
    out = {}
    for tf in TF_CFG:
        try:
            out[tf] = get_levels(tf)
        except Exception as e:
            out[tf] = {"error": type(e).__name__}
    return jsonify(out)


@app.route("/api/override", methods=["POST"])
def api_override():
    data = request.json or {}
    tf = str(data.get("tf", "5m")).lower()
    if tf not in TF_CFG:
        return jsonify({"status": "error", "message": "timeframe ไม่ถูกต้อง"}), 400
    if data.get("clear"):
        OVERRIDES.pop(tf, None)
        return jsonify({"status": "ok"})
    try:
        high, low = float(data.get("high")), float(data.get("low"))
    except Exception:
        return jsonify({"status": "error", "message": "ค่า High/Low ไม่ถูกต้อง"}), 400
    direction = "BUY" if str(data.get("direction", "SELL")).upper() == "BUY" else "SELL"
    if high <= low:
        return jsonify({"status": "error", "message": "High ต้องมากกว่า Low"}), 400
    OVERRIDES[tf] = {"direction": direction, "high": round(high, 2), "low": round(low, 2)}
    return jsonify({"status": "ok"})


@app.route("/api/system-state", methods=["GET"])
def get_system_state():
    events = fetch_forex_factory_calendar()
    locked = is_news_locked(events)
    return jsonify({
        "news_locked": locked,
        "lock_reason": "ล็อกช่วงข่าวแดง" if locked else "ตลาดปกติ",
        "signal_history": STATE["signal_history"],
        "economic_calendar": events,
        "calendar_available": bool(FF_CACHE["events"]),
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
        "oanda_configured": bool(OANDA_API_KEY),
        "server_time": datetime.now(TH_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/user-config", methods=["POST"])
def save_user_config():
    data = request.json or {}
    email = str(data.get("email", "")).strip().lower()
    chat_id = str(data.get("chat_id", "")).strip()
    key = chat_id or email or "trader@gold.ai"

    user = USERS_DB.get(key) or (USERS_DB.get(email) if email else None) or default_user(chat_id, email)
    user["chat_id"] = chat_id or user.get("chat_id", "")
    if email:
        user["email"] = email
    if "preferred_tf" in data and str(data["preferred_tf"]).lower() in TF_CFG:
        user["preferred_tf"] = str(data["preferred_tf"]).lower()
    for f in ("start_time", "end_time", "briefing_time"):
        if f in data and data[f]:
            user[f] = str(data[f])
    for f in ("alert_05", "alert_618", "briefing"):
        if f in data:
            user[f] = bool(data[f])
    user["auto_alert"] = True

    if email and email != key:
        USERS_DB.pop(email, None)
    USERS_DB[key] = user
    save_users()
    return jsonify({"status": "ok"})


@app.route("/api/telegram-detect-chat", methods=["GET"])
def detect_telegram_chat():
    chat_id, first_name = fetch_latest_telegram_chat_id()
    if chat_id:
        return jsonify({"status": "ok", "chat_id": chat_id, "name": first_name})
    return jsonify({"status": "not_found", "message": "ยังไม่พบ Chat ID (ตรวจ Token และกด /start ในบอท)"}), 404


@app.route("/api/telegram-status", methods=["GET"])
def telegram_status():
    ok, res = tg_call("getMe")
    if not ok:
        return jsonify({"status": "error", "message": res}), 400
    chat_ok, chat_res = tg_call("getChat", {"chat_id": OWNER_CHAT_ID}) if OWNER_CHAT_ID else (False, "ไม่มี Chat ID")
    return jsonify({"status": "ok", "bot": res.get("username"), "owner_chat_ok": chat_ok,
                    "owner_chat_detail": chat_res if not chat_ok else "ok"})


@app.route("/api/test-telegram", methods=["POST"])
def test_telegram():
    chat_id = str((request.json or {}).get("chat_id", "")).strip()
    msg = ("✅ <b>เชื่อมต่อ GOLD AI SNIPER PRO สำเร็จ!</b>\n"
           "ระบบพร้อมส่งแจ้งเตือนอัตโนมัติเมื่อราคาทองคำแตะ <b>0.5 (เตรียมตัว)</b> และ <b>61.8% (Golden Zone)</b> "
           "เฉพาะช่วงที่ตลาดมีเทรนด์ชัดเจนเท่านั้น")
    ok, info = send_telegram_message(chat_id, msg)
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": info}), 400


@app.route("/api/test-briefing", methods=["POST"])
def test_briefing():
    data = request.json or {}
    chat_id = str(data.get("chat_id", "")).strip()
    user = default_user(chat_id)
    if str(data.get("preferred_tf", "")).lower() in TF_CFG:
        user["preferred_tf"] = str(data["preferred_tf"]).lower()
    ok, info = send_telegram_message(chat_id, build_morning_briefing(user, datetime.now(TH_TZ)))
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": info}), 400


@app.route("/api/toggle-news-lock", methods=["POST"])
def toggle_news_lock():
    STATE["manual_news_lock"] = not STATE["manual_news_lock"]
    locked = is_news_locked()
    return jsonify({"status": "ok", "news_locked": locked})


@app.route("/api/send-signal", methods=["POST"])
def send_signal():
    data = request.json or {}
    chat_id = str(data.get("chat_id", "")).strip()
    tf = str(data.get("tf", "5m")).lower()

    if is_news_locked():
        return jsonify({"status": "blocked", "message": "ระบบงดส่งชั่วคราว: อยู่ในช่วงข่าวแดง/ล็อกด้วยตนเอง"}), 403
    try:
        d = get_levels(tf)
    except Exception:
        return jsonify({"status": "error", "message": "ดึงข้อมูลราคาไม่สำเร็จ"}), 502
    if d["blocked"]:
        return jsonify({"status": "blocked", "message": "NO TRADE: ตลาด Sideway — งดส่งสัญญาณ"}), 403

    L = d["levels"]
    now_dt = datetime.now(TH_TZ)
    msg = (f"🔔 <b>XAUUSD ({tf.upper()}) • โครงสร้าง {d['direction']}</b>\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"🟡 <b>จุดเตรียมตัว (0.5):</b> ${L['fib_05']:.2f}\n"
           f"🔵 <b>Golden Zone (61.8%):</b> ${L['entry']:.2f}\n"
           f"🔴 <b>ระยะ 78.6% (SL):</b> ${L['sl']:.2f}\n"
           f"🟢 <b>TP1 (1:2):</b> ${L['tp1']:.2f}\n"
           f"🟡 <b>TP2 (1:3):</b> ${L['tp2']:.2f}\n"
           f"<i>แหล่งข้อมูล: {d['source']}</i>")
    ok, info = send_telegram_message(chat_id, msg)
    if not ok:
        return jsonify({"status": "error", "message": f"ส่งเข้า Telegram ไม่สำเร็จ: {info}"}), 400

    STATE["signal_history"].insert(0, {
        "id": len(STATE["signal_history"]) + 1,
        "date": format_thai_date(now_dt), "time": now_dt.strftime("%H:%M:%S"),
        "symbol": "XAUUSD", "tf": tf.upper(), "direction": d["direction"],
        "fib_05": f"{L['fib_05']:.2f}", "entry": f"{L['entry']:.2f}", "sl": f"{L['sl']:.2f}",
        "tp1": f"{L['tp1']:.2f}", "tp2": f"{L['tp2']:.2f}", "status": "TELEGRAM SENT",
    })
    del STATE["signal_history"][50:]
    return jsonify({"status": "success", "signal_history": STATE["signal_history"]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
