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

# เขตเวลาประเทศไทย (UTC+7)
TH_TZ = timezone(timedelta(hours=7))

# เกณฑ์ตัดสินตลาด Sideway (หากระยะ Swing High - Low ใน 100 แท่ง แคบกว่า $8.00)
SIDEWAY_THRESHOLD_DOLLAR = 8.00

# แคชตารางข่าว Forex Factory
FF_CACHE = {
    "last_fetched": 0,
    "events": []
}

# ฐานข้อมูลผู้ใช้ในหน่วยความจำ (รองรับ Multi-user / Default Chat ID ของคุณซี)
USERS_DB = {
    "default@gold.ai": {
        "email": "default@gold.ai",
        "chat_id": "8948986514",
        "preferred_tf": "5m",
        "start_time": "08:00",
        "end_time": "22:00",
        "alert_05": True,
        "alert_618": True,
        "alert_sideway": True,
        "alert_morning_news": True,
        "balance": 1000.0,
        "risk_pct": 1.5,
        "auto_alert": True
    }
}

# สถานะระบบส่วนกลางและหน่วยความจำป้องกันการส่งซ้ำ (Deduplication Memory)
SYSTEM_STATE = {
    "manual_news_lock": False,
    "lock_reason": "NORMAL MARKET REGIME",
    "latest_signal": None,
    "last_alert_memory": {},     # เก็บสถานะการแจ้งเตือนต่อสวิง {swing_key: {"sent_05": bool, "sent_618": bool, "sent_sideway": bool}}
    "morning_brief_memory": {},  # เก็บสถานะการส่งข่าวรายวัน {email_YYYY-MM-DD: bool}
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
            "rr": "1:3",
            "status": "DISPATCHED",
            "reason": "Technical retracement to 61.8% Golden Zone after touching 0.5 preparation level."
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
# 2. TELEGRAM BOT ENGINE & AUTO CHAT-ID DISCOVERY
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
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "GoldAISniperInstitutional/5.0"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if res_data.get("ok"):
                return True, "OK"
            return False, res_data.get("description", "Telegram API Error")
    except urllib.error.HTTPError as he:
        try:
            err_body = he.read().decode("utf-8")
            err_json = json.loads(err_body)
            return False, f"HTTP {he.code}: {err_json.get('description', err_body)}"
        except Exception:
            return False, f"HTTP Error {he.code}: {he.reason}"
    except Exception as e:
        return False, str(e)


def fetch_latest_telegram_chat_id():
    """ดึง Chat ID ล่าสุดจากคนที่เพิ่งกด /start หรือทักแชทบอท"""
    if not TELEGRAM_BOT_TOKEN:
        return None, None
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=25"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok") and data.get("result"):
                for item in reversed(data["result"]):
                    msg = (
                        item.get("message")
                        or item.get("edited_message")
                        or item.get("my_chat_member")
                        or item.get("channel_post")
                    )
                    if msg and "chat" in msg:
                        chat_id = str(msg["chat"]["id"])
                        first_name = msg["chat"].get("first_name") or msg["chat"].get("title") or "Trader"
                        return chat_id, first_name
    except Exception as e:
        print("Telegram getUpdates Error:", e)
    return None, None


# ==============================================================================
# 3. QUANTITATIVE FIBONACCI & SIDEWAY REGIME ENGINE
# ==============================================================================
def calculate_fib_levels(direction, swing_high, swing_low, balance=1000.0, risk_pct=1.5):
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

    risk_money = balance * (risk_pct / 100.0)
    loss_per_lot = max(0.50, risk) * 100.0
    rec_lot = max(0.01, round(risk_money / loss_per_lot, 2))

    return {
        "direction": direction,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "range": round(rng, 2),
        "is_sideway": is_sideway,
        "regime": "SIDEWAY" if is_sideway else "TRENDING",
        "fib_05": round(fib_05, 2),
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "risk": round(risk, 2),
        "reward1": round(risk * 2.0, 2),
        "reward2": round(risk * 3.0, 2),
        "recommended_lot": f"{rec_lot:.2f}"
    }


def fetch_server_gold_candles(tf_key="5m"):
    tf_map = {
        "1m": ("1m", 90),
        "5m": ("5m", 96),
        "15m": ("15m", 96),
        "1h": ("1h", 100),
        "4h": ("4h", 100),
        "daily": ("1d", 90)
    }
    b_tf, lookback = tf_map.get(tf_key.lower(), ("5m", 96))
    url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={b_tf}&limit={lookback}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=6) as resp:
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
    levels["tf"] = tf_key.upper()
    return levels


# ==============================================================================
# 4. FOREX FACTORY ECONOMIC CALENDAR & MORNING BRIEFING FORMATTER
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
            countdown = f"อีก {days} วัน ({format_thai_date(event_dt)})"
            urgency = "FUTURE"

    return countdown, urgency, is_auto_locking_now


def get_fallback_forex_factory_schedule(now_dt):
    base_date = now_dt.date()
    monday = base_date + timedelta(days=1) if now_dt.weekday() == 6 else base_date - timedelta(days=now_dt.weekday())

    template_events = [
        (0, 21, 0, "USD", "CB Consumer Confidence (ความเชื่อมั่นผู้บริโภค)", "MEDIUM", "99.5", "98.7"),
        (1, 19, 30, "USD", "Prelim GDP q/q (ผลิตภัณฑ์มวลรวมสหรัฐฯ)", "HIGH", "2.9%", "3.0%"),
        (1, 21, 0, "USD", "JOLTS Job Openings (ตำแหน่งงานว่างเปิดใหม่)", "HIGH", "7.92M", "8.04M"),
        (2, 19, 15, "USD", "ADP Non-Farm Employment Change", "HIGH", "115K", "143K"),
        (2, 19, 30, "USD", "Core PCE / CPI Price Index m/m (ดัชนีเงินเฟ้อ)", "HIGH", "0.3%", "0.2%"),
        (3, 19, 30, "USD", "Initial Jobless Claims (ผู้ขอรับสวัสดิการว่างงาน)", "HIGH", "222K", "227K"),
        (3, 20, 45, "USD", "Chicago PMI (ดัชนีผู้จัดการฝ่ายจัดซื้อ)", "MEDIUM", "47.1", "46.6"),
        (4, 19, 30, "USD", "Non-Farm Employment Change (NFP)", "HIGH", "148K", "254K"),
        (4, 21, 0, "USD", "ISM Manufacturing PMI (ดัชนีภาคการผลิต)", "HIGH", "47.6", "47.2"),
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
            "lock_window": f"{lock_start} - {lock_end} น.",
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
                "lock_window": f"{lock_start} - {lock_end} น.",
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


def build_morning_news_brief_message(now_dt, calendar_events, start_t, end_t):
    today_iso = now_dt.strftime("%Y-%m-%d")
    today_high = [ev for ev in calendar_events if ev.get("iso_date") == today_iso and ev.get("impact") == "HIGH"]
    today_med = [ev for ev in calendar_events if ev.get("iso_date") == today_iso and ev.get("impact") == "MEDIUM"]

    lines = [
        f"🌅 <b>GOLD AI SNIPER PRO — MORNING BRIEFING</b>",
        f"📅 <b>ประจำวัน:</b> {format_thai_date(now_dt)}",
        f"⏰ <b>รอบเวลาสแกนของคุณ:</b> {start_t} – {end_t} น.",
        f"━━━━━━━━━━━━━━━━━━━━━━"
    ]

    if today_high:
        lines.append("🔴 <b>ข่าวแดง (HIGH IMPACT USD) ที่ต้องระวังวันนี้:</b>")
        for ev in today_high:
            lines.append(f"• <b>{ev['time_label']}</b> — {ev['event']}")
            lines.append(f"  └ 🛡️ <i>ล็อกสัญญาณอัตโนมัติ: {ev['lock_window']} (คาดการณ์: {ev['forecast']})</i>")
    else:
        lines.append("🟢 <b>ข่าวแดง (HIGH IMPACT USD):</b>")
        lines.append("• วันนี้ไม่มีตารางประกาศข่าวแดงสหรัฐฯ ตลาดเคลื่อนไหวตามโครงสร้างเทคนิคปกติ")

    if today_med:
        lines.append("")
        lines.append("🟠 <b>ข่าวส้ม (MEDIUM IMPACT) เพิ่มเติม:</b>")
        for ev in today_med[:4]:
            lines.append(f"• {ev['time_label']} — {ev['event']}")

    lines.extend([
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"📐 <b>ระบบเฝ้าระวังอัตโนมัติทำงานอยู่:</b>",
        f"1. แจ้งเตือนเมื่อตลาดเข้าโหมด <b>Sideway (&lt; ${SIDEWAY_THRESHOLD_DOLLAR:.2f})</b>",
        f"2. แจ้งเตือนล่วงหน้าที่ระดับ <b>Fibonacci 0.5 (50.0%)</b>",
        f"3. แจ้งเตือนเมื่อราคาเข้าโซน <b>Golden Zone 61.8%</b>"
    ])
    return "\n".join(lines)


# ==============================================================================
# 5. 24/7 AUTONOMOUS BACKGROUND SCANNER THREAD
# ==============================================================================
def is_within_schedule(now_dt, start_str, end_str):
    try:
        cur_mins = now_dt.hour * 60 + now_dt.minute
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        if start_mins <= end_mins:
            return start_mins <= cur_mins <= end_mins
        return cur_mins >= start_mins or cur_mins <= end_mins
    except Exception:
        return True


def background_price_scanner():
    """รันหลังบ้านตลอด 24 ชม. ตรวจจับข่าวเช้า, ตลาด Sideway, และระดับ Fibonacci 0.5 / 61.8%"""
    while True:
        try:
            now_dt = datetime.now(TH_TZ)
            SYSTEM_STATE["scanner_last_run"] = now_dt.strftime("%H:%M:%S")
            calendar_events = fetch_forex_factory_calendar()
            auto_locking = any(ev.get("is_locking_now") for ev in calendar_events)
            is_locked = SYSTEM_STATE["manual_news_lock"] or auto_locking

            if USERS_DB:
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

                today_str = now_dt.strftime("%Y-%m-%d")

                for email, user in list(USERS_DB.items()):
                    chat_id = user.get("chat_id")
                    if not chat_id or not user.get("auto_alert", True):
                        continue

                    start_t = user.get("start_time", "08:00")
                    end_t = user.get("end_time", "22:00")

                    if not is_within_schedule(now_dt, start_t, end_t):
                        continue

                    # ----------------------------------------------------------
                    # FEATURE B: ส่งสรุปข่าวเช้าอัตโนมัติ (แจ้งเตือนแรกของวันเมื่อเข้าช่วงเวลา)
                    # ----------------------------------------------------------
                    brief_key = f"{chat_id}_{today_str}"
                    if user.get("alert_morning_news", True) and not SYSTEM_STATE["morning_brief_memory"].get(brief_key):
                        morning_msg = build_morning_news_brief_message(now_dt, calendar_events, start_t, end_t)
                        ok, _ = send_telegram_message(chat_id, morning_msg)
                        if ok:
                            SYSTEM_STATE["morning_brief_memory"][brief_key] = True

                    if is_locked:
                        continue

                    tf = user.get("preferred_tf", "5m").lower()
                    data = tf_data_cache.get(tf)
                    if not data:
                        continue

                    price = data["current_price"]
                    fib_05 = data["fib_05"]
                    entry_618 = data["entry"]
                    direction = data["direction"]
                    rng = data["range"]
                    tolerance = max(0.45, rng * 0.035)

                    swing_key = f"{chat_id}_{tf}_{data['swing_high']}_{data['swing_low']}"
                    mem = SYSTEM_STATE["last_alert_memory"].get(swing_key, {})

                    # ----------------------------------------------------------
                    # FEATURE A: ตรวจจับตลาด SIDEWAY (< $8.00)
                    # ----------------------------------------------------------
                    if data["is_sideway"]:
                        if user.get("alert_sideway", True) and not mem.get("sent_sideway"):
                            side_msg = (
                                f"⚠️ <b>[SIDEWAY REGIME DETECTED] ตลาดไร้ทิศทาง</b>\n"
                                f"📊 <b>XAUUSD ({tf.upper()})</b> • กรอบสวิงแคบเพียง <b>${rng:.2f}</b> (&lt; ${SIDEWAY_THRESHOLD_DOLLAR:.2f})\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"⬆️ <b>Swing High:</b> ${data['swing_high']:.2f}\n"
                                f"⬇️ <b>Swing Low:</b> ${data['swing_low']:.2f}\n"
                                f"🛡️ <b>คำแนะนำทางสถิติ:</b> ราคากำลังบีบอัดออกข้าง (Low Volatility) ควรชะลอการเทรดหรือลดขนาด Lot ลง 50% เพื่อป้องกันการโดนกวาด Stop Loss"
                            )
                            ok, _ = send_telegram_message(chat_id, side_msg)
                            if ok:
                                mem["sent_sideway"] = True
                                SYSTEM_STATE["last_alert_memory"][swing_key] = mem
                        # เมื่อตลาดเป็น Sideway จะระงับการส่งสัญญาณ Fibo ชั่วคราวเพื่อความปลอดภัยสูงสุด
                        continue

                    # ----------------------------------------------------------
                    # FEATURE C (STAGE 1): แจ้งเตือนล่วงหน้าที่ระดับ 0.5 (50.0%)
                    # ----------------------------------------------------------
                    if user.get("alert_05", True) and not mem.get("sent_05"):
                        if abs(price - fib_05) <= tolerance:
                            msg_05 = (
                                f"🔔 <b>[STAGE 1: PREPARE] ราคาแตะระดับ 0.5 (50.0%)</b>\n"
                                f"📊 <b>XAUUSD ({tf.upper()})</b> • โครงสร้างฝั่ง <b>{direction}</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🟡 <b>ราคาปัจจุบัน:</b> ${price:.2f}\n"
                                f"🔔 <b>จุดเตรียมตัว 0.5:</b> ${fib_05:.2f}\n"
                                f"🔵 <b>โซนหลัก 61.8% ถัดไป:</b> ${entry_618:.2f}\n"
                                f"🔴 <b>ระดับอ้างอิง 78.6%:</b> ${data['sl']:.2f}\n"
                                f"🟢 <b>เป้าสถิติ TP1 / TP2:</b> ${data['tp1']:.2f} / ${data['tp2']:.2f}"
                            )
                            ok, _ = send_telegram_message(chat_id, msg_05)
                            if ok:
                                mem["sent_05"] = True
                                SYSTEM_STATE["last_alert_memory"][swing_key] = mem

                    # ----------------------------------------------------------
                    # FEATURE C (STAGE 2): แจ้งเตือนเมื่อเข้า GOLDEN ZONE 61.8%
                    # ----------------------------------------------------------
                    if user.get("alert_618", True) and not mem.get("sent_618"):
                        if abs(price - entry_618) <= tolerance:
                            calc_user = calculate_fib_levels(
                                direction,
                                data["swing_high"],
                                data["swing_low"],
                                user.get("balance", 1000.0),
                                user.get("risk_pct", 1.5)
                            )
                            msg_618 = (
                                f"🎯 <b>[STAGE 2: GOLDEN ZONE] ราคาเข้าโซน 61.8%</b>\n"
                                f"📊 <b>XAUUSD ({tf.upper()})</b> • โครงสร้างฝั่ง <b>{direction}</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🔵 <b>Golden Zone (61.8%):</b> ${entry_618:.2f}\n"
                                f"🔴 <b>Invalidation (78.6%):</b> ${data['sl']:.2f} (ระยะ ${data['risk']:.2f})\n"
                                f"🟢 <b>Target 1 (RR 1:2):</b> ${data['tp1']:.2f}\n"
                                f"🟡 <b>Target 2 (RR 1:3):</b> ${data['tp2']:.2f}\n"
                                f"⚖️ <b>ขนาด Lot คำนวณตามความเสี่ยง:</b> {calc_user['recommended_lot']} Lot"
                            )
                            ok, _ = send_telegram_message(chat_id, msg_618)
                            if ok:
                                mem["sent_618"] = True
                                SYSTEM_STATE["last_alert_memory"][swing_key] = mem
                                SYSTEM_STATE["signal_history"].insert(0, {
                                    "id": len(SYSTEM_STATE["signal_history"]) + 101,
                                    "date": format_thai_date(now_dt),
                                    "time": now_dt.strftime("%H:%M:%S"),
                                    "symbol": "XAUUSD",
                                    "tf": tf.upper(),
                                    "direction": direction,
                                    "regime": "TRENDING",
                                    "range": f"{rng:.2f}",
                                    "fib_05": f"{fib_05:.2f}",
                                    "entry": f"{entry_618:.2f}",
                                    "sl": f"{data['sl']:.2f}",
                                    "tp1": f"{data['tp1']:.2f}",
                                    "tp2": f"{data['tp2']:.2f}",
                                    "rr": "1:3",
                                    "status": "AUTO 61.8% SENT",
                                    "reason": f"Auto-Scanner triggered at 61.8% Golden Zone (${entry_618:.2f})"
                                })

        except Exception as e:
            print("Background Scanner Error:", e)
        time.sleep(25)


scanner_thread = threading.Thread(target=background_price_scanner, daemon=True)
scanner_thread.start()


# ==============================================================================
# 6. 5-STAR INSTITUTIONAL TERMINAL FRONTEND (OBSIDIAN PRECISION UI)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — Institutional XAUUSD Fibonacci & Regime Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Prompt:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-canvas: #06080E;
            --bg-surface: #0B0F17;
            --bg-elevated: #111726;
            --border-hairline: rgba(255, 255, 255, 0.07);
            --border-focus: rgba(212, 175, 55, 0.45);
            --gold-accent: #D4AF37;
            --amber-warn: #F59E0B;
            --emerald-bull: #10B981;
            --crimson-bear: #F43F5E;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Inter', 'Prompt', sans-serif;
            background-color: var(--bg-canvas);
            background-image: 
                radial-gradient(circle at 15% 0%, rgba(212, 175, 55, 0.05), transparent 40%),
                radial-gradient(circle at 85% 0%, rgba(16, 185, 129, 0.04), transparent 40%);
            color: #E2E8F0;
            overflow-x: hidden;
            margin: 0;
        }
        .font-mono-num {
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.02em;
        }
        .inst-panel {
            background-color: var(--bg-surface);
            border: 1px solid var(--border-hairline);
            box-shadow: 0 12px 32px -12px rgba(0, 0, 0, 0.85);
        }
        .inst-panel-gold {
            background: linear-gradient(180deg, rgba(17, 23, 38, 0.9) 0%, rgba(11, 15, 23, 0.98) 100%);
            border: 1px solid rgba(212, 175, 55, 0.28);
            box-shadow: 0 14px 36px -12px rgba(0, 0, 0, 0.9);
        }
        .inst-card-interactive {
            background-color: var(--bg-elevated);
            border: 1px solid var(--border-hairline);
            transition: all 0.16s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .inst-card-interactive:hover {
            border-color: rgba(255, 255, 255, 0.2);
            transform: translateY(-1px);
        }
        .inst-card-interactive:active {
            transform: translateY(0px) scale(0.99);
        }
        .inst-btn {
            transition: all 0.15s ease;
        }
        .inst-btn:hover:not(:disabled) {
            filter: brightness(1.08);
            transform: translateY(-1px);
        }
        .inst-btn:active:not(:disabled) {
            transform: translateY(0px) scale(0.98);
        }
        .status-dot {
            width: 7px;
            height: 7px;
            border-radius: 9999px;
            display: inline-block;
        }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: #06080E; }
        ::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #D4AF37; }
    </style>
</head>
<body class="antialiased min-h-screen flex flex-col justify-between selection:bg-amber-500 selection:text-slate-950">

    <!-- ==================================================================== -->
    <!-- MODAL 1: INSTITUTIONAL ACCESS & LEGAL DISCLAIMER                     -->
    <!-- ==================================================================== -->
    <div id="auth-modal" class="fixed inset-0 bg-black/85 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="inst-panel-gold rounded-xl max-w-md w-full p-6 space-y-5">
            <div class="flex items-center justify-between border-b border-white/10 pb-4">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-lg bg-amber-500/15 border border-amber-500/40 flex items-center justify-center text-amber-400 font-mono-num font-extrabold text-sm">
                        XAU
                    </div>
                    <div>
                        <h2 class="text-sm font-bold tracking-wide text-white uppercase">GOLD AI SNIPER PRO</h2>
                        <p class="text-[11px] text-slate-400">Institutional Fibonacci & Market Regime Terminal</p>
                    </div>
                </div>
                <span class="px-2 py-0.5 text-[10px] font-mono-num font-semibold bg-white/5 text-slate-300 rounded border border-white/10">v5.0 PRO</span>
            </div>

            <div class="space-y-4 text-xs">
                <div>
                    <label class="text-slate-300 font-semibold block mb-1.5">อีเมลผู้ใช้งาน (Institutional / Personal Email)</label>
                    <input type="email" id="login-email" placeholder="name@domain.com" class="w-full bg-[#06080E] border border-white/15 focus:border-amber-400 rounded-lg px-3.5 py-2.5 text-white outline-none font-mono-num text-xs">
                </div>

                <div class="bg-[#06080E] p-3.5 rounded-lg border border-white/10 space-y-2 text-[11px] text-slate-300 leading-relaxed">
                    <div class="font-bold text-amber-400 flex items-center gap-1.5 uppercase tracking-wider text-[10px]">
                        <i class="fa-solid fa-shield-halved"></i> ข้อตกลงการใช้งานเครื่องมือคำนวณทางสถิติ (Legal Disclaimer)
                    </div>
                    <p class="text-slate-400">
                        แพลตฟอร์มนี้เป็น <strong>เครื่องมือคำนวณระดับราคาทางคณิตศาสตร์ (Fibonacci Retracement) และตรวจจับความผันผวนทางสถิติอัตโนมัติเท่านั้น</strong> ไม่ใช่การให้คำแนะนำทางการเงินหรือการชักชวนลงทุน (Not Financial Advice) ผู้ใช้งานเป็นผู้รับผิดชอบการตัดสินใจด้วยตนเอง 100%
                    </p>
                    <label class="flex items-start gap-2.5 pt-1.5 cursor-pointer select-none text-slate-100 font-medium">
                        <input type="checkbox" id="login-disclaimer" class="mt-0.5 rounded accent-amber-500 w-3.5 h-3.5">
                        <span>ฉันรับทราบและยอมรับข้อตกลงการใช้งานเครื่องมือคำนวณทางเทคนิค</span>
                    </label>
                </div>
            </div>

            <button onclick="submitEmailLogin()" class="inst-btn w-full py-2.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs tracking-wide uppercase">
                เข้าสู่ระบบเทอร์มินัล (Initialize Terminal)
            </button>
        </div>
    </div>

    <!-- ==================================================================== -->
    <!-- MODAL 2: TELEGRAM 24/7 DISPATCH & MORNING BRIEF CONFIGURATION        -->
    <!-- ==================================================================== -->
    <div id="settings-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="inst-panel rounded-xl max-w-xl w-full p-6 space-y-5 max-h-[92vh] overflow-y-auto">
            <div class="flex justify-between items-center border-b border-white/10 pb-3.5">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-lg bg-sky-500/15 border border-sky-500/30 flex items-center justify-center text-sky-400 text-base">
                        <i class="fa-brands fa-telegram"></i>
                    </div>
                    <div>
                        <h3 class="text-sm font-bold text-white uppercase tracking-wide">Telegram 24/7 Autonomous Dispatch</h3>
                        <p class="text-[11px] text-slate-400">ตั้งค่าการส่งสรุปข่าวเช้า, เตือนตลาด Sideway และจุด Fibonacci เข้ามือถือ</p>
                    </div>
                </div>
                <button onclick="toggleSettingsModal()" class="text-slate-400 hover:text-white text-sm px-2 py-1 rounded hover:bg-white/5">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>

            <!-- STEP 1: BOT CONNECTION -->
            <div class="bg-[#06080E] p-4 rounded-lg border border-white/10 space-y-2.5 text-xs">
                <div class="flex items-center justify-between">
                    <span class="font-bold text-amber-400 uppercase tracking-wider text-[10px]">STEP 1 • เชื่อมต่อบอท @gold_ai_sniper_pro_bot</span>
                    <span class="text-[10px] font-mono-num text-emerald-400">BOT ONLINE</span>
                </div>
                <p class="text-slate-400 text-[11px]">กดเปิดบอทในแอป Telegram แล้วพิมพ์ <code class="text-white bg-white/10 px-1.5 py-0.5 rounded">/start</code> 1 ครั้ง จากนั้นกดปุ่มดึงเลข Chat ID อัตโนมัติ</p>
                <div class="flex flex-wrap gap-2 pt-1">
                    <a href="https://t.me/gold_ai_sniper_pro_bot" target="_blank" class="inst-btn px-3 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs inline-flex items-center gap-1.5">
                        <i class="fa-brands fa-telegram"></i> 1. เปิดบอทใน Telegram
                    </a>
                    <button onclick="autoDetectTelegramChatId()" class="inst-btn px-3 py-2 rounded-lg bg-amber-500/15 border border-amber-500/40 text-amber-300 font-semibold text-xs inline-flex items-center gap-1.5">
                        <i class="fa-solid fa-wand-magic-sparkles"></i> 2. ดึงเลข Chat ID อัตโนมัติ
                    </button>
                </div>
            </div>

            <!-- STEP 2: CHAT ID & SCHEDULE -->
            <div class="space-y-3.5 text-xs">
                <div>
                    <label class="text-slate-300 font-semibold block mb-1">Telegram Chat ID ของคุณ</label>
                    <div class="flex flex-wrap sm:flex-nowrap gap-2">
                        <input type="text" id="set-chat-id" value="8948986514" placeholder="เช่น 8948986514" class="w-full bg-[#06080E] border border-white/15 focus:border-amber-400 rounded-lg px-3 py-2 text-white font-mono-num text-xs outline-none">
                        <button onclick="sendTestTelegram()" class="inst-btn px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-200 border border-white/15 font-semibold shrink-0">
                            <i class="fa-regular fa-paper-plane mr-1 text-sky-400"></i> ทดสอบส่งข้อความ
                        </button>
                        <button onclick="sendMorningBriefNow()" class="inst-btn px-3 py-2 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 font-semibold shrink-0">
                            <i class="fa-solid fa-sun mr-1"></i> ส่งสรุปข่าวเช้าเดี๋ยวนี้
                        </button>
                    </div>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">Timeframe หลักที่ให้บอทเฝ้า</label>
                        <select id="set-tf" class="w-full bg-[#06080E] border border-white/15 rounded-lg p-2 text-white font-mono-num font-semibold text-xs">
                            <option value="1m">1M (Scalping)</option>
                            <option value="5m" selected>5M (Sniper Default)</option>
                            <option value="15m">15M (Intraday)</option>
                            <option value="1h">1H (Swing)</option>
                            <option value="4h">4H (Position)</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">เวลาเริ่ม (ส่งสรุปข่าวเช้าทันที)</label>
                        <input type="time" id="set-start-time" value="08:00" class="w-full bg-[#06080E] border border-white/15 rounded-lg p-2 text-white font-mono-num text-xs">
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">เวลาหยุดแจ้งเตือนของวัน</label>
                        <input type="time" id="set-end-time" value="22:00" class="w-full bg-[#06080E] border border-white/15 rounded-lg p-2 text-white font-mono-num text-xs">
                    </div>
                </div>

                <!-- STEP 3: ALERT TRIGGERS -->
                <div class="bg-[#06080E] p-3.5 rounded-lg border border-white/10 space-y-2">
                    <div class="font-bold text-slate-300 text-[10px] uppercase tracking-wider">เงื่อนไขการยิงแจ้งเตือนอัตโนมัติ (24/7 Background Rules)</div>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-morning" checked class="accent-amber-500 w-3.5 h-3.5">
                        <span>🌅 <strong>Morning News Briefing:</strong> ส่งสรุปตารางข่าวแดงของวันทันทีเมื่อถึงเวลาเริ่ม (เช่น 08:00 น.)</span>
                    </label>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-sideway" checked class="accent-amber-500 w-3.5 h-3.5">
                        <span>⚠️ <strong>Sideway Regime Warning:</strong> เตือนทันทีเมื่อกรอบสวิงแคบกว่า $8.00 (ตลาดออกข้างไร้ทิศทาง)</span>
                    </label>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-05" checked class="accent-amber-500 w-3.5 h-3.5">
                        <span>🔔 <strong>Stage 1 — Early Warning (0.5):</strong> เตือนล่วงหน้าเมื่อราคาแตะ Fibonacci 50.0% เพื่อเตรียมตัว</span>
                    </label>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-618" checked class="accent-amber-500 w-3.5 h-3.5">
                        <span>🎯 <strong>Stage 2 — Golden Zone (61.8%):</strong> เตือนเมื่อราคาเข้าโซน 61.8% พร้อม SL 78.6% และขนาด Lot</span>
                    </label>
                </div>
            </div>

            <div class="flex justify-end gap-2 pt-2 border-t border-white/10">
                <button onclick="toggleSettingsModal()" class="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold">ปิดหน้าต่าง</button>
                <button onclick="saveUserSettings()" class="inst-btn px-5 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs">
                    บันทึกและเปิดสแกน 24 ชม.
                </button>
            </div>
        </div>
    </div>

    <!-- ==================================================================== -->
    <!-- TOP INSTITUTIONAL COMMAND BAR                                        -->
    <!-- ==================================================================== -->
    <header class="inst-panel border-b border-white/10 px-4 py-2.5 sticky top-0 z-30 backdrop-blur-md bg-[#0B0F17]/95">
        <div class="max-w-[1760px] mx-auto flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3">
            
            <!-- Brand & System Telemetry -->
            <div class="flex flex-wrap items-center gap-3">
                <div class="flex items-center gap-2.5">
                    <div class="w-8 h-8 rounded bg-amber-500 flex items-center justify-center text-slate-950 font-mono-num font-black text-xs tracking-tighter">
                        XAU
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-extrabold tracking-tight text-white">GOLD AI SNIPER</span>
                            <span class="text-[10px] font-mono-num font-bold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">TERMINAL</span>
                        </div>
                        <span class="block text-[10px] text-slate-400">Quantitative Fibonacci & Market Regime Engine</span>
                    </div>
                </div>

                <div class="h-5 w-[1px] bg-white/10 hidden sm:block"></div>

                <!-- Market Regime Pill (Trending vs Sideway) -->
                <div id="top-regime-pill" class="px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-xs">
                    <span id="top-regime-dot" class="status-dot bg-emerald-400"></span>
                    <span id="top-regime-text" class="font-mono-num font-bold text-emerald-400 text-[11px]">REGIME: TRENDING</span>
                </div>

                <!-- Forex Factory Shield Pill -->
                <div id="news-shield-box" class="px-2.5 py-1 rounded bg-white/5 border border-white/10 flex items-center gap-2 text-xs">
                    <span id="shield-dot" class="status-dot bg-emerald-400"></span>
                    <span id="shield-status-text" class="text-[11px] font-medium text-slate-300">News Shield: Standby</span>
                    <button onclick="toggleNewsLock()" class="text-[10px] font-mono-num px-1.5 py-0.5 rounded bg-white/5 hover:bg-white/10 text-slate-400 border border-white/10">Test Lock</button>
                </div>
            </div>

            <!-- Right Telemetry: Live Spot, Telegram & Profile -->
            <div class="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-between lg:justify-end">
                <!-- Live XAUUSD Price -->
                <div class="bg-[#06080E] px-3 py-1 rounded border border-white/10 flex items-center gap-3">
                    <div>
                        <span class="text-[9px] font-mono-num uppercase text-slate-400 block">XAUUSD SPOT</span>
                        <span id="live-ticker-price" class="font-mono-num text-sm font-extrabold text-white">--</span>
                    </div>
                    <span id="proximity-pill" class="px-2 py-0.5 text-[10px] font-mono-num font-semibold rounded bg-white/5 text-slate-300 border border-white/10">SCANNING</span>
                </div>

                <!-- Telegram Configuration Button -->
                <button onclick="toggleSettingsModal()" class="inst-btn px-3 py-1.5 rounded bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 text-sky-300 text-xs font-semibold flex items-center gap-1.5">
                    <i class="fa-brands fa-telegram"></i>
                    <span id="telegram-status-btn">Telegram Bot</span>
                </button>

                <!-- User Profile Button -->
                <button onclick="openAuthModal()" class="inst-btn px-3 py-1.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-mono-num text-slate-300 flex items-center gap-1.5">
                    <i class="fa-regular fa-user text-amber-400"></i>
                    <span id="user-email-badge">Trader</span>
                </button>
            </div>
        </div>
    </header>

    <!-- ==================================================================== -->
    <!-- MAIN WORKSPACE BENTO GRID (12 COLUMNS)                               -->
    <!-- ==================================================================== -->
    <main class="max-w-[1760px] w-full mx-auto p-3 md:p-5 flex-1">
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">

            <!-- ============================================================ -->
            <!-- LEFT WORKSPACE (7 COLUMNS): CHART + FOREX FACTORY CALENDAR   -->
            <!-- ============================================================ -->
            <div class="xl:col-span-7 space-y-4">

                <!-- 1. TRADINGVIEW PRO CHART PANEL -->
                <section class="inst-panel rounded-xl p-3.5 space-y-3">
                    <div class="flex flex-wrap justify-between items-center gap-2 border-b border-white/10 pb-2.5">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-bold text-white uppercase tracking-wider">OANDA:XAUUSD • Real-Time Feed</span>
                            <span id="chart-tf-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">TF 5M</span>
                            <span id="chart-range-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num text-slate-400 bg-white/5">Swing Range: --</span>
                        </div>
                        <div class="flex items-center gap-2">
                            <button onclick="triggerAutoFibonacciCalculation(true)" class="inst-btn py-1 px-3 rounded bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold flex items-center gap-1.5">
                                <i id="fib-spin-icon" class="fa-solid fa-rotate text-[11px]"></i> Recalculate Fib
                            </button>
                        </div>
                    </div>

                    <div class="tradingview-widget-container rounded-lg overflow-hidden border border-white/10" style="height:510px; width:100%;">
                        <div id="tradingview_advanced_chart" style="height:100%; width:100%;"></div>
                    </div>
                </section>

                <!-- 2. FOREX FACTORY LIVE CALENDAR & MORNING BRIEFING PANEL -->
                <section class="inst-panel rounded-xl p-4 space-y-3">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2.5 border-b border-white/10 pb-3">
                        <div>
                            <div class="flex items-center gap-2">
                                <h2 class="text-xs font-bold text-white uppercase tracking-wider">Forex Factory Economic Calendar (UTC+7)</h2>
                                <span class="px-1.5 py-0.5 text-[9px] font-mono-num font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 rounded">AUTO-SHIELD ±30M</span>
                            </div>
                            <p class="text-[11px] text-slate-400 mt-0.5">สรุปตารางข่าวเศรษฐกิจสหรัฐฯ พร้อมส่งแจ้งเตือนเข้า Telegram อัตโนมัติทุกเช้าเมื่อเริ่มวัน</p>
                        </div>

                        <div class="flex flex-wrap items-center gap-1.5">
                            <button onclick="filterNews('ALL')" id="news-filter-ALL" class="px-2.5 py-1 rounded text-[11px] font-semibold bg-amber-500 text-slate-950">ทั้งสัปดาห์</button>
                            <button onclick="filterNews('TODAY')" id="news-filter-TODAY" class="px-2.5 py-1 rounded text-[11px] font-semibold bg-white/5 text-slate-300 border border-white/10">เฉพาะวันนี้</button>
                            <button onclick="filterNews('HIGH')" id="news-filter-HIGH" class="px-2.5 py-1 rounded text-[11px] font-semibold bg-white/5 text-rose-400 border border-white/10">เฉพาะข่าวแดง</button>
                            <button onclick="sendMorningBriefNow()" class="inst-btn px-2.5 py-1 rounded text-[11px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30">
                                <i class="fa-brands fa-telegram mr-1"></i>ส่งสรุปข่าววันนี้เข้า Telegram
                            </button>
                        </div>
                    </div>

                    <div class="overflow-x-auto max-h-[260px]">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-white/10 text-[10px] font-mono-num uppercase">
                                    <th class="py-2 px-2">วัน / เวลา (ไทย)</th>
                                    <th class="py-2 px-2">ตัวเลขเศรษฐกิจ (USD)</th>
                                    <th class="py-2 px-2">ระดับความแรง</th>
                                    <th class="py-2 px-2">คาดการณ์ / ก่อนหน้า</th>
                                    <th class="py-2 px-2">สถานะเวลา</th>
                                    <th class="py-2 px-2 text-right">เกราะป้องกันพอร์ต</th>
                                </tr>
                            </thead>
                            <tbody id="economic-calendar-body" class="divide-y divide-white/5 font-mono-num text-[11px]"></tbody>
                        </table>
                    </div>
                </section>
            </div>

            <!-- ============================================================ -->
            <!-- RIGHT WORKSPACE (5 COLUMNS): REGIME + FIB MATRIX + DISPATCH  -->
            <!-- ============================================================ -->
            <div class="xl:col-span-5 space-y-4">

                <!-- 1. TIMEFRAME SELECTOR & TELEMETRY BAR -->
                <section class="inst-panel rounded-xl p-4 space-y-3">
                    <div class="flex justify-between items-center">
                        <span class="text-xs font-bold text-white uppercase tracking-wider">1. Select Calculation Timeframe</span>
                        <span id="active-tf-badge" class="px-2 py-0.5 rounded text-[11px] font-mono-num font-bold bg-amber-500 text-slate-950">ACTIVE: 5M</span>
                    </div>

                    <div class="grid grid-cols-6 gap-1.5">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-bold border">1M</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-bold border">5M</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-bold border">15M</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-bold border">1H</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-bold border">4H</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-bold border">1D</button>
                    </div>
                </section>

                <!-- 2. DEDICATED SIDEWAY & MARKET REGIME DETECTOR BANNER -->
                <section id="regime-detector-card" class="inst-panel rounded-xl p-4 border-l-4 border-l-emerald-500 transition-all">
                    <div class="flex justify-between items-start gap-3">
                        <div class="space-y-1">
                            <div class="flex items-center gap-2">
                                <span class="text-[10px] font-mono-num uppercase tracking-wider text-slate-400">MARKET REGIME & VOLATILITY DETECTOR</span>
                                <span id="regime-badge-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">TRENDING</span>
                            </div>
                            <h3 id="regime-headline" class="text-sm font-bold text-white">ตลาดเคลื่อนไหวมีทิศทางชัดเจน (Normal Trend Regime)</h3>
                            <p id="regime-subtext" class="text-[11px] text-slate-400">ระยะสวิงกว้างกว่าเกณฑ์ขั้นต่ำ ($8.00) สามารถใช้กรอบ Fibonacci 0.5 และ 61.8% อ้างอิงตามปกติ</p>
                        </div>
                        <div class="text-right shrink-0 bg-[#06080E] px-3 py-2 rounded-lg border border-white/10">
                            <span class="text-[9px] font-mono-num text-slate-400 block uppercase">100-BAR RANGE</span>
                            <span id="regime-range-val" class="font-mono-num text-base font-extrabold text-emerald-400">$--</span>
                        </div>
                    </div>
                </section>

                <!-- 3. PRECISION 2-STAGE FIBONACCI EXECUTION MATRIX -->
                <section class="inst-panel-gold rounded-xl p-4 space-y-3.5">
                    
                    <!-- Direction Structure Header -->
                    <div id="right-card-direction-banner" class="p-3.5 rounded-lg border flex justify-between items-center">
                        <div>
                            <span class="text-[10px] font-mono-num uppercase tracking-wider text-slate-400 block">TECHNICAL SWING BIAS</span>
                            <div id="setup-order-badge" class="text-lg md:text-xl font-extrabold font-mono-num mt-0.5">--</div>
                            <div id="setup-order-subtext" class="text-[11px] text-slate-300 mt-0.5">--</div>
                        </div>
                        <div class="text-right font-mono-num text-xs space-y-1 bg-[#06080E]/80 px-3 py-2 rounded border border-white/10">
                            <div><span class="text-slate-400 text-[10px]">HIGH:</span> <strong id="display-swing-high" class="text-white">--</strong></div>
                            <div><span class="text-slate-400 text-[10px]">LOW:</span> <strong id="display-swing-low" class="text-white">--</strong></div>
                        </div>
                    </div>

                    <!-- STAGE 1: EARLY WARNING 0.5 (50.0% EQUILIBRIUM) -->
                    <div onclick="copyPrice('val-fib05')" class="inst-card-interactive cursor-pointer p-3.5 rounded-lg border-l-4 border-l-amber-400 flex justify-between items-center">
                        <div class="space-y-0.5">
                            <div class="flex items-center gap-2">
                                <span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono-num font-bold text-[10px]">STAGE 1 • 50.0%</span>
                                <span class="text-xs font-bold text-amber-300">จุดแจ้งเตือนล่วงหน้า (Fibonacci 0.5 Equilibrium)</span>
                            </div>
                            <p class="text-[11px] text-slate-400">บอทจะยิงแจ้งเตือนครั้งแรกเมื่อราคาแตะจุดนี้ เพื่อให้เตรียมตัวก่อนเข้า Golden Zone</p>
                        </div>
                        <div class="text-right shrink-0 ml-3">
                            <span id="val-fib05" class="font-mono-num text-xl font-extrabold text-amber-400 block">--</span>
                            <span class="text-[9px] font-mono-num text-slate-400 uppercase">Click to Copy</span>
                        </div>
                    </div>

                    <!-- STAGE 2: GOLDEN ZONE 61.8% & RISK MATRIX (4-GRID) -->
                    <div class="grid grid-cols-2 gap-2.5">
                        <!-- 61.8% Golden Zone -->
                        <div onclick="copyPrice('val-entry')" class="inst-card-interactive cursor-pointer p-3.5 rounded-lg border-l-4 border-l-sky-400">
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono-num font-bold text-sky-400 uppercase">STAGE 2 • GOLDEN ZONE 61.8%</span>
                                <i class="fa-regular fa-copy text-[10px] text-slate-500"></i>
                            </div>
                            <div id="val-entry" class="text-xl font-extrabold font-mono-num text-white mt-1">--</div>
                            <span class="text-[10px] text-slate-400 block mt-0.5">โซนคำนวณทางเทคนิคหลัก</span>
                        </div>

                        <!-- 78.6% Invalidation SL -->
                        <div onclick="copyPrice('val-sl')" class="inst-card-interactive cursor-pointer p-3.5 rounded-lg border-l-4 border-l-rose-500">
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono-num font-bold text-rose-400 uppercase">INVALIDATION • FIB 78.6%</span>
                                <span id="val-risk-pts" class="text-[10px] font-mono-num text-rose-300">--</span>
                            </div>
                            <div id="val-sl" class="text-xl font-extrabold font-mono-num text-rose-400 mt-1">--</div>
                            <span class="text-[10px] text-slate-400 block mt-0.5">จุดตัดความเสี่ยงทางสถิติ</span>
                        </div>

                        <!-- TP1 (1:2) -->
                        <div onclick="copyPrice('val-tp1')" class="inst-card-interactive cursor-pointer p-3.5 rounded-lg border-l-4 border-l-emerald-500">
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono-num font-bold text-emerald-400 uppercase">TARGET 1 • RR 1:2</span>
                                <span id="val-tp1-pts" class="text-[10px] font-mono-num text-emerald-300">--</span>
                            </div>
                            <div id="val-tp1" class="text-xl font-extrabold font-mono-num text-emerald-400 mt-1">--</div>
                            <span class="text-[10px] text-slate-400 block mt-0.5">เป้าหมายสถิติระยะที่ 1</span>
                        </div>

                        <!-- TP2 (1:3) -->
                        <div onclick="copyPrice('val-tp2')" class="inst-card-interactive cursor-pointer p-3.5 rounded-lg border-l-4 border-l-amber-500">
                            <div class="flex justify-between items-center">
                                <span class="text-[10px] font-mono-num font-bold text-amber-400 uppercase">TARGET 2 • RR 1:3</span>
                                <span id="val-tp2-pts" class="text-[10px] font-mono-num text-amber-300">--</span>
                            </div>
                            <div id="val-tp2" class="text-xl font-extrabold font-mono-num text-amber-400 mt-1">--</div>
                            <span class="text-[10px] text-slate-400 block mt-0.5">เป้าหมายสถิติหลัก</span>
                        </div>
                    </div>

                    <!-- INTEGRATED POSITION SIZING CALCULATOR -->
                    <div class="bg-[#06080E] p-3 rounded-lg border border-white/10 flex flex-wrap justify-between items-center gap-2 text-xs">
                        <div class="flex items-center gap-3">
                            <div>
                                <label class="text-[10px] text-slate-400 block">Balance ($)</label>
                                <input type="number" id="acc-balance" value="1000" oninput="recalcLotSize()" class="w-20 bg-[#111726] border border-white/15 rounded px-2 py-1 text-white font-mono-num text-xs">
                            </div>
                            <div>
                                <label class="text-[10px] text-slate-400 block">Risk (%)</label>
                                <input type="number" id="acc-risk-pct" value="1.5" step="0.1" oninput="recalcLotSize()" class="w-16 bg-[#111726] border border-white/15 rounded px-2 py-1 text-white font-mono-num text-xs">
                            </div>
                        </div>
                        <div class="text-right">
                            <span class="text-[10px] text-slate-400 block uppercase font-mono-num">Recommended Position Size</span>
                            <span id="calc-lot-result" class="font-mono-num font-extrabold text-sm text-amber-400">0.05 Lot</span>
                        </div>
                    </div>

                    <!-- MANUAL TELEGRAM DISPATCH BUTTON -->
                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="inst-btn w-full py-3 px-4 rounded-lg font-bold text-xs uppercase tracking-wider bg-amber-500 hover:bg-amber-400 text-slate-950 flex items-center justify-center gap-2 shadow-lg">
                        <i class="fa-brands fa-telegram text-sm"></i>
                        <span>Dispatch Current Matrix to Telegram Now</span>
                    </button>
                </section>

                <!-- 4. COLLAPSIBLE MANUAL SWING OVERRIDE DRAWER -->
                <details class="inst-panel rounded-xl p-3.5 text-xs">
                    <summary class="font-semibold text-slate-300 cursor-pointer select-none flex justify-between items-center">
                        <span><i class="fa-solid fa-sliders text-amber-400 mr-1.5"></i> Manual Swing High / Low Override (กำหนดกรอบสวิงเอง)</span>
                        <span class="text-[10px] font-mono-num text-slate-400">EXPAND</span>
                    </summary>
                    <div class="grid grid-cols-3 gap-2 pt-3">
                        <select id="custom-dir" class="bg-[#06080E] border border-white/15 rounded-lg p-2 text-white font-mono-num font-bold text-xs">
                            <option value="SELL">SELL BIAS</option>
                            <option value="BUY">BUY BIAS</option>
                        </select>
                        <input type="number" id="custom-high" step="0.1" placeholder="Swing High" class="bg-[#06080E] border border-white/15 rounded-lg p-2 text-white font-mono-num text-xs">
                        <input type="number" id="custom-low" step="0.1" placeholder="Swing Low" class="bg-[#06080E] border border-white/15 rounded-lg p-2 text-white font-mono-num text-xs">
                    </div>
                    <button onclick="applyCustomSwing()" class="inst-btn mt-2.5 w-full py-2 rounded-lg bg-white/10 hover:bg-amber-500 hover:text-slate-950 text-slate-200 font-bold text-xs">
                        Apply Custom Coordinates
                    </button>
                </details>

                <!-- 5. SIGNAL DISPATCH LOG & MULTI-TF MATRIX TABS -->
                <section class="inst-panel rounded-xl p-4 space-y-3">
                    <div class="flex items-center justify-between border-b border-white/10 pb-2.5">
                        <div class="flex gap-1.5">
                            <button onclick="switchRightTab('feed')" id="tab-btn-feed" class="px-2.5 py-1 rounded text-[11px] font-bold bg-amber-500 text-slate-950">Dispatch Log</button>
                            <button onclick="switchRightTab('matrix')" id="tab-btn-matrix" class="px-2.5 py-1 rounded text-[11px] font-semibold bg-white/5 text-slate-400 border border-white/10">Multi-TF Matrix</button>
                        </div>
                        <span class="text-[10px] text-slate-400 font-mono-num" id="feed-counter-label">--</span>
                    </div>
                    <div id="right-tab-feed" class="space-y-2 max-h-[200px] overflow-y-auto pr-1"></div>
                    <div id="right-tab-matrix" class="hidden space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
                        <div id="matrix-overview-list" class="space-y-1.5 text-xs"></div>
                    </div>
                </section>

            </div>
        </div>
    </main>

    <!-- INSTITUTIONAL FOOTER -->
    <footer class="border-t border-white/10 bg-[#0B0F17] py-3 px-4 text-center text-[11px] text-slate-500 mt-6">
        GOLD AI SNIPER PRO • Quantitative Fibonacci Retracement & Volatility Telemetry Terminal • For Technical & Statistical Reference Only (Not Financial Advice)
    </footer>

    <!-- TOAST FEEDBACK -->
    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-[#111726] border border-amber-500/50 text-white px-4 py-3 rounded-lg font-medium text-xs shadow-2xl z-50 flex items-center gap-2.5">
        <span class="status-dot bg-amber-400"></span>
        <span id="toast-notify-text">ดำเนินการสำเร็จ</span>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        const SIDEWAY_THRESHOLD = 8.00;
        const timeframeMeta = {
            '1m':    { label: '1M',  tvInterval: '1',   lookback: 90 },
            '5m':    { label: '5M',  tvInterval: '5',   lookback: 96 },
            '15m':   { label: '15M', tvInterval: '15',  lookback: 96 },
            '1h':    { label: '1H',  tvInterval: '60',  lookback: 100 },
            '4h':    { label: '4H',  tvInterval: '240', lookback: 100 },
            'daily': { label: '1D',  tvInterval: 'D',   lookback: 90 }
        };

        const liveTimeframeStore = {};
        let currentTfKey = '5m';
        let currentTvLoadedInterval = null;
        let isNewsLocked = false;
        let currentRiskDollar = 5.0;
        let allCalendarEvents = [];
        let currentNewsFilter = 'ALL';
        let localAlertMemory = {};

        // ====================================================================
        // 1. QUANTITATIVE FIBONACCI & SIDEWAY DETECTION MATH
        // ====================================================================
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
                fib05Num: fib05, entryNum: entry, slNum: sl, tp1Num: tp1, tp2Num: tp2,
                fib05: fib05.toFixed(2),
                entry: entry.toFixed(2),
                sl: sl.toFixed(2),
                tp1: tp1.toFixed(2),
                tp2: tp2.toFixed(2),
                riskNum: risk,
                riskDollar: risk.toFixed(2),
                reward1Dollar: (risk * 2.0).toFixed(2),
                reward2Dollar: (risk * 3.0).toFixed(2)
            };
        }

        async function fetchRealGoldCandles(tfKey) {
            const meta = timeframeMeta[tfKey];
            const binanceTf = tfKey === 'daily' ? '1d' : tfKey;
            const url = `https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=${binanceTf}&limit=150`;
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

        function updateRegimeBanners(tfKey, mathRes) {
            const topPill = document.getElementById('top-regime-pill');
            const topDot = document.getElementById('top-regime-dot');
            const topText = document.getElementById('top-regime-text');

            const card = document.getElementById('regime-detector-card');
            const badge = document.getElementById('regime-badge-pill');
            const headline = document.getElementById('regime-headline');
            const subtext = document.getElementById('regime-subtext');
            const rangeVal = document.getElementById('regime-range-val');

            rangeVal.innerText = `$${mathRes.range}`;
            document.getElementById('chart-range-pill').innerText = `Swing Range: $${mathRes.range}`;

            if (mathRes.isSideway) {
                topPill.className = "px-2.5 py-1 rounded bg-amber-500/15 border border-amber-500/40 flex items-center gap-2 text-xs";
                topDot.className = "status-dot bg-amber-400 animate-ping";
                topText.className = "font-mono-num font-bold text-amber-400 text-[11px]";
                topText.innerText = `SIDEWAY WARNING ($${mathRes.range})`;

                card.className = "inst-panel rounded-xl p-4 border-l-4 border-l-amber-500 bg-amber-500/5 transition-all";
                badge.className = "px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40";
                badge.innerText = "SIDEWAY / CHOPPY";
                headline.className = "text-sm font-bold text-amber-300";
                headline.innerText = `⚠️ ตรวจพบตลาด Sideway กรอบแคบผิดปกติ ($${mathRes.range} < $8.00)`;
                subtext.innerText = "ราคากำลังบีบอัดไร้ทิศทางชัดเจน แนะนำให้ชะลอการเข้าออเดอร์ หรือลดขนาด Lot ลง 50% เพื่อป้องกันการโดนกวาด SL";
                rangeVal.className = "font-mono-num text-base font-extrabold text-amber-400";
            } else {
                topPill.className = "px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-xs";
                topDot.className = "status-dot bg-emerald-400";
                topText.className = "font-mono-num font-bold text-emerald-400 text-[11px]";
                topText.innerText = `REGIME: TRENDING ($${mathRes.range})`;

                card.className = "inst-panel rounded-xl p-4 border-l-4 border-l-emerald-500 transition-all";
                badge.className = "px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30";
                badge.innerText = "TRENDING REGIME";
                headline.className = "text-sm font-bold text-white";
                headline.innerText = `ตลาดเคลื่อนไหวมีกรอบสวิงชัดเจน (Range $${mathRes.range})`;
                subtext.innerText = "ความผันผวนอยู่ในเกณฑ์มาตรฐาน สามารถใช้ระดับ 0.5 (เตรียมตัว) และ 61.8% (Golden Zone) อ้างอิงได้ตามปกติ";
                rangeVal.className = "font-mono-num text-base font-extrabold text-emerald-400";
            }
        }

        function checkProximityAndAlert(tfKey, state, mathRes) {
            const pill = document.getElementById('proximity-pill');
            const price = state.currentPrice;
            const tol = Math.max(0.45, mathRes.rangeNum * 0.035);

            if (mathRes.isSideway) {
                pill.className = "px-2 py-0.5 text-[10px] font-mono-num font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40";
                pill.innerText = "SIDEWAY PAUSE";
                return;
            }

            if (Math.abs(price - mathRes.entryNum) <= tol) {
                pill.className = "px-2 py-0.5 text-[10px] font-mono-num font-bold rounded bg-sky-500 text-slate-950";
                pill.innerText = "IN 61.8% ZONE";
            } else if (Math.abs(price - mathRes.fib05Num) <= tol) {
                pill.className = "px-2 py-0.5 text-[10px] font-mono-num font-bold rounded bg-amber-400 text-slate-950";
                pill.innerText = "TOUCHED 0.5 PREP";
            } else {
                pill.className = "px-2 py-0.5 text-[10px] font-mono-num font-semibold rounded bg-white/5 text-slate-300 border border-white/10";
                pill.innerText = `WAIT 0.5 ($${mathRes.fib05})`;
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
                rightBanner.className = "p-3.5 rounded-lg border border-rose-500/40 bg-rose-950/20 flex justify-between items-center";
                rightBadge.className = "text-lg md:text-xl font-extrabold font-mono-num text-rose-400";
                rightBadge.innerText = `BEARISH RETRACEMENT (SELL BIAS • ${tfKey.toUpperCase()})`;
                rightSub.innerText = `เตรียมตัวที่ 0.5 ($${mathRes.fib05}) • โซนหลัก 61.8% ($${mathRes.entry})`;
            } else {
                rightBanner.className = "p-3.5 rounded-lg border border-emerald-500/40 bg-emerald-950/20 flex justify-between items-center";
                rightBadge.className = "text-lg md:text-xl font-extrabold font-mono-num text-emerald-400";
                rightBadge.innerText = `BULLISH RETRACEMENT (BUY BIAS • ${tfKey.toUpperCase()})`;
                rightSub.innerText = `เตรียมตัวที่ 0.5 ($${mathRes.fib05}) • โซนหลัก 61.8% ($${mathRes.entry})`;
            }

            updateRegimeBanners(tfKey, mathRes);
            checkProximityAndAlert(tfKey, state, mathRes);
            recalcLotSize();
            renderMatrixTable(tfKey);
        }

        function recalcLotSize() {
            const balance = parseFloat(document.getElementById('acc-balance').value) || 1000;
            const riskPct = parseFloat(document.getElementById('acc-risk-pct').value) || 1.5;
            const riskMoney = balance * (riskPct / 100.0);
            const lossPerOneLot = Math.max(0.5, currentRiskDollar) * 100.0;
            const finalLot = Math.max(0.01, riskMoney / lossPerOneLot).toFixed(2);
            document.getElementById('calc-lot-result').innerText = `${finalLot} Lot ($${riskMoney.toFixed(1)})`;
        }

        async function triggerAutoFibonacciCalculation(showNotification = true) {
            const icon = document.getElementById('fib-spin-icon');
            if (icon) icon.className = "fa-solid fa-spinner fa-spin text-[11px]";
            try {
                const state = await fetchRealGoldCandles(currentTfKey);
                applyStateToUI(currentTfKey, state);
                if (showNotification) showToast(`คำนวณกรอบราคา ${currentTfKey.toUpperCase()} เรียบร้อย`);
            } catch (e) {
                console.error(e);
            } finally {
                if (icon) icon.className = "fa-solid fa-rotate text-[11px]";
            }
        }

        async function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const meta = timeframeMeta[tfKey];
            if (!meta) return;

            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-bold bg-[#06080E] text-slate-400 border border-white/10 hover:text-white";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn inst-btn py-2 rounded-lg text-xs font-mono-num font-extrabold bg-amber-500 text-slate-950 border border-amber-400";
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
            showToast('อัปเดตกรอบราคาจากค่าที่กำหนดเองเรียบร้อย');
        }

        function loadTradingViewStudio(intervalCode) {
            if (currentTvLoadedInterval === intervalCode) return;
            currentTvLoadedInterval = intervalCode;
            const container = document.getElementById('tradingview_advanced_chart');
            container.innerHTML = '';
            new TradingView.widget({
                "width": "100%",
                "height": "510",
                "symbol": "OANDA:XAUUSD",
                "interval": intervalCode,
                "timezone": "Asia/Bangkok",
                "theme": "dark",
                "style": "1",
                "locale": "th",
                "toolbar_bg": "#0B0F17",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "container_id": "tradingview_advanced_chart"
            });
        }

        // ====================================================================
        // 2. AUTHENTICATION & TELEGRAM API HANDLERS
        // ====================================================================
        function checkAuthStatus() {
            const savedEmail = localStorage.getItem('gold_sniper_email');
            const savedChatId = localStorage.getItem('gold_sniper_chat_id') || '8948986514';
            localStorage.setItem('gold_sniper_chat_id', savedChatId);
            document.getElementById('set-chat-id').value = savedChatId;
            document.getElementById('telegram-status-btn').innerText = `TG: ${savedChatId}`;

            if (!savedEmail) {
                document.getElementById('auth-modal').classList.remove('hidden');
            } else {
                document.getElementById('user-email-badge').innerText = savedEmail.split('@')[0];
                document.getElementById('login-email').value = savedEmail;
            }
        }

        function openAuthModal() {
            document.getElementById('auth-modal').classList.remove('hidden');
        }

        async function submitEmailLogin() {
            const email = document.getElementById('login-email').value.trim();
            const accepted = document.getElementById('login-disclaimer').checked;
            if (!email || !email.includes('@')) {
                showToast('กรุณากรอกอีเมลให้ถูกต้อง');
                return;
            }
            if (!accepted) {
                showToast('กรุณาติ๊กยอมรับข้อตกลงการใช้งานเครื่องมือทางเทคนิค');
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
                    chat_id: document.getElementById('set-chat-id').value.trim(),
                    preferred_tf: currentTfKey
                })
            });
            showToast('เข้าสู่ระบบ GOLD AI SNIPER PRO เรียบร้อย');
        }

        function toggleSettingsModal() {
            document.getElementById('settings-modal').classList.toggle('hidden');
        }

        async function autoDetectTelegramChatId() {
            showToast('กำลังค้นหา Chat ID ล่าสุดที่กด /start...');
            try {
                const res = await fetch('/api/telegram-detect-chat');
                const data = await res.json();
                if (data.status === 'ok' && data.chat_id) {
                    document.getElementById('set-chat-id').value = data.chat_id;
                    localStorage.setItem('gold_sniper_chat_id', data.chat_id);
                    document.getElementById('telegram-status-btn').innerText = `TG: ${data.chat_id}`;
                    showToast(`พบ Chat ID: ${data.chat_id} (${data.name})`);
                } else {
                    showToast('ยังไม่พบข้อความใหม่ กรุณาทัก /start ในบอทอีกครั้ง');
                }
            } catch (e) {
                showToast('ไม่สามารถดึงข้อมูล Chat ID ได้');
            }
        }

        async function saveUserSettings() {
            const email = localStorage.getItem('gold_sniper_email') || 'default@gold.ai';
            const chatId = document.getElementById('set-chat-id').value.trim();
            const tf = document.getElementById('set-tf').value;
            const startT = document.getElementById('set-start-time').value;
            const endT = document.getElementById('set-end-time').value;
            const alertMorning = document.getElementById('set-alert-morning').checked;
            const alertSideway = document.getElementById('set-alert-sideway').checked;
            const alert05 = document.getElementById('set-alert-05').checked;
            const alert618 = document.getElementById('set-alert-618').checked;
            const balance = parseFloat(document.getElementById('acc-balance').value) || 1000;
            const riskPct = parseFloat(document.getElementById('acc-risk-pct').value) || 1.5;

            localStorage.setItem('gold_sniper_chat_id', chatId);
            if (chatId) {
                document.getElementById('telegram-status-btn').innerText = `TG: ${chatId}`;
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
                    alert_morning_news: alertMorning,
                    alert_sideway: alertSideway,
                    alert_05: alert05,
                    alert_618: alert618,
                    balance: balance,
                    risk_pct: riskPct
                })
            });

            selectTimeframe(tf);
            toggleSettingsModal();
            showToast('บันทึกการตั้งค่าและเปิดระบบสแกน 24 ชม. เรียบร้อย');
        }

        async function sendTestTelegram() {
            const chatId = document.getElementById('set-chat-id').value.trim();
            if (!chatId) {
                showToast('กรุณากรอกเลข Chat ID ก่อนทดสอบ');
                return;
            }
            const res = await fetch('/api/test-telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId })
            });
            const data = await res.json();
            if (res.ok && data.status === 'ok') {
                showToast('ส่งข้อความทดสอบเข้า Telegram สำเร็จ!');
            } else {
                showToast('ส่งไม่สำเร็จ: ' + (data.message || 'กรุณาเช็กการกด /start'));
            }
        }

        async function sendMorningBriefNow() {
            const chatId = document.getElementById('set-chat-id').value.trim() || localStorage.getItem('gold_sniper_chat_id');
            if (!chatId) {
                toggleSettingsModal();
                showToast('กรุณาระบุ Chat ID ก่อนส่งสรุปข่าว');
                return;
            }
            const startT = document.getElementById('set-start-time').value || '08:00';
            const endT = document.getElementById('set-end-time').value || '22:00';
            const res = await fetch('/api/send-morning-brief', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId, start_time: startT, end_time: endT })
            });
            const data = await res.json();
            if (res.ok && data.status === 'ok') {
                showToast('ส่งสรุปตารางข่าวประจำวันเข้า Telegram เรียบร้อย!');
            } else {
                showToast('ส่งสรุปข่าวไม่สำเร็จ: ' + (data.message || 'Error'));
            }
        }

        async function broadcastCurrentSignal() {
            if (isNewsLocked) {
                showToast('ระบบล็อกการส่งชั่วคราวเนื่องจากอยู่ในช่วงเฝ้าระวังข่าวแดง');
                return;
            }
            const chatId = document.getElementById('set-chat-id').value.trim() || localStorage.getItem('gold_sniper_chat_id') || '';
            if (!chatId) {
                toggleSettingsModal();
                showToast('กรุณาตั้งค่า Telegram Chat ID ก่อนส่งสัญญาณ');
                return;
            }

            const curState = liveTimeframeStore[currentTfKey];
            const mathRes = calculateSniperMath(
                document.getElementById('custom-dir').value,
                parseFloat(document.getElementById('display-swing-high').innerText.replace('$', '')),
                parseFloat(document.getElementById('display-swing-low').innerText.replace('$', ''))
            );

            const payload = {
                chat_id: chatId,
                symbol: 'XAUUSD',
                tf: currentTfKey.toUpperCase(),
                direction: document.getElementById('custom-dir').value,
                regime: mathRes.isSideway ? 'SIDEWAY' : 'TRENDING',
                range: mathRes.range,
                fib_05: mathRes.fib05,
                entry: mathRes.entry,
                sl: mathRes.sl,
                tp1: mathRes.tp1,
                tp2: mathRes.tp2,
                lot: document.getElementById('calc-lot-result').innerText
            };

            const res = await fetch('/api/send-signal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                const data = await res.json();
                renderSignalFeed(data.signal_history);
                showToast('ส่งข้อมูลระดับราคาเข้า Telegram เรียบร้อย!');
            } else {
                const err = await res.json();
                showToast('ส่งไม่สำเร็จ: ' + (err.message || 'Error'));
            }
        }

        // ====================================================================
        // 3. TABLES, LOGS & ECONOMIC CALENDAR RENDERING
        // ====================================================================
        function switchRightTab(tab) {
            document.getElementById('right-tab-feed').classList.toggle('hidden', tab !== 'feed');
            document.getElementById('right-tab-matrix').classList.toggle('hidden', tab !== 'matrix');
            document.getElementById('tab-btn-feed').className = tab === 'feed'
                ? "px-2.5 py-1 rounded text-[11px] font-bold bg-amber-500 text-slate-950"
                : "px-2.5 py-1 rounded text-[11px] font-semibold bg-white/5 text-slate-400 border border-white/10";
            document.getElementById('tab-btn-matrix').className = tab === 'matrix'
                ? "px-2.5 py-1 rounded text-[11px] font-bold bg-amber-500 text-slate-950"
                : "px-2.5 py-1 rounded text-[11px] font-semibold bg-white/5 text-slate-400 border border-white/10";
        }

        function renderMatrixTable(activeKey) {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';
            Object.keys(timeframeMeta).forEach(key => {
                const st = liveTimeframeStore[key];
                if (!st) return;
                const lvls = calculateSniperMath(st.calcDir, st.swingHigh, st.swingLow);
                const row = document.createElement('div');
                row.className = `flex items-center justify-between p-2.5 rounded-lg border cursor-pointer font-mono-num ${
                    key === activeKey ? 'bg-amber-500/10 border-amber-500/40' : 'bg-[#06080E] border-white/10 hover:border-white/20'
                }`;
                row.onclick = () => selectTimeframe(key);
                row.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="font-bold text-amber-400 w-8 uppercase">${key}</span>
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${st.calcDir === 'SELL' ? 'bg-rose-500/15 text-rose-400' : 'bg-emerald-500/15 text-emerald-400'}">${st.calcDir}</span>
                        <span class="text-[10px] ${lvls.isSideway ? 'text-amber-400' : 'text-slate-400'}">${lvls.isSideway ? 'SIDEWAY' : 'TREND'} ($${lvls.range})</span>
                    </div>
                    <div class="flex gap-3 text-[11px]">
                        <span class="text-amber-300">0.5: $${lvls.fib05}</span>
                        <span class="text-sky-400 font-bold">61.8%: $${lvls.entry}</span>
                    </div>
                `;
                list.appendChild(row);
            });
        }

        function renderSignalFeed(signals) {
            const container = document.getElementById('right-tab-feed');
            document.getElementById('feed-counter-label').innerText = `${signals.length} RECORDS`;
            container.innerHTML = '';
            signals.forEach(sig => {
                const isSell = sig.direction === 'SELL';
                const card = document.createElement('div');
                card.className = `p-3 rounded-lg bg-[#06080E] border border-white/10 border-l-2 ${isSell ? 'border-l-rose-500' : 'border-l-emerald-500'} space-y-1 text-xs font-mono-num`;
                card.innerHTML = `
                    <div class="flex justify-between items-center">
                        <span class="font-bold text-white">${sig.symbol} • ${sig.tf} (${sig.direction})</span>
                        <span class="text-[10px] text-slate-400">${sig.time}</span>
                    </div>
                    <div class="flex flex-wrap gap-2.5 text-[11px] pt-0.5">
                        <span class="text-amber-300">0.5: $${sig.fib_05 || '-'}</span>
                        <span class="text-sky-400 font-bold">61.8%: $${sig.entry}</span>
                        <span class="text-rose-400">SL: $${sig.sl}</span>
                        <span class="text-emerald-400">TP2: $${sig.tp2}</span>
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
            ['ALL', 'TODAY', 'HIGH'].forEach(m => {
                const btn = document.getElementById('news-filter-' + m);
                if (!btn) return;
                btn.className = (m === mode)
                    ? "px-2.5 py-1 rounded text-[11px] font-semibold bg-amber-500 text-slate-950"
                    : "px-2.5 py-1 rounded text-[11px] font-semibold bg-white/5 text-slate-300 border border-white/10";
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
            if (!filtered.length) {
                tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-slate-500">ไม่มีรายการข่าวเศรษฐกิจในหมวดที่เลือก</td></tr>`;
                return;
            }
            filtered.forEach(item => {
                const badge = item.impact === 'HIGH'
                    ? '<span class="px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-400 border border-rose-500/30 font-bold text-[10px]">HIGH</span>'
                    : '<span class="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold text-[10px]">MED</span>';
                const tr = document.createElement('tr');
                tr.className = "hover:bg-white/[0.02]";
                tr.innerHTML = `
                    <td class="py-2.5 px-2 text-amber-300 whitespace-nowrap">${item.date_label} • ${item.time_label}</td>
                    <td class="py-2.5 px-2 text-slate-200 font-sans font-medium">${item.event}</td>
                    <td class="py-2.5 px-2 whitespace-nowrap">${badge}</td>
                    <td class="py-2.5 px-2 text-slate-400 whitespace-nowrap">${item.forecast} / ${item.previous}</td>
                    <td class="py-2.5 px-2 text-slate-300 whitespace-nowrap">${item.countdown}</td>
                    <td class="py-2.5 px-2 text-right text-slate-400 whitespace-nowrap">${item.status}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        function updateNewsShieldUI(locked, reasonText) {
            const box = document.getElementById('news-shield-box');
            const dot = document.getElementById('shield-dot');
            const text = document.getElementById('shield-status-text');
            if (locked) {
                box.className = "px-2.5 py-1 rounded bg-rose-500/15 border border-rose-500/40 flex items-center gap-2 text-xs";
                dot.className = "status-dot bg-rose-500 animate-ping";
                text.className = "text-[11px] font-bold text-rose-400";
                text.innerText = "SHIELD ACTIVE (LOCKED)";
            } else {
                box.className = "px-2.5 py-1 rounded bg-white/5 border border-white/10 flex items-center gap-2 text-xs";
                dot.className = "status-dot bg-emerald-400";
                text.className = "text-[11px] font-medium text-slate-300";
                text.innerText = "News Shield: Standby";
            }
        }

        async function toggleNewsLock() {
            const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
            const data = await res.json();
            isNewsLocked = data.news_locked;
            updateNewsShieldUI(isNewsLocked, data.lock_reason);
            showToast(isNewsLocked ? 'เปิดโหมดจำลองการล็อกช่วงข่าวแดง' : 'ปลดล็อกโหมดข่าวแดง');
        }

        function copyPrice(elementId) {
            const text = document.getElementById(elementId).innerText.replace('$', '');
            navigator.clipboard.writeText(text);
            showToast(`คัดลอกระดับราคา $${text} เรียบร้อย`);
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
            for (const k of Object.keys(timeframeMeta)) {
                if (k !== currentTfKey) { try { await fetchRealGoldCandles(k); } catch (e) {} }
            }
            renderMatrixTable(currentTfKey);

            setInterval(() => {
                triggerAutoFibonacciCalculation(false);
            }, 20000);
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
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()
    auto_locking_event = next((ev for ev in calendar_events if ev.get("is_locking_now")), None)
    is_locked = SYSTEM_STATE["manual_news_lock"] or (auto_locking_event is not None)

    return jsonify({
        "safe_to_trade": not is_locked,
        "news_locked": is_locked,
        "lock_reason": "SHIELD LOCKED" if is_locked else "STANDBY",
        "signal_history": SYSTEM_STATE["signal_history"],
        "economic_calendar": calendar_events,
        "scanner_last_run": SYSTEM_STATE["scanner_last_run"],
        "server_time": now_dt.strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/api/user-config', methods=['POST'])
def save_user_config():
    data = request.json or {}
    email = data.get("email", "default@gold.ai").strip().lower()
    chat_id = str(data.get("chat_id", "8948986514")).strip()

    USERS_DB[email] = {
        "email": email,
        "chat_id": chat_id,
        "preferred_tf": data.get("preferred_tf", "5m").lower(),
        "start_time": data.get("start_time", "08:00"),
        "end_time": data.get("end_time", "22:00"),
        "alert_morning_news": bool(data.get("alert_morning_news", True)),
        "alert_sideway": bool(data.get("alert_sideway", True)),
        "alert_05": bool(data.get("alert_05", True)),
        "alert_618": bool(data.get("alert_618", True)),
        "balance": float(data.get("balance", 1000.0)),
        "risk_pct": float(data.get("risk_pct", 1.5)),
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
    now_dt = datetime.now(TH_TZ)
    msg = (
        f"✅ <b>GOLD AI SNIPER PRO — TERMINAL LINKED</b>\n"
        f"🕒 <b>เวลาเซิร์ฟเวอร์:</b> {now_dt.strftime('%H:%M:%S')} น.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"ระบบเชื่อมต่อกับ Telegram ของคุณสำเร็จ 100% พร้อมสแกนและแจ้งเตือน:\n"
        f"1. 🌅 สรุปตารางข่าวแดงประจำวันตอนเช้า\n"
        f"2. ⚠️ เตือนเมื่อตลาดเข้าโหมด Sideway (&lt; ${SIDEWAY_THRESHOLD_DOLLAR:.2f})\n"
        f"3. 🔔 เตือนล่วงหน้าเมื่อแตะระดับ 0.5 (50.0%)\n"
        f"4. 🎯 เตือนเมื่อราคาเข้า Golden Zone 61.8%"
    )
    ok, err = send_telegram_message(chat_id, msg)
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": err}), 400


@app.route('/api/send-morning-brief', methods=['POST'])
def trigger_morning_brief():
    data = request.json or {}
    chat_id = data.get("chat_id", "").strip()
    start_t = data.get("start_time", "08:00")
    end_t = data.get("end_time", "22:00")
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()

    msg = build_morning_news_brief_message(now_dt, calendar_events, start_t, end_t)
    ok, err = send_telegram_message(chat_id, msg)
    if ok:
        today_str = now_dt.strftime("%Y-%m-%d")
        SYSTEM_STATE["morning_brief_memory"][f"{chat_id}_{today_str}"] = True
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": err}), 400


@app.route('/api/toggle-news-lock', methods=['POST'])
def toggle_news_lock():
    SYSTEM_STATE["manual_news_lock"] = not SYSTEM_STATE["manual_news_lock"]
    return jsonify({
        "status": "ok",
        "news_locked": SYSTEM_STATE["manual_news_lock"],
        "lock_reason": "SHIELD LOCKED" if SYSTEM_STATE["manual_news_lock"] else "STANDBY"
    })


@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()
    auto_locking_event = next((ev for ev in calendar_events if ev.get("is_locking_now")), None)

    if SYSTEM_STATE["manual_news_lock"] or auto_locking_event:
        return jsonify({
            "status": "blocked",
            "message": "News Shield Active: ระบบล็อกการส่งสัญญาณในช่วงข่าวแดง"
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
        "regime": data.get("regime", "TRENDING"),
        "range": data.get("range", "0.00"),
        "fib_05": data.get("fib_05", "0.00"),
        "entry": data.get("entry", "0.00"),
        "sl": data.get("sl", "0.00"),
        "tp1": data.get("tp1", "0.00"),
        "tp2": data.get("tp2", "0.00"),
        "status": "DISPATCHED"
    }

    SYSTEM_STATE["latest_signal"] = sig
    SYSTEM_STATE["signal_history"].insert(0, sig)

    regime_tag = "⚠️ SIDEWAY WARNING" if sig["regime"] == "SIDEWAY" else "🟢 TRENDING REGIME"
    msg = (
        f"📐 <b>XAUUSD ({sig['tf']}) • {sig['direction']} MATRIX</b>\n"
        f"📡 <b>สถานะตลาด:</b> {regime_tag} (Range ${sig['range']})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 <b>Stage 1 — จุดเตรียมตัว (0.5):</b> ${sig['fib_05']}\n"
        f"🔵 <b>Stage 2 — Golden Zone (61.8%):</b> ${sig['entry']}\n"
        f"🔴 <b>Invalidation (78.6% SL):</b> ${sig['sl']}\n"
        f"🟢 <b>Target 1 (1:2):</b> ${sig['tp1']}\n"
        f"🟡 <b>Target 2 (1:3):</b> ${sig['tp2']}\n"
        f"⚖️ <b>ขนาด Lot แนะนำ:</b> {data.get('lot', '0.05 Lot')}"
    )

    ok, err = send_telegram_message(chat_id, msg)
    if not ok:
        return jsonify({"status": "error", "message": err}), 400

    return jsonify({
        "status": "success",
        "latest_signal": sig,
        "signal_history": SYSTEM_STATE["signal_history"]
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
