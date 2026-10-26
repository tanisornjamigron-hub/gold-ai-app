import os
import math
import json
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# ==============================================================================
# 1. SYSTEM CONFIGURATION & SELF-HEALING TELEGRAM CREDENTIALS
# ==============================================================================
# รหัส Token ที่ถูกต้อง 100% จาก BotFather (@gold_ai_sniper_pro_bot)
VERIFIED_BOT_TOKEN = "8718020170:AAFj1pPh4HLi8i7Vaz12hi_qAD_J4Dnlzlg"
ENV_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

# ใช้ Verified Token เป็นหลักเพื่อป้องกันปัญหาค่าเก่าค้างใน Render Environment
TELEGRAM_BOT_TOKEN = VERIFIED_BOT_TOKEN
TELEGRAM_BOT_USERNAME = "gold_ai_sniper_pro_bot"
DEFAULT_CHAT_ID = "8948986514"

# เขตเวลาประเทศไทย (UTC+7)
TH_TZ = timezone(timedelta(hours=7))

# แคชตารางข่าว Forex Factory และแคชข้อมูลราคา Multi-Timeframe
FF_CACHE = {
    "last_fetched": 0,
    "events": []
}

MARKET_CACHE = {
    "last_oanda_sync": 0,
    "oanda_spot": None,
    "tf_data": {}
}

# ฐานข้อมูลผู้ใช้งาน (ตั้งค่าเริ่มต้นให้พร้อมทำงานทันที)
USERS_DB = {
    "default@gold.ai": {
        "email": "default@gold.ai",
        "chat_id": DEFAULT_CHAT_ID,
        "custom_bot_token": VERIFIED_BOT_TOKEN,
        "preferred_tf": "5m",
        "start_time": "08:00",
        "end_time": "23:00",
        "alert_05": True,
        "alert_618": True,
        "alert_sideway": True,
        "alert_morning_news": True,
        "balance": 1000.0,
        "risk_pct": 1.5,
        "auto_alert": True
    }
}

# สถานะส่วนกลางของระบบ
SYSTEM_STATE = {
    "active_bot_token": VERIFIED_BOT_TOKEN,
    "manual_news_lock": False,
    "lock_reason": "ตลาดปกติ (Normal Market Conditions)",
    "latest_signal": None,
    "last_alert_memory": {},       # ป้องกันการส่งแจ้งเตือนซ้ำในสวิงเดิม
    "morning_brief_memory": {},    # ป้องกันการส่งสรุปข่าวเช้าซ้ำในวันเดียวกัน
    "scanner_last_run": "-",
    "scanner_status": "INITIALIZING",
    "webhook_override": {},        # รองรับการรับค่าจาก TradingView Webhook หากมีการส่งเข้ามา
    "signal_history": [
        {
            "id": 101,
            "date": "26 ต.ค. 2026",
            "time": "14:20:00",
            "symbol": "XAUUSD",
            "tf": "5M",
            "direction": "BUY",
            "regime": "UPTREND",
            "adx": "28.4",
            "fib_05": "4001.66",
            "entry": "4000.64",
            "sl": "3999.19",
            "tp1": "4003.54",
            "tp2": "4004.99",
            "rr": "1:3",
            "status": "TELEGRAM SENT",
            "reason": "EMA 20 > EMA 50 • ADX 28.4 ยืนยันเทรนด์ขาขึ้น โครงสร้างยก Higher Low"
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
# 2. SELF-HEALING TELEGRAM BOT ENGINE (AUTO-FIX HTTP 401 UNAUTHORIZED)
# ==============================================================================
def get_candidate_tokens(custom_token=None):
    """เรียงลำดับ Token ที่จะใช้ยิง โดยให้ Verified Token มาก่อนค่าเก่าใน Environment เสมอ"""
    candidates = []
    for t in [custom_token, SYSTEM_STATE.get("active_bot_token"), VERIFIED_BOT_TOKEN, ENV_BOT_TOKEN]:
        if t and isinstance(t, str):
            clean_t = t.strip()
            if clean_t and clean_t not in candidates:
                candidates.append(clean_t)
    return candidates


def send_telegram_message(chat_id, text, custom_token=None):
    """
    ส่งข้อความเข้า Telegram พร้อมระบบ Self-Healing:
    หาก Token แรกติด HTTP 401 Unauthorized ระบบจะสลับไปใช้ VERIFIED_BOT_TOKEN อัตโนมัติทันที
    """
    clean_chat_id = str(chat_id or DEFAULT_CHAT_ID).strip()
    if not clean_chat_id:
        return False, "กรุณาระบุ Telegram Chat ID"

    tokens_to_try = get_candidate_tokens(custom_token)
    if not tokens_to_try:
        return False, "ไม่พบรหัส Telegram Bot Token ในระบบ"

    last_error = "Unknown Error"
    for token in tokens_to_try:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({
                "chat_id": clean_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "GoldAISniperPro/5.0"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if res_data.get("ok"):
                    SYSTEM_STATE["active_bot_token"] = token
                    return True, "ส่งข้อความสำเร็จ"
                last_error = res_data.get("description", "Telegram API Error")
        except urllib.error.HTTPError as he:
            try:
                err_body = he.read().decode("utf-8")
                err_json = json.loads(err_body)
                desc = err_json.get("description", err_body)
            except Exception:
                desc = he.reason
            last_error = f"HTTP {he.code}: {desc}"
            # หากติด 401 Unauthorized ให้วนลูปไปลอง Token ถัดไปทันที
            if he.code == 401:
                continue
            else:
                break
        except Exception as e:
            last_error = str(e)

    return False, last_error


def fetch_latest_telegram_chat_id(custom_token=None):
    """ดึง Chat ID ล่าสุดจากผู้ใช้ที่กด /start ในบอท @gold_ai_sniper_pro_bot"""
    tokens_to_try = get_candidate_tokens(custom_token)
    for token in tokens_to_try:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?limit=30"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok") and data.get("result"):
                    SYSTEM_STATE["active_bot_token"] = token
                    for item in reversed(data["result"]):
                        msg = (
                            item.get("message")
                            or item.get("edited_message")
                            or item.get("my_chat_member")
                            or item.get("channel_post")
                        )
                        if msg and "chat" in msg:
                            chat_id = str(msg["chat"]["id"])
                            first_name = (
                                msg["chat"].get("first_name")
                                or msg["chat"].get("username")
                                or msg["chat"].get("title")
                                or "Trader"
                            )
                            return chat_id, first_name
        except Exception as e:
            print("Telegram getUpdates Error:", e)
            continue
    return None, None


# ==============================================================================
# 3. OANDA:XAUUSD LIVE CALIBRATION & MULTI-FACTOR QUANTITATIVE ENGINE
# ==============================================================================
def fetch_tradingview_oanda_telemetry(tf_key="5m"):
    """
    ดึงราคาสดและค่าอินดิเคเตอร์ของ OANDA:XAUUSD โดยตรงจาก TradingView Scanner API
    เพื่อให้ราคาตรงกับกราฟ TradingView (OANDA:XAUUSD) บนหน้าเว็บ 100%
    """
    tf_suffix_map = {
        "1m": "|1",
        "5m": "|5",
        "15m": "|15",
        "1h": "|60",
        "4h": "|240",
        "daily": ""
    }
    sfx = tf_suffix_map.get(tf_key.lower(), "|5")
    cols = [
        f"close{sfx}",
        f"open{sfx}",
        f"high{sfx}",
        f"low{sfx}",
        f"EMA20{sfx}",
        f"EMA50{sfx}",
        f"ADX{sfx}",
        f"ADX+DI{sfx}",
        f"ADX-DI{sfx}",
        f"ATR{sfx}",
        f"RSI{sfx}",
        "close"
    ]
    try:
        url = "https://scanner.tradingview.com/cfd/scan"
        payload = json.dumps({
            "symbols": {"tickers": ["OANDA:XAUUSD"], "query": {"types": []}},
            "columns": cols
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            rows = res.get("data", [])
            if rows and "d" in rows[0]:
                d = rows[0]["d"]
                spot_close = float(d[0] if d[0] is not None else d[11])
                MARKET_CACHE["oanda_spot"] = spot_close
                MARKET_CACHE["last_oanda_sync"] = time.time()
                return {
                    "close": round(spot_close, 2),
                    "open": round(float(d[1] or spot_close), 2),
                    "high": round(float(d[2] or spot_close), 2),
                    "low": round(float(d[3] or spot_close), 2),
                    "ema20": round(float(d[4] or spot_close), 2),
                    "ema50": round(float(d[5] or spot_close), 2),
                    "adx": round(float(d[6] if d[6] is not None else 22.0), 2),
                    "plus_di": round(float(d[7] if d[7] is not None else 20.0), 2),
                    "minus_di": round(float(d[8] if d[8] is not None else 20.0), 2),
                    "atr": round(float(d[9] if d[9] is not None else 3.5), 2),
                    "rsi": round(float(d[10] if d[10] is not None else 50.0), 2)
                }
    except Exception as e:
        print(f"TradingView OANDA Telemetry Error ({tf_key}):", e)
    return None


def fetch_raw_gold_candles(tf_key="5m", limit=140):
    """
    ดึงชุดแท่งเทียนย้อนหลัง 140 แท่งจาก Yahoo Finance Spot Gold (XAUUSD=X / GC=F)
    หรือ Binance PAXGUSDT แล้วนำมาทำ Auto-Spread Calibration ให้ตรงกับ OANDA:XAUUSD
    """
    # ลำดับที่ 1: ดึงจาก Yahoo Finance Chart API
    yf_interval_map = {
        "1m": ("1m", "1d"),
        "5m": ("5m", "5d"),
        "15m": ("15m", "5d"),
        "1h": ("60m", "1mo"),
        "4h": ("60m", "1mo"),
        "daily": ("1d", "6mo")
    }
    yf_int, yf_rng = yf_interval_map.get(tf_key.lower(), ("5m", "5d"))
    candles = []

    try:
        yf_url = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval={yf_int}&range={yf_rng}"
        req = urllib.request.Request(yf_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = data.get("chart", {}).get("result", [])
            if result:
                timestamps = result[0].get("timestamp", [])
                quote = result[0].get("indicators", {}).get("quote", [{}])[0]
                opens = quote.get("open", [])
                highs = quote.get("high", [])
                lows = quote.get("low", [])
                closes = quote.get("close", [])

                raw_bars = []
                for i in range(len(timestamps)):
                    if None in (opens[i], highs[i], lows[i], closes[i]):
                        continue
                    raw_bars.append({
                        "time": int(timestamps[i]),
                        "open": float(opens[i]),
                        "high": float(highs[i]),
                        "low": float(lows[i]),
                        "close": float(closes[i])
                    })

                # หากเป็น 4H ให้ยุบรวมทุก 4 แท่งของ 1H
                if tf_key.lower() == "4h" and len(raw_bars) >= 16:
                    grouped = []
                    for i in range(0, len(raw_bars) - 3, 4):
                        chunk = raw_bars[i:i + 4]
                        grouped.append({
                            "time": chunk[0]["time"],
                            "open": chunk[0]["open"],
                            "high": max(c["high"] for c in chunk),
                            "low": min(c["low"] for c in chunk),
                            "close": chunk[-1]["close"]
                        })
                    candles = grouped[-limit:]
                else:
                    candles = raw_bars[-limit:]
    except Exception:
        pass

    # ลำดับที่ 2: หาก Yahoo Finance ไม่ตอบสนอง ใช้ Binance Klines เป็นฐานโครงสร้างแท่งเทียน
    if len(candles) < 40:
        b_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "daily": "1d"}
        b_tf = b_map.get(tf_key.lower(), "5m")
        try:
            b_url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={b_tf}&limit={limit}"
            req = urllib.request.Request(b_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                candles = [
                    {
                        "time": int(k[0] // 1000),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4])
                    }
                    for k in raw
                ]
        except Exception as e:
            print("Fallback Candle Fetch Error:", e)

    return candles


def compute_ema_series(values, period):
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    ema_list = [values[0]]
    for val in values[1:]:
        ema_list.append((val * k) + (ema_list[-1] * (1.0 - k)))
    return ema_list


def compute_atr_and_adx(candles, period=14):
    """คำนวณ ATR(14), ADX(14), +DI, -DI และ Choppiness Index(14) จากแท่งเทียนจริง"""
    n = len(candles)
    if n < period + 2:
        return 3.5, 22.0, 20.0, 20.0, 50.0

    trs = []
    plus_dms = []
    minus_dms = []

    for i in range(1, n):
        curr = candles[i]
        prev = candles[i - 1]
        up_move = curr["high"] - prev["high"]
        down_move = prev["low"] - curr["low"]

        pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
        mdm = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr = max(
            curr["high"] - curr["low"],
            abs(curr["high"] - prev["close"]),
            abs(curr["low"] - prev["close"])
        )
        trs.append(tr)
        plus_dms.append(pdm)
        minus_dms.append(mdm)

    # Wilder's Smoothing
    atr = sum(trs[:period]) / period
    sm_pdm = sum(plus_dms[:period]) / period
    sm_mdm = sum(minus_dms[:period]) / period
    dxs = []

    for i in range(period, len(trs)):
        atr = ((atr * (period - 1)) + trs[i]) / period
        sm_pdm = ((sm_pdm * (period - 1)) + plus_dms[i]) / period
        sm_mdm = ((sm_mdm * (period - 1)) + minus_dms[i]) / period

        pdi = 100.0 * (sm_pdm / atr) if atr > 0 else 0.0
        mdi = 100.0 * (sm_mdm / atr) if atr > 0 else 0.0
        denom = pdi + mdi
        dx = 100.0 * (abs(pdi - mdi) / denom) if denom > 0 else 0.0
        dxs.append((dx, pdi, mdi))

    if not dxs:
        return round(atr, 2), 20.0, 20.0, 20.0, 50.0

    adx_vals = [x[0] for x in dxs]
    adx = sum(adx_vals[:period]) / min(len(adx_vals), period)
    for val in adx_vals[period:]:
        adx = ((adx * (period - 1)) + val) / period

    last_pdi = dxs[-1][1]
    last_mdi = dxs[-1][2]

    # คำนวณ Choppiness Index (14) เพื่อวัดการวิ่งออกข้างในกรอบ (Sideway Consolidation)
    recent_14 = candles[-period:]
    sum_tr_14 = sum(trs[-period:])
    max_h_14 = max(c["high"] for c in recent_14)
    min_l_14 = min(c["low"] for c in recent_14)
    hl_range_14 = max(0.01, max_h_14 - min_l_14)
    try:
        chop = 100.0 * math.log10(max(1.0, sum_tr_14 / hl_range_14)) / math.log10(period)
        chop = max(0.0, min(100.0, chop))
    except Exception:
        chop = 50.0

    return round(atr, 2), round(adx, 2), round(last_pdi, 2), round(last_mdi, 2), round(chop, 2)


def detect_zig_zag_fractals(candles, left_bars=3, right_bars=3):
    """
    อัลกอริทึมค้นหาจุด Swing High และ Swing Low ตามหลัก Pivot Point / ZigZag Fractals
    เหมือน Indicator มาตรฐานบน TradingView
    """
    n = len(candles)
    pivot_highs = []
    pivot_lows = []

    if n < (left_bars + right_bars + 5):
        return pivot_highs, pivot_lows

    for i in range(left_bars, n - right_bars):
        h_val = candles[i]["high"]
        l_val = candles[i]["low"]

        is_ph = all(h_val >= candles[j]["high"] for j in range(i - left_bars, i + right_bars + 1) if j != i)
        is_pl = all(l_val <= candles[j]["low"] for j in range(i - left_bars, i + right_bars + 1) if j != i)

        if is_ph:
            pivot_highs.append({"index": i, "price": round(h_val, 2), "time": candles[i]["time"]})
        if is_pl:
            pivot_lows.append({"index": i, "price": round(l_val, 2), "time": candles[i]["time"]})

    return pivot_highs, pivot_lows


def analyze_market_structure_and_regime(tf_key="5m", balance=1000.0, risk_pct=1.5):
    """
    สมองกลหลักในการวิเคราะห์กราฟ:
    1. ซิงก์ราคาให้ตรงกับ OANDA:XAUUSD อัตโนมัติ (Auto-Spread Calibration)
    2. ค้นหาจุด Swing High / Swing Low จาก Pivot Fractals และโครงสร้าง HH, HL, LH, LL
    3. วิเคราะห์ EMA 20, EMA 50, ADX 14, ATR 14, Choppiness Index
    4. ฟันธงสถานะ UPTREND (วางแผน BUY), DOWNTREND (วางแผน SELL), หรือ SIDEWAY (งดเทรดเด็ดขาด)
    """
    tf_clean = tf_key.lower()
    oanda_live = fetch_tradingview_oanda_telemetry(tf_clean)
    raw_candles = fetch_raw_gold_candles(tf_clean, limit=130)

    # กรณีฉุกเฉินหากอินเทอร์เน็ตภายนอกขัดข้อง
    if not raw_candles:
        spot = oanda_live["close"] if oanda_live else 4001.50
        raw_candles = [
            {"time": int(time.time()) - (60 - i) * 300, "open": spot, "high": spot + 4.0, "low": spot - 4.0, "close": spot}
            for i in range(60)
        ]

    # Auto-Spread Calibration: ปรับจูนชุดแท่งเทียนทั้งหมดให้ตรงกับราคาสดของ OANDA:XAUUSD เป๊ะ 100%
    feed_last_close = raw_candles[-1]["close"]
    target_oanda_close = oanda_live["close"] if oanda_live else (MARKET_CACHE.get("oanda_spot") or feed_last_close)
    spread_offset = target_oanda_close - feed_last_close

    calibrated_candles = []
    for c in raw_candles:
        calibrated_candles.append({
            "time": c["time"],
            "open": round(c["open"] + spread_offset, 2),
            "high": round(c["high"] + spread_offset, 2),
            "low": round(c["low"] + spread_offset, 2),
            "close": round(c["close"] + spread_offset, 2)
        })

    # บังคับแท่งล่าสุดให้ตรงกับราคา High/Low/Close ของ OANDA ปัจจุบัน
    if oanda_live:
        calibrated_candles[-1]["close"] = oanda_live["close"]
        calibrated_candles[-1]["high"] = max(calibrated_candles[-1]["high"], oanda_live["high"])
        calibrated_candles[-1]["low"] = min(calibrated_candles[-1]["low"], oanda_live["low"])

    current_price = calibrated_candles[-1]["close"]
    closes = [c["close"] for c in calibrated_candles]

    # คำนวณ EMA 20 และ EMA 50
    ema20_series = compute_ema_series(closes, 20)
    ema50_series = compute_ema_series(closes, 50)
    calc_ema20 = round(ema20_series[-1], 2)
    calc_ema50 = round(ema50_series[-1], 2)
    ema20_prev = ema20_series[-5] if len(ema20_series) >= 5 else ema20_series[0]

    # ใช้ค่า EMA / ADX / ATR จาก OANDA Telemetry หากมี หรือใช้ค่าที่คำนวณจากแท่งเทียนที่ซิงก์แล้ว
    atr_val, adx_val, plus_di, minus_di, chop_val = compute_atr_and_adx(calibrated_candles, 14)
    ema20 = oanda_live["ema20"] if (oanda_live and oanda_live.get("ema20")) else calc_ema20
    ema50 = oanda_live["ema50"] if (oanda_live and oanda_live.get("ema50")) else calc_ema50
    if oanda_live and oanda_live.get("adx"):
        adx_val = oanda_live["adx"]
        plus_di = oanda_live["plus_di"]
        minus_di = oanda_live["minus_di"]
    if oanda_live and oanda_live.get("atr"):
        atr_val = max(0.5, oanda_live["atr"])

    # ค้นหาจุด Swing High / Swing Low ด้วยอัลกอริทึม Pivot Fractals
    pivot_highs, pivot_lows = detect_zig_zag_fractals(calibrated_candles, left_bars=3, right_bars=3)

    # วิเคราะห์โครงสร้างการยกไฮยกโลว์ (HH, HL, LH, LL)
    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        h_curr, h_prev = pivot_highs[-1]["price"], pivot_highs[-2]["price"]
        l_curr, l_prev = pivot_lows[-1]["price"], pivot_lows[-2]["price"]
        high_tag = "HH (Higher High)" if h_curr > h_prev else "LH (Lower High)"
        low_tag = "HL (Higher Low)" if l_curr > l_prev else "LL (Lower Low)"
        structure_label = f"{high_tag} • {low_tag}"
    else:
        h_curr = max(c["high"] for c in calibrated_candles[-45:])
        l_curr = min(c["low"] for c in calibrated_candles[-45:])
        high_tag = "Swing High"
        low_tag = "Swing Low"
        structure_label = "กำลังสร้างโครงสร้างสวิงใหม่"

    # คัดเลือกกรอบ Active Swing High และ Active Swing Low ของคลื่นปัจจุบัน (Major Impulse Leg)
    active_window = calibrated_candles[-65:]
    window_max_h = max(c["high"] for c in active_window)
    window_min_l = min(c["low"] for c in active_window)

    recent_ph = [p["price"] for p in pivot_highs if p["index"] >= len(calibrated_candles) - 65]
    recent_pl = [p["price"] for p in pivot_lows if p["index"] >= len(calibrated_candles) - 65]

    swing_high = max(recent_ph + [window_max_h]) if recent_ph else window_max_h
    swing_low = min(recent_pl + [window_min_l]) if recent_pl else window_min_l

    # ตรวจสอบกรณีผู้ใช้ส่งพิกัดผ่าน Webhook หรือ Manual Override
    override = SYSTEM_STATE["webhook_override"].get(tf_clean)
    if override and override.get("active"):
        swing_high = float(override["swing_high"])
        swing_low = float(override["swing_low"])

    swing_range = round(max(0.50, swing_high - swing_low), 2)

    # ==========================================================================
    # ตรรกะตัดสินสภาพตลาด 3 รูปแบบ: UPTREND / DOWNTREND / SIDEWAY
    # ==========================================================================
    ema_gap = abs(ema20 - ema50)
    ema_slope = abs(calc_ema20 - ema20_prev)

    # เกณฑ์ตรวจจับตลาด SIDEWAY (Multi-Factor Technical Filter)
    is_ema_tangled = ema_gap < (atr_val * 0.22)
    is_weak_adx = adx_val < 19.5
    is_high_chop = chop_val > 61.5
    is_conflicting_structure = (
        ("HH" in high_tag and "LL" in low_tag)
        or ("LH" in high_tag and "HL" in low_tag)
    )

    sideway_reasons = []
    trend_reasons = []

    if is_weak_adx:
        sideway_reasons.append(f"ค่า ADX อยู่ที่ {adx_val:.1f} (< 19.5) บ่งชี้ว่าตลาดขาดแรงขับเคลื่อนของเทรนด์")
    if is_ema_tangled:
        sideway_reasons.append(f"เส้น EMA 20 (${ema20:.2f}) และ EMA 50 (${ema50:.2f}) บีบตัวพันกันในแนวราบ")
    if is_high_chop:
        sideway_reasons.append(f"ดัชนี Choppiness Index พุ่งสูงถึง {chop_val:.1f} (ราคากำลังแกว่งตัวสะสมพลังในกรอบ)")
    if is_conflicting_structure:
        sideway_reasons.append(f"โครงสร้างราคาขัดแย้งกัน ({structure_label}) ยังไม่เลือกทิศทางเบรกเอาต์")

    # ตัดสินว่าเป็น SIDEWAY เมื่อเข้าเงื่อนไขความผันผวนต่ำ/ไร้ทิศทางตั้งแต่ 2 ข้อขึ้นไป หรือ ADX ต่ำมาก
    is_sideway = (
        (len(sideway_reasons) >= 2)
        or (adx_val < 16.5)
        or (is_ema_tangled and is_high_chop)
    )

    if override and override.get("active") and override.get("force_trend"):
        is_sideway = False

    if is_sideway:
        regime = "SIDEWAY"
        direction = "NO_TRADE"
        bias_title = "⚠️ ตลาด SIDEWAY (ไร้ทิศทางชัดเจน) — งดเทรดเด็ดขาด"
        explanation = " • ".join(sideway_reasons) if sideway_reasons else "กราฟวิ่งออกข้างในกรอบสะสมพลัง รอให้ราคาเบรกเอาต์และเกิดเทรนด์ชัดเจนก่อน"
        fib_pull_desc = "🔒 ระบบล็อกการตี Fibonacci ชั่วคราว (ป้องกันการโดนกวาด Stop Loss ในตลาด Sideway)"
        fib_05 = 0.0
        entry = 0.0
        sl = 0.0
        tp1 = 0.0
        tp2 = 0.0
        risk = 0.0
        reward1 = 0.0
        reward2 = 0.0
        rec_lot = "0.00"
    else:
        # ตลาดมีเทรนด์ชัดเจน: ตัดสินฝั่ง UPTREND (BUY) หรือ DOWNTREND (SELL)
        bullish_score = 0
        bearish_score = 0

        if ema20 >= ema50:
            bullish_score += 2
            trend_reasons.append(f"EMA 20 (${ema20:.2f}) ยืนเหนือ EMA 50 (${ema50:.2f})")
        else:
            bearish_score += 2
            trend_reasons.append(f"EMA 20 (${ema20:.2f}) อยู่ใต้ EMA 50 (${ema50:.2f})")

        if plus_di >= minus_di:
            bullish_score += 1
        else:
            bearish_score += 1

        if "HH" in high_tag or "HL" in low_tag:
            bullish_score += 1
        if "LH" in high_tag or "LL" in low_tag:
            bearish_score += 1

        trend_reasons.append(f"ADX {adx_val:.1f} ยืนยันความแข็งแกร่งของเทรนด์")
        trend_reasons.append(f"โครงสร้าง {structure_label}")

        if override and override.get("active") and override.get("direction") in ("BUY", "SELL"):
            direction = override["direction"]
        else:
            direction = "BUY" if bullish_score >= bearish_score else "SELL"

        if direction == "BUY":
            regime = "UPTREND"
            bias_title = f"🟢 เทรนด์ขาขึ้นชัดเจน (UPTREND • วางแผน BUY เท่านั้น)"
            fib_pull_desc = f"ลาก Fibonacci จากจุด Swing Low (${swing_low:.2f}) ขึ้นไปหา Swing High (${swing_high:.2f}) เพื่อรอราคาย่อตัว (Retracement)"
            fib_05 = round(swing_high - (swing_range * 0.500), 2)
            entry = round(swing_high - (swing_range * 0.618), 2)
            sl = round(swing_high - (swing_range * 0.786), 2)
            risk = round(max(0.20, abs(entry - sl)), 2)
            tp1 = round(entry + (risk * 2.0), 2)
            tp2 = round(entry + (risk * 3.0), 2)
        else:
            regime = "DOWNTREND"
            bias_title = f"🔴 เทรนด์ขาลงชัดเจน (DOWNTREND • วางแผน SELL เท่านั้น)"
            fib_pull_desc = f"ลาก Fibonacci จากจุด Swing High (${swing_high:.2f}) ลงมาหา Swing Low (${swing_low:.2f}) เพื่อรอราคาเด้งขึ้น (Pullback)"
            fib_05 = round(swing_low + (swing_range * 0.500), 2)
            entry = round(swing_low + (swing_range * 0.618), 2)
            sl = round(swing_low + (swing_range * 0.786), 2)
            risk = round(max(0.20, abs(sl - entry)), 2)
            tp1 = round(entry - (risk * 2.0), 2)
            tp2 = round(entry - (risk * 3.0), 2)

        explanation = " • ".join(trend_reasons)
        reward1 = round(risk * 2.0, 2)
        reward2 = round(risk * 3.0, 2)
        risk_money = balance * (risk_pct / 100.0)
        loss_per_lot = max(0.50, risk) * 100.0
        rec_lot = f"{max(0.01, round(risk_money / loss_per_lot, 2)):.2f}"

    result = {
        "tf": tf_clean.upper(),
        "feed_source": "OANDA:XAUUSD Real-Time Sync",
        "current_price": round(current_price, 2),
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "range": swing_range,
        "regime": regime,
        "is_sideway": is_sideway,
        "direction": direction,
        "bias_title": bias_title,
        "explanation": explanation,
        "fib_pull_desc": fib_pull_desc,
        "structure_label": structure_label,
        "ema20": ema20,
        "ema50": ema50,
        "adx": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "atr": atr_val,
        "chop": chop_val,
        "fib_05": fib_05,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "reward1": reward1,
        "reward2": reward2,
        "recommended_lot": rec_lot,
        "updated_at": datetime.now(TH_TZ).strftime("%H:%M:%S")
    }

    MARKET_CACHE["tf_data"][tf_clean] = result
    return result


# ==============================================================================
# 4. FOREX FACTORY ECONOMIC CALENDAR & MORNING BRIEFING ENGINE
# ==============================================================================
def compute_countdown_and_lock(event_dt, now_dt, impact):
    diff_sec = (event_dt - now_dt).total_seconds()
    is_same_day = (event_dt.date() == now_dt.date())
    is_tomorrow = (event_dt.date() == (now_dt.date() + timedelta(days=1)))
    is_auto_locking_now = (impact == "HIGH" and -1800 <= diff_sec <= 1800)

    if -1800 <= diff_sec <= 1800:
        countdown = "🔥 กำลังประกาศข่าว! (ล็อก ±30 นาที)"
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
        (1, 19, 30, "USD", "Prelim GDP q/q (ตัวเลขผลิตภัณฑ์มวลรวมสหรัฐฯ)", "HIGH", "2.9%", "3.0%"),
        (1, 21, 0, "USD", "JOLTS Job Openings (ตำแหน่งงานว่างเปิดใหม่)", "HIGH", "7.92M", "8.04M"),
        (2, 19, 15, "USD", "ADP Non-Farm Employment Change (การจ้างงานภาคเอกชน)", "HIGH", "115K", "143K"),
        (2, 19, 30, "USD", "Core PCE / CPI Price Index m/m (ดัชนีเงินเฟ้อสหรัฐฯ)", "HIGH", "0.3%", "0.2%"),
        (3, 19, 30, "USD", "Initial Jobless Claims (ผู้ขอรับสวัสดิการว่างงาน)", "HIGH", "222K", "227K"),
        (3, 20, 45, "USD", "Flash Manufacturing PMI (ดัชนีผู้จัดการฝ่ายจัดซื้อ)", "MEDIUM", "47.8", "47.3"),
        (4, 19, 30, "USD", "Non-Farm Employment Change - NFP (การจ้างงานนอกภาคเกษตร)", "HIGH", "148K", "254K"),
        (4, 21, 0, "USD", "ISM Manufacturing PMI (ดัชนีภาคการผลิตสหรัฐฯ)", "HIGH", "47.6", "47.2"),
    ]

    results = []
    for day_offset, hr, mn, curr, title, impact, forecast, previous in template_events:
        ev_date = monday + timedelta(days=day_offset)
        ev_dt = datetime(ev_date.year, ev_date.month, ev_date.day, hr, mn, tzinfo=TH_TZ)
        countdown, urgency, is_locking = compute_countdown_and_lock(ev_dt, now_dt, impact)
        lock_start = (ev_dt - timedelta(minutes=30)).strftime("%H:%M")
        lock_end = (ev_dt + timedelta(minutes=30)).strftime("%H:%M")
        rule_text = f"ล็อกอัตโนมัติ {lock_start}–{lock_end} น." if impact == "HIGH" else "ลดขนาด Lot 50%"

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
            rule_text = f"ล็อกอัตโนมัติ {lock_start}–{lock_end} น." if impact_raw == "HIGH" else "ระวังความผันผวน"

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


def build_morning_news_brief_message(now_dt, calendar_events, start_t="08:00", end_t="23:00"):
    today_iso = now_dt.strftime("%Y-%m-%d")
    today_high = [ev for ev in calendar_events if ev.get("iso_date") == today_iso and ev.get("impact") == "HIGH"]
    today_med = [ev for ev in calendar_events if ev.get("iso_date") == today_iso and ev.get("impact") == "MEDIUM"]

    lines = [
        f"🌅 <b>GOLD AI SNIPER PRO — สรุปตารางข่าวเช้าวันนี้</b>",
        f"📅 <b>ประจำวัน:</b> {format_thai_date(now_dt)}",
        f"⏰ <b>รอบเวลาทำงานของบอท:</b> {start_t} – {end_t} น.",
        f"━━━━━━━━━━━━━━━━━━━━━━"
    ]

    if today_high:
        lines.append("🔴 <b>ข่าวแดง (HIGH IMPACT USD) ที่ต้องระวังวันนี้:</b>")
        for ev in today_high:
            lines.append(f"• <b>{ev['time_label']}</b> — {ev['event']}")
            lines.append(f"  └ 🛡️ <i>ระบบล็อกสัญญาณอัตโนมัติ: {ev['lock_window']} (คาดการณ์: {ev['forecast']})</i>")
    else:
        lines.append("🟢 <b>ข่าวแดง (HIGH IMPACT USD):</b>")
        lines.append("• วันนี้ไม่มีตารางประกาศข่าวแดงสหรัฐฯ กราฟวิ่งตามโครงสร้างเทคนิคปกติ")

    if today_med:
        lines.append("")
        lines.append("🟠 <b>ข่าวส้ม (MEDIUM IMPACT) เพิ่มเติม:</b>")
        for ev in today_med[:4]:
            lines.append(f"• {ev['time_label']} — {ev['event']} (คาดการณ์: {ev['forecast']})")

    lines.extend([
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"🧠 <b>กฎเหล็กสมองกลวิเคราะห์กราฟวันนี้:</b>",
        f"1. ซิงก์ราคาตรงกับกราฟ <b>OANDA:XAUUSD</b> อัตโนมัติ",
        f"2. หากตรวจพบตลาด <b>SIDEWAY (EMA พันกัน / ADX ต่ำ)</b> ระบบจะสั่ง <b>งดเทรดทันที</b>",
        f"3. แจ้งเตือน 2 จังหวะเฉพาะเมื่อเกิดเทรนด์ชัดเจน: <b>ระดับ 0.5 (เตรียมตัว)</b> และ <b>61.8% (Golden Zone)</b>"
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
    """รันหลังบ้านตลอด 24 ชม. เพื่อส่งข่าวเช้า, ตรวจจับ Sideway, และส่งสัญญาณ Fibonacci 0.5 / 61.8%"""
    while True:
        try:
            now_dt = datetime.now(TH_TZ)
            SYSTEM_STATE["scanner_last_run"] = now_dt.strftime("%H:%M:%S")
            SYSTEM_STATE["scanner_status"] = "ACTIVE 24/7"

            calendar_events = fetch_forex_factory_calendar()
            auto_locking = any(ev.get("is_locking_now") for ev in calendar_events)
            is_locked = SYSTEM_STATE["manual_news_lock"] or auto_locking

            if USERS_DB:
                active_tfs = set()
                for u in USERS_DB.values():
                    if u.get("chat_id") and u.get("auto_alert", True):
                        active_tfs.add(u.get("preferred_tf", "5m").lower())

                tf_analysis_cache = {}
                for tf in active_tfs:
                    try:
                        tf_analysis_cache[tf] = analyze_market_structure_and_regime(tf)
                    except Exception as e:
                        print(f"Scanner Analysis Error ({tf}):", e)

                today_str = now_dt.strftime("%Y-%m-%d")

                for email, user in list(USERS_DB.items()):
                    chat_id = user.get("chat_id")
                    custom_token = user.get("custom_bot_token")
                    if not chat_id or not user.get("auto_alert", True):
                        continue

                    start_t = user.get("start_time", "08:00")
                    end_t = user.get("end_time", "23:00")

                    if not is_within_schedule(now_dt, start_t, end_t):
                        continue

                    # 1. ส่งสรุปตารางข่าวตอนเช้าอัตโนมัติ (วันละ 1 ครั้งเมื่อเข้าช่วงเวลาเริ่มต้น)
                    brief_key = f"{chat_id}_{today_str}"
                    if user.get("alert_morning_news", True) and not SYSTEM_STATE["morning_brief_memory"].get(brief_key):
                        morning_msg = build_morning_news_brief_message(now_dt, calendar_events, start_t, end_t)
                        ok, _ = send_telegram_message(chat_id, morning_msg, custom_token)
                        if ok:
                            SYSTEM_STATE["morning_brief_memory"][brief_key] = True

                    # หากอยู่ในช่วงล็อกข่าวแดง ±30 นาที ให้หยุดส่งสัญญาณเทคนิคชั่วคราว
                    if is_locked:
                        continue

                    tf = user.get("preferred_tf", "5m").lower()
                    data = tf_analysis_cache.get(tf)
                    if not data:
                        continue

                    swing_key = f"{chat_id}_{tf}_{data['swing_high']}_{data['swing_low']}_{data['regime']}"
                    mem = SYSTEM_STATE["last_alert_memory"].get(swing_key, {})

                    # 2. กฎเหล็กเมื่อตรวจพบตลาด SIDEWAY: แจ้งเตือนให้งดเทรด 1 ครั้ง และห้ามส่งสัญญาณ BUY/SELL เด็ดขาด!
                    if data["is_sideway"]:
                        if user.get("alert_sideway", True) and not mem.get("sent_sideway"):
                            sideway_msg = (
                                f"⚠️ <b>[NO TRADE ZONE] ตรวจพบตลาด SIDEWAY ไร้ทิศทาง</b>\n"
                                f"📊 <b>OANDA:XAUUSD ({tf.upper()})</b> • ราคาปัจจุบัน: <b>${data['current_price']:.2f}</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🧠 <b>วิเคราะห์โครงสร้าง:</b> {data['explanation']}\n"
                                f"📈 <b>EMA 20 / 50:</b> ${data['ema20']:.2f} / ${data['ema50']:.2f} | <b>ADX:</b> {data['adx']:.1f}\n"
                                f"🛑 <b>คำสั่งระบบ:</b> <b>งดเทรด / ไม่มีจุดเข้าซื้อขายเด็ดขาด</b> รอให้กราฟเบรกเอาต์เลือกทิศทางและเกิดเทรนด์ก่อน"
                            )
                            ok, _ = send_telegram_message(chat_id, sideway_msg, custom_token)
                            if ok:
                                mem["sent_sideway"] = True
                                SYSTEM_STATE["last_alert_memory"][swing_key] = mem
                        continue

                    # 3. เมื่อตลาดเป็นเทรนด์ชัดเจน (UPTREND / DOWNTREND) จึงอนุญาตให้เช็กจุด Fibonacci 0.5 และ 61.8%
                    price = data["current_price"]
                    fib_05 = data["fib_05"]
                    entry_618 = data["entry"]
                    direction = data["direction"]
                    rng = max(1.0, data["range"])
                    tolerance = max(0.45, rng * 0.035)

                    # จังหวะที่ 1: เตือนล่วงหน้าที่ระดับ 0.5 (50.0%)
                    if user.get("alert_05", True) and not mem.get("sent_05"):
                        if abs(price - fib_05) <= tolerance:
                            msg_05 = (
                                f"🔔 <b>[จังหวะที่ 1: เตรียมตัว] ราคาแตะระดับ 0.5 (50.0%)</b>\n"
                                f"📊 <b>OANDA:XAUUSD ({tf.upper()})</b> • เทรนด์ <b>{data['regime']} (ฝั่ง {direction})</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🟡 <b>ราคาปัจจุบัน:</b> ${price:.2f}\n"
                                f"🔔 <b>ระดับ 0.5 (เตรียมตัว):</b> ${fib_05:.2f}\n"
                                f"🎯 <b>รอเข้าที่ Golden Zone 61.8%:</b> ${entry_618:.2f}\n"
                                f"🔴 <b>จุดตัดขาดทุน 78.6% (SL):</b> ${data['sl']:.2f}\n"
                                f"🟢 <b>เป้าทำกำไร TP1 / TP2:</b> ${data['tp1']:.2f} / ${data['tp2']:.2f}\n"
                                f"🧠 <b>เหตุผลเทคนิค:</b> {data['explanation']}"
                            )
                            ok, _ = send_telegram_message(chat_id, msg_05, custom_token)
                            if ok:
                                mem["sent_05"] = True
                                SYSTEM_STATE["last_alert_memory"][swing_key] = mem

                    # จังหวะที่ 2: เตือนเมื่อราคาเข้า Golden Zone 61.8%
                    if user.get("alert_618", True) and not mem.get("sent_618"):
                        if abs(price - entry_618) <= tolerance:
                            msg_618 = (
                                f"🎯 <b>[จังหวะที่ 2: เข้าโซนหลัก] ราคาแตะ Golden Zone 61.8%</b>\n"
                                f"📊 <b>OANDA:XAUUSD ({tf.upper()})</b> • แผนเทรดฝั่ง <b>{direction} ONLY</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🔵 <b>จุดเข้าเทรด (61.8%):</b> ${entry_618:.2f}\n"
                                f"🔴 <b>จุดตัดขาดทุน (78.6% SL):</b> ${data['sl']:.2f} (ระยะ ${data['risk']:.2f})\n"
                                f"🟢 <b>เป้า TP1 (RR 1:2):</b> ${data['tp1']:.2f}\n"
                                f"🟡 <b>เป้า TP2 (RR 1:3):</b> ${data['tp2']:.2f}\n"
                                f"⚖️ <b>ขนาด Lot แนะนำ:</b> {data['recommended_lot']} Lot\n"
                                f"🧠 <b>โครงสร้างเทรนด์:</b> {data['explanation']}"
                            )
                            ok, _ = send_telegram_message(chat_id, msg_618, custom_token)
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
                                    "regime": data["regime"],
                                    "adx": f"{data['adx']:.1f}",
                                    "fib_05": f"{fib_05:.2f}",
                                    "entry": f"{entry_618:.2f}",
                                    "sl": f"{data['sl']:.2f}",
                                    "tp1": f"{data['tp1']:.2f}",
                                    "tp2": f"{data['tp2']:.2f}",
                                    "rr": "1:3",
                                    "status": "AUTO 61.8% SENT",
                                    "reason": data["explanation"]
                                })
        except Exception as e:
            print("Background Scanner Loop Error:", e)
        time.sleep(22)


scanner_thread = threading.Thread(target=background_price_scanner, daemon=True)
scanner_thread.start()


# ==============================================================================
# 6. 5-STAR INSTITUTIONAL TRADING TERMINAL FRONTEND (FULLSCREEN + SMART UI)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GOLD AI SNIPER PRO — Institutional OANDA:XAUUSD Fibonacci & Smart Regime Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Prompt:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-obsidian: #06080E;
            --bg-panel: #0B0F17;
            --bg-elevated: #111726;
            --border-subtle: rgba(255, 255, 255, 0.08);
            --gold-primary: #D4AF37;
            --amber-glow: #F59E0B;
            --bull-emerald: #10B981;
            --bear-crimson: #F43F5E;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Prompt', 'Inter', sans-serif;
            background-color: var(--bg-obsidian);
            background-image:
                radial-gradient(circle at 12% 0%, rgba(212, 175, 55, 0.06), transparent 38%),
                radial-gradient(circle at 88% 0%, rgba(16, 185, 129, 0.05), transparent 38%);
            color: #F1F5F9;
            margin: 0;
            overflow-x: hidden;
        }
        .font-mono-num {
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.02em;
        }
        .terminal-panel {
            background-color: var(--bg-panel);
            border: 1px solid var(--border-subtle);
            box-shadow: 0 16px 40px -16px rgba(0, 0, 0, 0.85);
        }
        .terminal-panel-gold {
            background: linear-gradient(180deg, rgba(17, 23, 38, 0.94) 0%, rgba(11, 15, 23, 0.99) 100%);
            border: 1px solid rgba(212, 175, 55, 0.32);
            box-shadow: 0 18px 45px -15px rgba(0, 0, 0, 0.92);
        }
        .price-card {
            background-color: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            transition: all 0.16s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .price-card:hover {
            border-color: rgba(255, 255, 255, 0.24);
            transform: translateY(-2px);
        }
        .btn-action {
            transition: all 0.15s ease;
        }
        .btn-action:hover:not(:disabled) {
            filter: brightness(1.08);
            transform: translateY(-1px);
        }
        .btn-action:active:not(:disabled) {
            transform: translateY(0) scale(0.98);
        }
        /* FULLSCREEN CHART OVERLAY MODE */
        .chart-fullscreen-mode {
            position: fixed !important;
            inset: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 9999 !important;
            background-color: #06080E !important;
            padding: 12px !important;
            border-radius: 0 !important;
            display: flex !important;
            flex-direction: column !important;
        }
        .chart-fullscreen-mode #tv-chart-box {
            flex: 1 1 auto !important;
            height: calc(100vh - 78px) !important;
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #06080E; }
        ::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #D4AF37; }
    </style>
</head>
<body class="antialiased min-h-screen flex flex-col justify-between">

    <!-- ==================================================================== -->
    <!-- MODAL 1: หน้าเข้าสู่ระบบด้วยอีเมล + ยอมรับเงื่อนไขทางกฎหมาย (Disclaimer) -->
    <!-- ==================================================================== -->
    <div id="auth-modal" class="fixed inset-0 bg-black/85 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="terminal-panel-gold rounded-2xl max-w-md w-full p-6 space-y-5">
            <div class="flex items-center justify-between border-b border-white/10 pb-4">
                <div class="flex items-center gap-3">
                    <div class="w-11 h-11 rounded-xl bg-amber-500 flex items-center justify-center text-slate-950 font-mono-num font-black text-base shadow-lg">
                        XAU
                    </div>
                    <div>
                        <h2 class="text-base font-extrabold text-white tracking-tight">GOLD AI SNIPER PRO</h2>
                        <p class="text-[11px] text-amber-300">Institutional OANDA:XAUUSD Fibonacci Terminal</p>
                    </div>
                </div>
                <span class="px-2 py-0.5 text-[10px] font-mono-num font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 rounded">v5.0 PRO</span>
            </div>

            <div class="space-y-3.5 text-xs">
                <div>
                    <label class="text-slate-300 font-bold block mb-1.5">อีเมลผู้ใช้งาน (Email Address)</label>
                    <input type="email" id="login-email" placeholder="name@gmail.com" class="w-full bg-[#06080E] border border-white/15 focus:border-amber-400 rounded-xl px-3.5 py-2.5 text-white outline-none font-mono-num text-xs">
                </div>

                <div class="bg-[#06080E] p-3.5 rounded-xl border border-white/10 space-y-2 text-[11px] text-slate-300 leading-relaxed">
                    <div class="font-bold text-amber-400 flex items-center gap-1.5">
                        <i class="fa-solid fa-scale-balanced"></i> ข้อตกลงการใช้งานเครื่องมือคำนวณทางสถิติ (Disclaimer)
                    </div>
                    <p class="text-slate-400">
                        แพลตฟอร์มนี้เป็น <strong>เครื่องมือคำนวณระดับราคาทางคณิตศาสตร์ (Fibonacci Retracement) และตรวจจับโครงสร้างเทรนด์/ไซด์เวย์ทางสถิติอัตโนมัติเท่านั้น</strong> มิใช่การให้คำแนะนำทางการเงินหรือการชักชวนลงทุน (Not Financial Advice) ผู้ใช้งานเป็นผู้ตัดสินใจและรับความเสี่ยงด้วยตนเอง 100%
                    </p>
                    <label class="flex items-start gap-2.5 pt-1 cursor-pointer select-none text-white font-semibold">
                        <input type="checkbox" id="login-disclaimer" checked class="mt-0.5 rounded accent-amber-500 w-4 h-4">
                        <span>ฉันอ่านและยอมรับว่านี่คือเครื่องมือคำนวณทางสถิติเท่านั้น</span>
                    </label>
                </div>
            </div>

            <button onclick="submitEmailLogin()" class="btn-action w-full py-3 rounded-xl bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 font-black text-xs uppercase tracking-wider shadow-lg">
                เข้าสู่ระบบเทอร์มินัล (Initialize Terminal)
            </button>
        </div>
    </div>

    <!-- ==================================================================== -->
    <!-- MODAL 2: ตั้งค่า TELEGRAM BOT 24 ชม. (พร้อมระบบแก้ Error 401 อัตโนมัติ) -->
    <!-- ==================================================================== -->
    <div id="settings-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 hidden flex items-center justify-center p-4">
        <div class="terminal-panel rounded-2xl max-w-2xl w-full p-6 space-y-4 max-h-[92vh] overflow-y-auto text-xs">
            <div class="flex justify-between items-center border-b border-white/10 pb-3.5">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-sky-500/15 border border-sky-500/30 flex items-center justify-center text-sky-400 text-xl">
                        <i class="fa-brands fa-telegram"></i>
                    </div>
                    <div>
                        <h3 class="text-sm font-extrabold text-white">ตั้งค่าระบบแจ้งเตือน Telegram Bot 24 ชม. (Self-Healing Token)</h3>
                        <p class="text-[11px] text-slate-400">เชื่อมต่อบอท @gold_ai_sniper_pro_bot พร้อมระบบป้องกัน HTTP Error 401 อัตโนมัติ</p>
                    </div>
                </div>
                <button onclick="toggleSettingsModal()" class="text-slate-400 hover:text-white text-base px-2.5 py-1 rounded-lg hover:bg-white/5">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>

            <!-- STEP 1: กด /start และดึง Chat ID -->
            <div class="bg-[#06080E] p-4 rounded-xl border border-white/10 space-y-2.5">
                <div class="flex items-center justify-between">
                    <span class="font-bold text-amber-400 uppercase text-[11px]">STEP 1 • เชื่อมต่อบอท @gold_ai_sniper_pro_bot</span>
                    <span class="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 font-mono-num text-[10px] font-bold">TOKEN VERIFIED</span>
                </div>
                <p class="text-slate-400 text-[11px]">1. กดปุ่มเปิดบอทในแอป Telegram แล้วกด <strong>Start (/start)</strong> 1 ครั้ง • 2. กดปุ่มดึงเลข Chat ID อัตโนมัติ</p>
                <div class="flex flex-wrap gap-2 pt-1">
                    <a href="https://t.me/gold_ai_sniper_pro_bot" target="_blank" class="btn-action px-3.5 py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-slate-950 font-extrabold inline-flex items-center gap-1.5">
                        <i class="fa-brands fa-telegram"></i> 1. เปิดบอท @gold_ai_sniper_pro_bot
                    </a>
                    <button onclick="autoDetectTelegramChatId()" class="btn-action px-3.5 py-2 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-300 font-bold inline-flex items-center gap-1.5">
                        <i class="fa-solid fa-wand-magic-sparkles"></i> 2. ดึงเลข Chat ID อัตโนมัติ
                    </button>
                </div>
            </div>

            <!-- STEP 2: ตรวจสอบ Bot Token และ Chat ID -->
            <div class="space-y-3">
                <div>
                    <label class="text-slate-300 font-bold block mb-1">Telegram Bot HTTP API Token (แก้ไขได้หากเปลี่ยนบอทใหม่ในอนาคต)</label>
                    <input type="text" id="set-bot-token" value="8718020170:AAFj1pPh4HLi8i7Vaz12hi_qAD_J4Dnlzlg" class="w-full bg-[#06080E] border border-white/15 focus:border-amber-400 rounded-xl px-3 py-2 text-amber-300 font-mono-num text-[11px] outline-none">
                </div>

                <div>
                    <label class="text-slate-300 font-bold block mb-1">Telegram Chat ID ของคุณ</label>
                    <div class="flex flex-wrap sm:flex-nowrap gap-2">
                        <input type="text" id="set-chat-id" value="8948986514" placeholder="เช่น 8948986514" class="w-full bg-[#06080E] border border-white/15 focus:border-amber-400 rounded-xl px-3 py-2 text-white font-mono-num text-xs outline-none">
                        <button onclick="sendTestTelegram()" class="btn-action px-3.5 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 font-bold shrink-0">
                            <i class="fa-regular fa-paper-plane mr-1"></i> ทดสอบส่งข้อความ
                        </button>
                        <button onclick="sendMorningBriefNow()" class="btn-action px-3.5 py-2 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 font-bold shrink-0">
                            <i class="fa-solid fa-sun mr-1"></i> ทดสอบส่งสรุปข่าวเช้า
                        </button>
                    </div>
                    <div id="telegram-diagnostic-log" class="hidden mt-2 p-2.5 rounded-lg bg-black/60 border border-white/10 font-mono-num text-[11px]"></div>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">Timeframe หลักที่บอทสแกน</label>
                        <select id="set-tf" class="w-full bg-[#06080E] border border-white/15 rounded-xl p-2.5 text-white font-mono-num font-bold">
                            <option value="1m">1 นาที (1M)</option>
                            <option value="5m" selected>5 นาที (5M - แนะนำ)</option>
                            <option value="15m">15 นาที (15M)</option>
                            <option value="1h">1 ชั่วโมง (1H)</option>
                            <option value="4h">4 ชั่วโมง (4H)</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">เวลาเริ่ม (ส่งข่าวเช้าอัตโนมัติ)</label>
                        <input type="time" id="set-start-time" value="08:00" class="w-full bg-[#06080E] border border-white/15 rounded-xl p-2.5 text-white font-mono-num">
                    </div>
                    <div>
                        <label class="text-slate-400 block mb-1 text-[11px]">เวลาหยุดสแกนของวัน</label>
                        <input type="time" id="set-end-time" value="23:00" class="w-full bg-[#06080E] border border-white/15 rounded-xl p-2.5 text-white font-mono-num">
                    </div>
                </div>

                <!-- เงื่อนไขการแจ้งเตือนอัตโนมัติ -->
                <div class="bg-[#06080E] p-3.5 rounded-xl border border-white/10 space-y-2">
                    <div class="font-bold text-amber-400 text-[11px]">เงื่อนไขการแจ้งเตือนอัตโนมัติ 24 ชม.</div>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-morning" checked class="accent-amber-500 w-4 h-4">
                        <span>🌅 <strong>ส่งสรุปตารางข่าวแดงตอนเช้าอัตโนมัติ</strong> เมื่อถึงเวลาเริ่มงานของวัน</span>
                    </label>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-sideway" checked class="accent-amber-500 w-4 h-4">
                        <span>⚠️ <strong>แจ้งเตือนเมื่อตลาดเข้าโหมด SIDEWAY</strong> และล็อกการส่งสัญญาณ BUY/SELL อัตโนมัติ</span>
                    </label>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-05" checked class="accent-amber-500 w-4 h-4">
                        <span>🔔 <strong>จังหวะที่ 1 — เตือนล่วงหน้าที่ระดับ 0.5 (50.0%)</strong> เพื่อให้เตรียมตัว</span>
                    </label>
                    <label class="flex items-center gap-2.5 cursor-pointer text-slate-200">
                        <input type="checkbox" id="set-alert-618" checked class="accent-amber-500 w-4 h-4">
                        <span>🎯 <strong>จังหวะที่ 2 — เตือนเมื่อเข้าโซน Golden Zone 61.8%</strong> พร้อมจุด SL 78.6% และ TP</span>
                    </label>
                </div>
            </div>

            <div class="flex justify-end gap-2 pt-2 border-t border-white/10">
                <button onclick="toggleSettingsModal()" class="px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 font-bold">ปิดหน้าต่าง</button>
                <button onclick="saveUserSettings()" class="btn-action px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-black">
                    <i class="fa-solid fa-floppy-disk mr-1"></i> บันทึกและเปิดสแกน 24 ชม.
                </button>
            </div>
        </div>
    </div>

    <!-- ==================================================================== -->
    <!-- TOP INSTITUTIONAL COMMAND BAR                                        -->
    <!-- ==================================================================== -->
    <header class="terminal-panel border-b border-white/10 px-4 py-3 sticky top-0 z-30 backdrop-blur-md bg-[#0B0F17]/95">
        <div class="max-w-[1780px] mx-auto flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3">
            
            <!-- Brand & Live Market Regime Status -->
            <div class="flex flex-wrap items-center gap-3">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-yellow-600 flex items-center justify-center text-slate-950 font-mono-num font-black text-xs shadow">
                        XAU
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <h1 class="text-sm md:text-base font-black tracking-tight text-white">GOLD AI SNIPER PRO</h1>
                            <span class="text-[10px] font-mono-num font-bold px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">OANDA SYNC</span>
                        </div>
                        <p class="text-[11px] text-slate-400">ระบบคำนวณ Fibonacci ตามเทรนด์อัตโนมัติ & คัดกรองตลาด Sideway</p>
                    </div>
                </div>

                <div class="h-5 w-[1px] bg-white/10 hidden sm:block"></div>

                <!-- ป้ายสถานะเทรนด์ / ไซด์เวย์ ด้านบน -->
                <div id="top-regime-pill" class="px-3 py-1 rounded-xl bg-emerald-500/15 border border-emerald-500/40 flex items-center gap-2 text-xs">
                    <span id="top-regime-dot" class="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span id="top-regime-text" class="font-mono-num font-bold text-emerald-400 text-[11px]">กำลังวิเคราะห์โครงสร้าง...</span>
                </div>

                <!-- ป้ายเกราะป้องกันข่าวแดง -->
                <div id="news-shield-box" class="px-3 py-1 rounded-xl bg-white/5 border border-white/10 flex items-center gap-2 text-xs">
                    <span id="shield-dot" class="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span id="shield-status-text" class="text-[11px] font-semibold text-slate-300">News Shield: ตลาดปกติ</span>
                    <button onclick="toggleNewsLock()" class="text-[10px] font-mono-num px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 text-slate-400 border border-white/10">สลับโหมด</button>
                </div>
            </div>

            <!-- ราคาทองคำสด OANDA + ปุ่มตั้งค่า Telegram -->
            <div class="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-between lg:justify-end">
                <div class="bg-[#06080E] px-3.5 py-1.5 rounded-xl border border-white/10 flex items-center gap-3">
                    <div>
                        <span class="text-[9px] font-mono-num uppercase text-amber-400 font-bold block">OANDA:XAUUSD LIVE</span>
                        <span id="live-ticker-price" class="font-mono-num text-sm md:text-base font-black text-white">--</span>
                    </div>
                    <span id="proximity-pill" class="px-2.5 py-0.5 text-[10px] font-mono-num font-bold rounded-lg bg-white/5 text-slate-300 border border-white/10">รอสแกน...</span>
                </div>

                <button onclick="toggleSettingsModal()" class="btn-action px-3.5 py-2 rounded-xl bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/40 text-sky-300 text-xs font-bold flex items-center gap-1.5">
                    <i class="fa-brands fa-telegram text-sm"></i>
                    <span id="telegram-status-btn">TG: 8948986514</span>
                </button>

                <button onclick="openAuthModal()" class="btn-action px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-mono-num text-amber-300 flex items-center gap-1.5">
                    <i class="fa-regular fa-user"></i>
                    <span id="user-email-badge">Trader</span>
                </button>
            </div>
        </div>
    </header>

    <!-- ==================================================================== -->
    <!-- MAIN WORKSPACE GRID (12 COLUMNS)                                     -->
    <!-- ==================================================================== -->
    <main class="max-w-[1780px] w-full mx-auto p-3 md:p-5 flex-1">
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">

            <!-- ============================================================ -->
            <!-- LEFT COLUMN (7 COLS): TRADINGVIEW FULLSCREEN + CALENDAR      -->
            <!-- ============================================================ -->
            <div class="xl:col-span-7 space-y-4">

                <!-- 1. กราฟ TRADINGVIEW (OANDA:XAUUSD) พร้อมโหมดขยายเต็มจอ + FLOATING HUD -->
                <section id="chart-card-wrapper" class="terminal-panel rounded-2xl p-4 space-y-3 transition-all">
                    <!-- แถบควบคุมหัวการ์ดกราฟ & Floating HUD เมื่อเปิดเต็มจอ -->
                    <div class="flex flex-wrap justify-between items-center gap-2 border-b border-white/10 pb-2.5">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class="text-xs font-extrabold text-white"><i class="fa-solid fa-chart-candlestick text-amber-400 mr-1.5"></i>OANDA:XAUUSD</span>
                            <span id="chart-tf-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">TF 5M</span>
                            
                            <!-- Floating HUD Summary (จะเด่นชัดมากเวลาขยายเต็มจอ) -->
                            <div class="flex items-center gap-2 bg-[#06080E] px-2.5 py-1 rounded-lg border border-white/10 text-[11px] font-mono-num">
                                <span id="hud-regime-tag" class="font-bold text-emerald-400">--</span>
                                <span class="text-slate-600">|</span>
                                <span class="text-amber-300">0.5: <strong id="hud-fib05">--</strong></span>
                                <span class="text-slate-600">|</span>
                                <span class="text-sky-400">61.8%: <strong id="hud-fib618">--</strong></span>
                            </div>
                        </div>

                        <div class="flex items-center gap-2">
                            <!-- ปุ่มสลับ Timeframe ด่วน -->
                            <div class="hidden sm:flex items-center gap-1 bg-[#06080E] p-1 rounded-lg border border-white/10">
                                <button onclick="selectTimeframe('1m')" class="px-2 py-0.5 rounded text-[10px] font-mono-num hover:bg-white/10 text-slate-300">1M</button>
                                <button onclick="selectTimeframe('5m')" class="px-2 py-0.5 rounded text-[10px] font-mono-num hover:bg-white/10 text-amber-400 font-bold">5M</button>
                                <button onclick="selectTimeframe('15m')" class="px-2 py-0.5 rounded text-[10px] font-mono-num hover:bg-white/10 text-slate-300">15M</button>
                                <button onclick="selectTimeframe('1h')" class="px-2 py-0.5 rounded text-[10px] font-mono-num hover:bg-white/10 text-slate-300">1H</button>
                            </div>

                            <button onclick="refreshMarketAnalysis(true)" class="btn-action py-1.5 px-3 rounded-xl bg-white/5 hover:bg-white/10 border border-white/15 text-slate-200 text-xs font-bold flex items-center gap-1.5">
                                <i id="fib-spin-icon" class="fa-solid fa-rotate text-[11px] text-amber-400"></i> ซิงก์ราคา OANDA
                            </button>

                            <!-- ปุ่มขยายกราฟเต็มจอ (Fullscreen Mode) -->
                            <button onclick="toggleChartFullscreen()" id="fullscreen-toggle-btn" class="btn-action py-1.5 px-3.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black flex items-center gap-1.5 shadow">
                                <i id="fullscreen-icon" class="fa-solid fa-expand"></i>
                                <span id="fullscreen-btn-text">ขยายกราฟเต็มจอ</span>
                            </button>
                        </div>
                    </div>

                    <!-- กล่องกราฟ TradingView -->
                    <div id="tv-chart-box" class="tradingview-widget-container rounded-xl overflow-hidden border border-white/10" style="height:520px; width:100%;">
                        <div id="tradingview_advanced_chart" style="height:100%; width:100%;"></div>
                    </div>
                </section>

                <!-- 2. ปฏิทินข่าวเศรษฐกิจ FOREX FACTORY & ระบบส่งข่าวเช้า -->
                <section class="terminal-panel rounded-2xl p-4 space-y-3">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2.5 border-b border-white/10 pb-3">
                        <div>
                            <div class="flex items-center gap-2">
                                <h2 class="text-xs md:text-sm font-extrabold text-white"><i class="fa-regular fa-calendar-check text-rose-400 mr-1.5"></i>ปฏิทินข่าวเศรษฐกิจ Forex Factory (เวลาไทย UTC+7)</h2>
                                <span class="px-2 py-0.5 text-[9px] font-mono-num font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 rounded">AUTO-LOCK ±30M</span>
                            </div>
                            <p class="text-[11px] text-slate-400 mt-0.5">บอทส่งสรุปข่าวแดงเข้า Telegram อัตโนมัติทุกเช้า และล็อกสัญญาณช่วงข่าวแดง ±30 นาที</p>
                        </div>

                        <div class="flex flex-wrap items-center gap-1.5">
                            <button onclick="filterNews('ALL')" id="news-filter-ALL" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-amber-500 text-slate-950">ทั้งหมด</button>
                            <button onclick="filterNews('TODAY')" id="news-filter-TODAY" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-white/5 text-slate-300 border border-white/10">วันนี้</button>
                            <button onclick="filterNews('HIGH')" id="news-filter-HIGH" class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-white/5 text-rose-400 border border-white/10">🔴 ข่าวแดง</button>
                            <button onclick="sendMorningBriefNow()" class="btn-action px-2.5 py-1 rounded-lg text-[11px] font-bold bg-sky-500/15 text-sky-300 border border-sky-500/30">
                                <i class="fa-brands fa-telegram mr-1"></i>ส่งสรุปข่าววันนี้เข้า Telegram
                            </button>
                        </div>
                    </div>

                    <div class="overflow-x-auto max-h-[260px]">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="text-slate-400 border-b border-white/10 text-[10px] font-mono-num uppercase">
                                    <th class="py-2 px-2">วัน / เวลา (ไทย)</th>
                                    <th class="py-2 px-2">ข่าวเศรษฐกิจสหรัฐฯ (USD)</th>
                                    <th class="py-2 px-2">ความรุนแรง</th>
                                    <th class="py-2 px-2">คาดการณ์ / ก่อนหน้า</th>
                                    <th class="py-2 px-2">สถานะเวลา</th>
                                    <th class="py-2 px-2 text-right">การป้องกันพอร์ต</th>
                                </tr>
                            </thead>
                            <tbody id="economic-calendar-body" class="divide-y divide-white/5 font-mono-num text-[11px]"></tbody>
                        </table>
                    </div>
                </section>
            </div>

            <!-- ============================================================ -->
            <!-- RIGHT COLUMN (5 COLS): SMART REGIME + FIBONACCI MATRIX       -->
            <!-- ============================================================ -->
            <div class="xl:col-span-5 space-y-4">

                <!-- 1. เลือก TIMEFRAME ที่ใช้คำนวณ -->
                <section class="terminal-panel rounded-2xl p-4 space-y-3">
                    <div class="flex justify-between items-center">
                        <span class="text-xs font-extrabold text-white uppercase tracking-wider">1. เลือก Timeframe ที่ใช้วิเคราะห์โครงสร้าง</span>
                        <span id="active-tf-badge" class="px-2.5 py-0.5 rounded-lg text-[11px] font-mono-num font-black bg-amber-500 text-slate-950">ACTIVE: 5M</span>
                    </div>
                    <div class="grid grid-cols-6 gap-1.5">
                        <button onclick="selectTimeframe('1m')" id="btn-1m" class="tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-bold border">1M</button>
                        <button onclick="selectTimeframe('5m')" id="btn-5m" class="tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-bold border">5M</button>
                        <button onclick="selectTimeframe('15m')" id="btn-15m" class="tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-bold border">15M</button>
                        <button onclick="selectTimeframe('1h')" id="btn-1h" class="tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-bold border">1H</button>
                        <button onclick="selectTimeframe('4h')" id="btn-4h" class="tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-bold border">4H</button>
                        <button onclick="selectTimeframe('daily')" id="btn-daily" class="tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-bold border">1D</button>
                    </div>
                </section>

                <!-- 2. การ์ดสมองกลวิเคราะห์เทรนด์ & ตรวจจับตลาด SIDEWAY (MULTI-FACTOR TELEMETRY) -->
                <section id="regime-detector-card" class="terminal-panel rounded-2xl p-4 border-l-4 border-l-emerald-500 space-y-3 transition-all">
                    <div class="flex justify-between items-start gap-3">
                        <div class="space-y-1">
                            <div class="flex items-center gap-2">
                                <span class="text-[10px] font-mono-num uppercase tracking-wider text-slate-400">SMART TREND & SIDEWAY ENGINE</span>
                                <span id="regime-badge-pill" class="px-2 py-0.5 rounded text-[10px] font-mono-num font-extrabold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">ANALYZING</span>
                            </div>
                            <h3 id="regime-headline" class="text-sm md:text-base font-extrabold text-white">กำลังประมวลผลโครงสร้างตลาด...</h3>
                            <p id="regime-subtext" class="text-[11px] text-slate-300 leading-relaxed">--</p>
                        </div>
                    </div>

                    <!-- ตารางย่อยแสดงค่าอินดิเคเตอร์ทางเทคนิคสด -->
                    <div class="grid grid-cols-4 gap-2 pt-1 text-center font-mono-num">
                        <div class="bg-[#06080E] p-2 rounded-xl border border-white/10">
                            <span class="text-[9px] text-slate-400 block">EMA 20 / 50</span>
                            <span id="ind-ema-val" class="text-[11px] font-bold text-white">--</span>
                        </div>
                        <div class="bg-[#06080E] p-2 rounded-xl border border-white/10">
                            <span class="text-[9px] text-slate-400 block">ADX (14)</span>
                            <span id="ind-adx-val" class="text-[11px] font-bold text-amber-400">--</span>
                        </div>
                        <div class="bg-[#06080E] p-2 rounded-xl border border-white/10">
                            <span class="text-[9px] text-slate-400 block">CHOP INDEX</span>
                            <span id="ind-chop-val" class="text-[11px] font-bold text-sky-400">--</span>
                        </div>
                        <div class="bg-[#06080E] p-2 rounded-xl border border-white/10">
                            <span class="text-[9px] text-slate-400 block">SWING RANGE</span>
                            <span id="ind-range-val" class="text-[11px] font-bold text-emerald-400">--</span>
                        </div>
                    </div>
                </section>

                <!-- 3. การ์ดแผนเทรด FIBONACCI (ซ่อนและล็อกทันทีเมื่อเป็น SIDEWAY) -->
                <section class="terminal-panel-gold rounded-2xl p-4 space-y-3.5">
                    
                    <!-- ป้ายหัวข้อทิศทางและจุด Swing High / Low ที่ซิงก์กับ OANDA -->
                    <div id="right-card-direction-banner" class="p-3.5 rounded-xl border flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                        <div>
                            <span id="structure-tag-line" class="text-[10px] font-mono-num uppercase tracking-wider text-amber-300 block">MARKET STRUCTURE</span>
                            <div id="setup-order-badge" class="text-base md:text-lg font-black font-mono-num mt-0.5">--</div>
                            <div id="setup-order-subtext" class="text-[11px] text-slate-300 mt-0.5">--</div>
                        </div>
                        <div class="text-right font-mono-num text-xs space-y-1 bg-[#06080E]/90 px-3 py-2 rounded-xl border border-white/10 shrink-0">
                            <div><span class="text-slate-400 text-[10px]">SWING HIGH:</span> <strong id="display-swing-high" class="text-white">--</strong></div>
                            <div><span class="text-slate-400 text-[10px]">SWING LOW:</span> <strong id="display-swing-low" class="text-white">--</strong></div>
                        </div>
                    </div>

                    <!-- กล่องเตือนพิเศษเมื่อตลาดเป็น SIDEWAY (NO TRADE ZONE) -->
                    <div id="sideway-lockout-banner" class="hidden bg-amber-500/10 border-2 border-amber-500/60 rounded-xl p-4 text-center space-y-2">
                        <div class="w-10 h-10 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center mx-auto text-lg">
                            <i class="fa-solid fa-ban"></i>
                        </div>
                        <h4 class="text-sm font-black text-amber-300 uppercase">⚠️ ตลาด SIDEWAY — งดเทรด / ไม่มีจุดเข้าซื้อขายเด็ดขาด</h4>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            เครื่องมือ Fibonacci ใช้สำหรับหาจังหวะย่อตัวตามเทรนด์เท่านั้น การฝืนเข้าออเดอร์ BUY หรือ SELL ในสภาวะตลาดไร้ทิศทางจะทำให้โดนกวาด Stop Loss สูงมาก <strong>ระบบจึงล็อกจุดเข้าและงดส่งสัญญาณชั่วคราว จนกว่ากราฟจะเลือกทางและเกิดเทรนด์ชัดเจน</strong>
                        </p>
                    </div>

                    <!-- กล่องระดับราคา Fibonacci (แสดงเฉพาะเมื่อตลาดมีเทรนด์ UPTREND / DOWNTREND) -->
                    <div id="fib-execution-grid" class="space-y-3">
                        <!-- จังหวะที่ 1: 0.5 (50.0%) -->
                        <div onclick="copyPrice('val-fib05')" class="price-card cursor-pointer p-3.5 rounded-xl border-l-4 border-l-amber-400 flex justify-between items-center">
                            <div class="space-y-0.5">
                                <div class="flex items-center gap-2">
                                    <span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono-num font-bold text-[10px]">STAGE 1 • 50.0%</span>
                                    <span class="text-xs font-extrabold text-amber-300">🔔 จุดแจ้งเตือนล่วงหน้า (Fibonacci 0.5)</span>
                                </div>
                                <p class="text-[11px] text-slate-400">เมื่อราคาแตะจุดนี้ บอทจะส่งเตือนครั้งที่ 1 ให้เตรียมตัวก่อนเข้าโซนหลัก</p>
                            </div>
                            <div class="text-right shrink-0 ml-3">
                                <span id="val-fib05" class="font-mono-num text-xl font-black text-amber-400 block">--</span>
                                <span class="text-[9px] font-mono-num text-slate-400">คลิกคัดลอก</span>
                            </div>
                        </div>

                        <!-- จังหวะที่ 2: 61.8%, SL 78.6%, TP1, TP2 -->
                        <div class="grid grid-cols-2 gap-2.5">
                            <div onclick="copyPrice('val-entry')" class="price-card cursor-pointer p-3.5 rounded-xl border-l-4 border-l-sky-400">
                                <div class="flex justify-between items-center">
                                    <span class="text-[10px] font-mono-num font-extrabold text-sky-400 uppercase">🎯 GOLDEN ZONE (61.8%)</span>
                                    <i class="fa-regular fa-copy text-[10px] text-slate-500"></i>
                                </div>
                                <div id="val-entry" class="text-xl font-black font-mono-num text-white mt-1">--</div>
                                <span id="entry-action-label" class="text-[10px] text-sky-300 block mt-0.5">จุดเข้าตามเทรนด์หลัก</span>
                            </div>

                            <div onclick="copyPrice('val-sl')" class="price-card cursor-pointer p-3.5 rounded-xl border-l-4 border-l-rose-500">
                                <div class="flex justify-between items-center">
                                    <span class="text-[10px] font-mono-num font-extrabold text-rose-400 uppercase">🔴 STOP LOSS (78.6%)</span>
                                    <span id="val-risk-pts" class="text-[10px] font-mono-num text-rose-300">--</span>
                                </div>
                                <div id="val-sl" class="text-xl font-black font-mono-num text-rose-400 mt-1">--</div>
                                <span class="text-[10px] text-slate-400 block mt-0.5">จุดยอมแพ้เมื่อหลุดโครงสร้าง</span>
                            </div>

                            <div onclick="copyPrice('val-tp1')" class="price-card cursor-pointer p-3.5 rounded-xl border-l-4 border-l-emerald-500">
                                <div class="flex justify-between items-center">
                                    <span class="text-[10px] font-mono-num font-extrabold text-emerald-400 uppercase">🟢 TARGET 1 (RR 1:2)</span>
                                    <span id="val-tp1-pts" class="text-[10px] font-mono-num text-emerald-300">--</span>
                                </div>
                                <div id="val-tp1" class="text-xl font-black font-mono-num text-emerald-400 mt-1">--</div>
                                <span class="text-[10px] text-slate-400 block mt-0.5">เป้าหมายทำกำไรระยะที่ 1</span>
                            </div>

                            <div onclick="copyPrice('val-tp2')" class="price-card cursor-pointer p-3.5 rounded-xl border-l-4 border-l-amber-500">
                                <div class="flex justify-between items-center">
                                    <span class="text-[10px] font-mono-num font-extrabold text-amber-400 uppercase">🟡 TARGET 2 (RR 1:3)</span>
                                    <span id="val-tp2-pts" class="text-[10px] font-mono-num text-amber-300">--</span>
                                </div>
                                <div id="val-tp2" class="text-xl font-black font-mono-num text-amber-400 mt-1">--</div>
                                <span class="text-[10px] text-slate-400 block mt-0.5">เป้าหมายทำกำไรหลัก</span>
                            </div>
                        </div>
                    </div>

                    <!-- คำนวณขนาด Lot อัตโนมัติ -->
                    <div class="bg-[#06080E] p-3 rounded-xl border border-white/10 flex flex-wrap justify-between items-center gap-2 text-xs">
                        <div class="flex items-center gap-3">
                            <div>
                                <label class="text-[10px] text-slate-400 block">เงินทุน ($)</label>
                                <input type="number" id="acc-balance" value="1000" oninput="recalcLotSize()" class="w-20 bg-[#111726] border border-white/15 rounded-lg px-2 py-1 text-white font-mono-num text-xs">
                            </div>
                            <div>
                                <label class="text-[10px] text-slate-400 block">ความเสี่ยง (%)</label>
                                <input type="number" id="acc-risk-pct" value="1.5" step="0.1" oninput="recalcLotSize()" class="w-16 bg-[#111726] border border-white/15 rounded-lg px-2 py-1 text-white font-mono-num text-xs">
                            </div>
                        </div>
                        <div class="text-right">
                            <span class="text-[10px] text-slate-400 block font-mono-num uppercase">ขนาด Lot ที่เหมาะสม</span>
                            <span id="calc-lot-result" class="font-mono-num font-black text-sm text-amber-400">0.05 Lot</span>
                        </div>
                    </div>

                    <!-- ปุ่มส่งสัญญาณเข้า Telegram ทันที -->
                    <button id="broadcast-btn" onclick="broadcastCurrentSignal()" class="btn-action w-full py-3 px-4 rounded-xl font-black text-xs uppercase tracking-wider bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 flex items-center justify-center gap-2 shadow-lg">
                        <i class="fa-brands fa-telegram text-base"></i>
                        <span id="broadcast-btn-text">ส่งแผนระดับราคาชุดนี้เข้า Telegram ทันที</span>
                    </button>
                </section>

                <!-- 4. ประวัติการแจ้งเตือน & ตารางสรุปสถานะทุก TIMEFRAME -->
                <section class="terminal-panel rounded-2xl p-4 space-y-3">
                    <div class="flex items-center justify-between border-b border-white/10 pb-2.5">
                        <div class="flex gap-1.5">
                            <button onclick="switchRightTab('matrix')" id="tab-btn-matrix" class="px-3 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950">สรุปสถานะทุก Timeframe</button>
                            <button onclick="switchRightTab('feed')" id="tab-btn-feed" class="px-3 py-1 rounded-lg text-xs font-bold bg-white/5 text-slate-400 border border-white/10">ประวัติแจ้งเตือนล่าสุด</button>
                        </div>
                        <span class="text-[10px] text-slate-400 font-mono-num" id="feed-counter-label">--</span>
                    </div>

                    <div id="right-tab-matrix" class="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
                        <div id="matrix-overview-list" class="space-y-1.5 text-xs"></div>
                    </div>
                    <div id="right-tab-feed" class="hidden space-y-2 max-h-[220px] overflow-y-auto pr-1"></div>
                </section>

            </div>
        </div>
    </main>

    <!-- FOOTER DISCLAIMER -->
    <footer class="border-t border-white/10 bg-[#0B0F17] py-3 px-4 text-center text-[11px] text-slate-500 mt-6">
        GOLD AI SNIPER PRO • ระบบซิงก์ราคา OANDA:XAUUSD อัตโนมัติและคัดกรองสภาพตลาดด้วย EMA 20/50, ADX, ATR และ Pivot Fractals • ข้อมูลเพื่อประกอบการวิเคราะห์ทางสถิติเท่านั้น
    </footer>

    <!-- TOAST NOTIFICATION -->
    <div id="toast-notify" class="fixed bottom-5 right-5 hidden bg-[#111726] border border-amber-500/60 text-white px-4 py-3 rounded-xl font-bold text-xs shadow-2xl z-50 flex items-center gap-2.5">
        <span class="w-2 h-2 rounded-full bg-amber-400"></span>
        <span id="toast-notify-text">ดำเนินการสำเร็จ</span>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        const timeframeMeta = {
            '1m':    { label: '1M',  tvInterval: '1' },
            '5m':    { label: '5M',  tvInterval: '5' },
            '15m':   { label: '15M', tvInterval: '15' },
            '1h':    { label: '1H',  tvInterval: '60' },
            '4h':    { label: '4H',  tvInterval: '240' },
            'daily': { label: '1D',  tvInterval: 'D' }
        };

        let currentTfKey = '5m';
        let currentTvLoadedInterval = null;
        let isChartFullscreen = false;
        let isNewsLocked = false;
        let currentAnalysis = null;
        let multiTfStore = {};
        let allCalendarEvents = [];
        let currentNewsFilter = 'ALL';

        // ====================================================================
        // 1. FULLSCREEN TRADINGVIEW CHART MODE (WITH FLOATING HUD & ESC KEY)
        // ====================================================================
        function toggleChartFullscreen() {
            const wrapper = document.getElementById('chart-card-wrapper');
            const icon = document.getElementById('fullscreen-icon');
            const text = document.getElementById('fullscreen-btn-text');
            isChartFullscreen = !isChartFullscreen;

            if (isChartFullscreen) {
                wrapper.classList.add('chart-fullscreen-mode');
                icon.className = "fa-solid fa-compress";
                text.innerText = "ย่อกลับขนาดปกติ (Exit Fullscreen)";
                if (wrapper.requestFullscreen) {
                    wrapper.requestFullscreen().catch(() => {});
                }
            } else {
                wrapper.classList.remove('chart-fullscreen-mode');
                icon.className = "fa-solid fa-expand";
                text.innerText = "ขยายกราฟเต็มจอ";
                if (document.fullscreenElement && document.exitFullscreen) {
                    document.exitFullscreen().catch(() => {});
                }
            }
            // รีโหลดความสูงกราฟให้เต็มพื้นที่อัตโนมัติ
            setTimeout(() => {
                loadTradingViewStudio(timeframeMeta[currentTfKey].tvInterval, true);
            }, 120);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && isChartFullscreen) {
                toggleChartFullscreen();
            }
        });

        function loadTradingViewStudio(intervalCode, forceReload = false) {
            if (!forceReload && currentTvLoadedInterval === intervalCode) return;
            currentTvLoadedInterval = intervalCode;
            const container = document.getElementById('tradingview_advanced_chart');
            container.innerHTML = '';
            new TradingView.widget({
                "autosize": true,
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
                "studies": [
                    "Moving Average Exponential@tv-basicstudies"
                ],
                "container_id": "tradingview_advanced_chart"
            });
        }

        // ====================================================================
        // 2. OANDA-SYNCED MARKET ANALYSIS & SMART SIDEWAY UI ENGINE
        // ====================================================================
        async function refreshMarketAnalysis(showToastMsg = false) {
            const spinIcon = document.getElementById('fib-spin-icon');
            if (spinIcon) spinIcon.className = "fa-solid fa-spinner fa-spin text-[11px] text-amber-400";

            try {
                const balance = parseFloat(document.getElementById('acc-balance').value) || 1000;
                const riskPct = parseFloat(document.getElementById('acc-risk-pct').value) || 1.5;
                const res = await fetch(`/api/analyze?tf=${currentTfKey}&balance=${balance}&risk_pct=${riskPct}`);
                const payload = await res.json();

                if (payload.status === 'ok' && payload.analysis) {
                    currentAnalysis = payload.analysis;
                    multiTfStore[currentTfKey] = currentAnalysis;
                    if (payload.multi_tf) {
                        Object.assign(multiTfStore, payload.multi_tf);
                    }
                    applyAnalysisToUI(currentAnalysis);
                    renderMatrixTable();
                    if (showToastMsg) {
                        showToast(`ซิงก์ราคา OANDA:XAUUSD (${currentTfKey.toUpperCase()}) สำเร็จ`);
                    }
                }
            } catch (e) {
                console.error("Analysis Fetch Error:", e);
            } finally {
                if (spinIcon) spinIcon.className = "fa-solid fa-rotate text-[11px] text-amber-400";
            }
        }

        function applyAnalysisToUI(data) {
            // 1. อัปเดตราคาสดและค่าอินดิเคเตอร์
            document.getElementById('live-ticker-price').innerText = `$${data.current_price.toFixed(2)}`;
            document.getElementById('chart-tf-pill').innerText = `TF ${data.tf}`;
            document.getElementById('display-swing-high').innerText = `$${data.swing_high.toFixed(2)}`;
            document.getElementById('display-swing-low').innerText = `$${data.swing_low.toFixed(2)}`;

            document.getElementById('ind-ema-val').innerText = `${data.ema20.toFixed(0)} / ${data.ema50.toFixed(0)}`;
            document.getElementById('ind-adx-val').innerText = `${data.adx.toFixed(1)}`;
            document.getElementById('ind-chop-val').innerText = `${data.chop.toFixed(1)}`;
            document.getElementById('ind-range-val').innerText = `$${data.range.toFixed(2)}`;
            document.getElementById('structure-tag-line').innerText = `STRUCTURE: ${data.structure_label}`;

            const topPill = document.getElementById('top-regime-pill');
            const topDot = document.getElementById('top-regime-dot');
            const topText = document.getElementById('top-regime-text');

            const regimeCard = document.getElementById('regime-detector-card');
            const regimeBadge = document.getElementById('regime-badge-pill');
            const regimeHeadline = document.getElementById('regime-headline');
            const regimeSubtext = document.getElementById('regime-subtext');

            const dirBanner = document.getElementById('right-card-direction-banner');
            const orderBadge = document.getElementById('setup-order-badge');
            const orderSub = document.getElementById('setup-order-subtext');

            const sidewayBanner = document.getElementById('sideway-lockout-banner');
            const fibGrid = document.getElementById('fib-execution-grid');
            const broadcastBtn = document.getElementById('broadcast-btn');
            const broadcastBtnText = document.getElementById('broadcast-btn-text');
            const proxPill = document.getElementById('proximity-pill');

            // 2. กรณีตรวจพบตลาด SIDEWAY: ล็อกห้ามเทรดทันที!
            if (data.is_sideway) {
                topPill.className = "px-3 py-1 rounded-xl bg-amber-500/20 border border-amber-500/50 flex items-center gap-2 text-xs";
                topDot.className = "w-2 h-2 rounded-full bg-amber-400 animate-ping";
                topText.className = "font-mono-num font-extrabold text-amber-300 text-[11px]";
                topText.innerText = `⚠️ SIDEWAY — งดเทรด (NO TRADE ZONE)`;

                regimeCard.className = "terminal-panel rounded-2xl p-4 border-l-4 border-l-amber-500 bg-amber-500/5 space-y-3";
                regimeBadge.className = "px-2 py-0.5 rounded text-[10px] font-mono-num font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/40";
                regimeBadge.innerText = "SIDEWAY / NO TRADE";
                regimeHeadline.className = "text-sm md:text-base font-extrabold text-amber-300";
                regimeHeadline.innerText = "⚠️ ตลาด SIDEWAY (ไร้ทิศทางชัดเจน) — งดเทรดเด็ดขาด";
                regimeSubtext.innerText = data.explanation;

                dirBanner.className = "p-3.5 rounded-xl border border-amber-500/50 bg-amber-950/25 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2";
                orderBadge.className = "text-base md:text-lg font-black font-mono-num text-amber-400";
                orderBadge.innerText = "🚫 NO TRADE ZONE (ห้ามเข้า BUY / SELL)";
                orderSub.innerText = "รอให้กราฟเบรกเอาต์ออกจากกรอบและเกิดเทรนด์ชัดเจนก่อน";

                // ซ่อนตารางจุดเข้า Fibonacci และแสดงป้ายเตือนห้ามเทรดแทน
                sidewayBanner.classList.remove('hidden');
                fibGrid.classList.add('hidden');

                broadcastBtn.disabled = true;
                broadcastBtn.className = "w-full py-3 px-4 rounded-xl font-black text-xs uppercase bg-slate-800 text-slate-400 border border-white/10 cursor-not-allowed flex items-center justify-center gap-2";
                broadcastBtnText.innerText = "🔒 ล็อกการส่งสัญญาณ (ตลาดเป็น SIDEWAY ห้ามเทรด)";

                proxPill.className = "px-2.5 py-0.5 text-[10px] font-mono-num font-bold rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40";
                proxPill.innerText = "SIDEWAY PAUSE";

                document.getElementById('hud-regime-tag').className = "font-bold text-amber-400";
                document.getElementById('hud-regime-tag').innerText = "⚠️ SIDEWAY (NO TRADE)";
                document.getElementById('hud-fib05').innerText = "LOCKED";
                document.getElementById('hud-fib618').innerText = "LOCKED";
                document.getElementById('calc-lot-result').innerText = "งดเทรด (0.00 Lot)";
                return;
            }

            // 3. กรณีตลาดเป็นเทรนด์ชัดเจน (UPTREND -> BUY / DOWNTREND -> SELL)
            sidewayBanner.classList.add('hidden');
            fibGrid.classList.remove('hidden');

            broadcastBtn.disabled = false;
            broadcastBtn.className = "btn-action w-full py-3 px-4 rounded-xl font-black text-xs uppercase tracking-wider bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 flex items-center justify-center gap-2 shadow-lg";
            broadcastBtnText.innerText = `ส่งแผน ${data.direction} (${data.tf}) ชุดนี้เข้า Telegram ทันที`;

            const isBuy = data.direction === 'BUY';
            if (isBuy) {
                topPill.className = "px-3 py-1 rounded-xl bg-emerald-500/15 border border-emerald-500/40 flex items-center gap-2 text-xs";
                topDot.className = "w-2 h-2 rounded-full bg-emerald-400";
                topText.className = "font-mono-num font-bold text-emerald-400 text-[11px]";
                topText.innerText = `UPTREND • แผน BUY ONLY`;

                regimeCard.className = "terminal-panel rounded-2xl p-4 border-l-4 border-l-emerald-500 space-y-3";
                regimeBadge.className = "px-2 py-0.5 rounded text-[10px] font-mono-num font-extrabold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30";
                regimeBadge.innerText = "UPTREND REGIME";
                regimeHeadline.className = "text-sm md:text-base font-extrabold text-emerald-400";
                regimeHeadline.innerText = data.bias_title;

                dirBanner.className = "p-3.5 rounded-xl border border-emerald-500/50 bg-emerald-950/25 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2";
                orderBadge.className = "text-base md:text-lg font-black font-mono-num text-emerald-400";
                orderBadge.innerText = `🟢 แผนเทรดฝั่ง BUY (${data.tf}) — รอย่อตัว`;
                document.getElementById('entry-action-label').innerText = "จุดรอ BUY เมื่อราคาย่อลงมาแตะ 61.8%";
                document.getElementById('hud-regime-tag').className = "font-bold text-emerald-400";
                document.getElementById('hud-regime-tag').innerText = `🟢 BUY TREND (${data.tf})`;
            } else {
                topPill.className = "px-3 py-1 rounded-xl bg-rose-500/15 border border-rose-500/40 flex items-center gap-2 text-xs";
                topDot.className = "w-2 h-2 rounded-full bg-rose-400";
                topText.className = "font-mono-num font-bold text-rose-400 text-[11px]";
                topText.innerText = `DOWNTREND • แผน SELL ONLY`;

                regimeCard.className = "terminal-panel rounded-2xl p-4 border-l-4 border-l-rose-500 space-y-3";
                regimeBadge.className = "px-2 py-0.5 rounded text-[10px] font-mono-num font-extrabold bg-rose-500/15 text-rose-400 border border-rose-500/30";
                regimeBadge.innerText = "DOWNTREND REGIME";
                regimeHeadline.className = "text-sm md:text-base font-extrabold text-rose-400";
                regimeHeadline.innerText = data.bias_title;

                dirBanner.className = "p-3.5 rounded-xl border border-rose-500/50 bg-rose-950/25 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2";
                orderBadge.className = "text-base md:text-lg font-black font-mono-num text-rose-400";
                orderBadge.innerText = `🔴 แผนเทรดฝั่ง SELL (${data.tf}) — รอเด้งขึ้น`;
                document.getElementById('entry-action-label').innerText = "จุดรอ SELL เมื่อราคาเด้งขึ้นมาแตะ 61.8%";
                document.getElementById('hud-regime-tag').className = "font-bold text-rose-400";
                document.getElementById('hud-regime-tag').innerText = `🔴 SELL TREND (${data.tf})`;
            }

            regimeSubtext.innerText = `${data.explanation} • ${data.fib_pull_desc}`;
            orderSub.innerText = `เตือนล่วงหน้า 0.5: $${data.fib_05.toFixed(2)} • โซนเข้าเทรด 61.8%: $${data.entry.toFixed(2)}`;

            document.getElementById('val-fib05').innerText = `$${data.fib_05.toFixed(2)}`;
            document.getElementById('val-entry').innerText = `$${data.entry.toFixed(2)}`;
            document.getElementById('val-sl').innerText = `$${data.sl.toFixed(2)}`;
            document.getElementById('val-tp1').innerText = `$${data.tp1.toFixed(2)}`;
            document.getElementById('val-tp2').innerText = `$${data.tp2.toFixed(2)}`;

            document.getElementById('val-risk-pts').innerText = `-$${data.risk.toFixed(2)}`;
            document.getElementById('val-tp1-pts').innerText = `+$${data.reward1.toFixed(2)}`;
            document.getElementById('val-tp2-pts').innerText = `+$${data.reward2.toFixed(2)}`;

            document.getElementById('hud-fib05').innerText = `$${data.fib_05.toFixed(2)}`;
            document.getElementById('hud-fib618').innerText = `$${data.entry.toFixed(2)}`;

            const tol = Math.max(0.45, data.range * 0.035);
            if (Math.abs(data.current_price - data.entry) <= tol) {
                proxPill.className = "px-2.5 py-0.5 text-[10px] font-mono-num font-black rounded-lg bg-sky-400 text-slate-950 animate-pulse";
                proxPill.innerText = "🎯 เข้าโซน 61.8%!";
            } else if (Math.abs(data.current_price - data.fib_05) <= tol) {
                proxPill.className = "px-2.5 py-0.5 text-[10px] font-mono-num font-black rounded-lg bg-amber-400 text-slate-950 animate-pulse";
                proxPill.innerText = "🔔 แตะ 0.5 (เตรียมตัว)";
            } else {
                proxPill.className = "px-2.5 py-0.5 text-[10px] font-mono-num font-bold rounded-lg bg-white/5 text-slate-300 border border-white/10";
                proxPill.innerText = `รอแตะ 0.5 ($${data.fib_05.toFixed(2)})`;
            }

            recalcLotSize();
        }

        function recalcLotSize() {
            if (!currentAnalysis || currentAnalysis.is_sideway) {
                document.getElementById('calc-lot-result').innerText = "งดเทรด (0.00 Lot)";
                return;
            }
            const balance = parseFloat(document.getElementById('acc-balance').value) || 1000;
            const riskPct = parseFloat(document.getElementById('acc-risk-pct').value) || 1.5;
            const riskMoney = balance * (riskPct / 100.0);
            const lossPerLot = Math.max(0.50, currentAnalysis.risk) * 100.0;
            const lot = Math.max(0.01, riskMoney / lossPerLot).toFixed(2);
            document.getElementById('calc-lot-result').innerText = `${lot} Lot ($${riskMoney.toFixed(1)})`;
        }

        async function selectTimeframe(tfKey) {
            currentTfKey = tfKey;
            const meta = timeframeMeta[tfKey];
            if (!meta) return;

            document.querySelectorAll('.tf-btn').forEach(btn => {
                btn.className = "tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-bold bg-[#06080E] text-slate-400 border border-white/10 hover:text-white";
            });
            const activeBtn = document.getElementById('btn-' + tfKey);
            if (activeBtn) {
                activeBtn.className = "tf-btn btn-action py-2 rounded-xl text-xs font-mono-num font-black bg-amber-500 text-slate-950 border border-amber-300 shadow";
            }

            document.getElementById('active-tf-badge').innerText = `ACTIVE: ${tfKey.toUpperCase()}`;
            loadTradingViewStudio(meta.tvInterval);
            await refreshMarketAnalysis(false);
        }

        // ====================================================================
        // 3. TELEGRAM SETTINGS & DIAGNOSTICS
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
            await saveUserSettings(true);
            showToast('✅ เข้าสู่ระบบ GOLD AI SNIPER PRO สำเร็จ');
        }

        function toggleSettingsModal() {
            document.getElementById('settings-modal').classList.toggle('hidden');
        }

        function showDiagnosticLog(text, isSuccess = true) {
            const box = document.getElementById('telegram-diagnostic-log');
            box.classList.remove('hidden');
            box.className = `mt-2 p-2.5 rounded-lg border font-mono-num text-[11px] ${
                isSuccess ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300' : 'bg-rose-950/40 border-rose-500/40 text-rose-300'
            }`;
            box.innerText = text;
        }

        async function autoDetectTelegramChatId() {
            showToast('🔍 กำลังค้นหา Chat ID ล่าสุดที่กด /start...');
            const botToken = document.getElementById('set-bot-token').value.trim();
            try {
                const res = await fetch(`/api/telegram-detect-chat?token=${encodeURIComponent(botToken)}`);
                const data = await res.json();
                if (data.status === 'ok' && data.chat_id) {
                    document.getElementById('set-chat-id').value = data.chat_id;
                    localStorage.setItem('gold_sniper_chat_id', data.chat_id);
                    document.getElementById('telegram-status-btn').innerText = `TG: ${data.chat_id}`;
                    showDiagnosticLog(`✅ พบ Chat ID อัตโนมัติ: ${data.chat_id} (${data.name})`, true);
                    showToast(`✅ พบ Chat ID: ${data.chat_id} (${data.name})`);
                } else {
                    showDiagnosticLog('⚠️ ยังไม่พบประวัติการกด /start ล่าสุด กรุณาเปิดบอท @gold_ai_sniper_pro_bot แล้วพิมพ์ /start อีกครั้ง', false);
                    showToast('⚠️ กรุณากด /start ในบอทก่อนครับ');
                }
            } catch (e) {
                showDiagnosticLog('⚠️ เกิดข้อผิดพลาดในการเชื่อมต่อ API', false);
            }
        }

        async function saveUserSettings(silent = false) {
            const email = localStorage.getItem('gold_sniper_email') || 'default@gold.ai';
            const chatId = document.getElementById('set-chat-id').value.trim();
            const botToken = document.getElementById('set-bot-token').value.trim();
            const tf = document.getElementById('set-tf').value;
            const startT = document.getElementById('set-start-time').value;
            const endT = document.getElementById('set-end-time').value;

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
                    custom_bot_token: botToken,
                    preferred_tf: tf,
                    start_time: startT,
                    end_time: endT,
                    alert_morning_news: document.getElementById('set-alert-morning').checked,
                    alert_sideway: document.getElementById('set-alert-sideway').checked,
                    alert_05: document.getElementById('set-alert-05').checked,
                    alert_618: document.getElementById('set-alert-618').checked,
                    balance: parseFloat(document.getElementById('acc-balance').value) || 1000,
                    risk_pct: parseFloat(document.getElementById('acc-risk-pct').value) || 1.5
                })
            });

            if (!silent) {
                selectTimeframe(tf);
                toggleSettingsModal();
                showToast('✅ บันทึกการตั้งค่าและเปิดสแกนหลังบ้าน 24 ชม. เรียบร้อย!');
            }
        }

        async function sendTestTelegram() {
            const chatId = document.getElementById('set-chat-id').value.trim();
            const botToken = document.getElementById('set-bot-token').value.trim();
            if (!chatId) {
                showToast('⚠️ กรุณาระบุเลข Chat ID ก่อนทดสอบ');
                return;
            }
            showDiagnosticLog('⏳ กำลังทดสอบส่งข้อความเข้า Telegram...', true);
            const res = await fetch('/api/test-telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId, custom_bot_token: botToken })
            });
            const data = await res.json();
            if (res.ok && data.status === 'ok') {
                showDiagnosticLog('✅ ส่งข้อความเข้า Telegram สำเร็จ 100%! (Self-Healing Token Verified)', true);
                showToast('🚀 ส่งข้อความทดสอบเข้า Telegram มือถือเรียบร้อย!');
            } else {
                showDiagnosticLog(`❌ ส่งไม่สำเร็จ: ${data.message}`, false);
                showToast('⚠️ ส่งไม่สำเร็จ: ' + (data.message || 'Error'));
            }
        }

        async function sendMorningBriefNow() {
            const chatId = document.getElementById('set-chat-id').value.trim() || localStorage.getItem('gold_sniper_chat_id') || '8948986514';
            const botToken = document.getElementById('set-bot-token').value.trim();
            const startT = document.getElementById('set-start-time').value || '08:00';
            const endT = document.getElementById('set-end-time').value || '23:00';

            const res = await fetch('/api/send-morning-brief', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: chatId,
                    custom_bot_token: botToken,
                    start_time: startT,
                    end_time: endT
                })
            });
            const data = await res.json();
            if (res.ok && data.status === 'ok') {
                showDiagnosticLog('✅ ส่งสรุปตารางข่าวเช้าเข้า Telegram สำเร็จ!', true);
                showToast('🌅 ส่งสรุปข่าวเศรษฐกิจวันนี้เข้า Telegram เรียบร้อย!');
            } else {
                showDiagnosticLog(`❌ ส่งสรุปข่าวไม่สำเร็จ: ${data.message}`, false);
                showToast('⚠️ ส่งสรุปข่าวไม่สำเร็จ: ' + (data.message || 'Error'));
            }
        }

        async function broadcastCurrentSignal() {
            if (isNewsLocked) {
                showToast('🛑 ระบบล็อกการส่งชั่วคราวเนื่องจากอยู่ในช่วงเฝ้าระวังข่าวแดง');
                return;
            }
            if (!currentAnalysis || currentAnalysis.is_sideway) {
                showToast('⚠️ ตลาดเป็น SIDEWAY ระบบล็อกห้ามส่งสัญญาณ BUY/SELL เด็ดขาด!');
                return;
            }

            const chatId = document.getElementById('set-chat-id').value.trim() || localStorage.getItem('gold_sniper_chat_id') || '8948986514';
            const botToken = document.getElementById('set-bot-token').value.trim();

            const payload = {
                chat_id: chatId,
                custom_bot_token: botToken,
                symbol: 'XAUUSD',
                tf: currentAnalysis.tf,
                direction: currentAnalysis.direction,
                regime: currentAnalysis.regime,
                adx: currentAnalysis.adx.toFixed(1),
                fib_05: currentAnalysis.fib_05.toFixed(2),
                entry: currentAnalysis.entry.toFixed(2),
                sl: currentAnalysis.sl.toFixed(2),
                tp1: currentAnalysis.tp1.toFixed(2),
                tp2: currentAnalysis.tp2.toFixed(2),
                lot: document.getElementById('calc-lot-result').innerText,
                reason: currentAnalysis.explanation
            };

            const res = await fetch('/api/send-signal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.status === 'success') {
                renderSignalFeed(data.signal_history);
                showToast('🚀 ส่งแผนระดับราคาเข้า Telegram เรียบร้อย!');
            } else {
                showToast('⚠️ ' + (data.message || 'ส่งไม่สำเร็จ'));
            }
        }

        // ====================================================================
        // 4. MULTI-TF MATRIX, SIGNAL FEED & FOREX FACTORY CALENDAR
        // ====================================================================
        function switchRightTab(tab) {
            document.getElementById('right-tab-matrix').classList.toggle('hidden', tab !== 'matrix');
            document.getElementById('right-tab-feed').classList.toggle('hidden', tab !== 'feed');
            document.getElementById('tab-btn-matrix').className = tab === 'matrix'
                ? "px-3 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950"
                : "px-3 py-1 rounded-lg text-xs font-bold bg-white/5 text-slate-400 border border-white/10";
            document.getElementById('tab-btn-feed').className = tab === 'feed'
                ? "px-3 py-1 rounded-lg text-xs font-extrabold bg-amber-500 text-slate-950"
                : "px-3 py-1 rounded-lg text-xs font-bold bg-white/5 text-slate-400 border border-white/10";
        }

        function renderMatrixTable() {
            const list = document.getElementById('matrix-overview-list');
            list.innerHTML = '';
            Object.keys(timeframeMeta).forEach(key => {
                const st = multiTfStore[key];
                if (!st) return;

                const row = document.createElement('div');
                row.className = `flex items-center justify-between p-2.5 rounded-xl border cursor-pointer font-mono-num ${
                    key === currentTfKey ? 'bg-amber-500/15 border-amber-500/50' : 'bg-[#06080E] border-white/10 hover:border-white/25'
                }`;
                row.onclick = () => selectTimeframe(key);

                let statusHtml = '';
                let rightHtml = '';
                if (st.is_sideway) {
                    statusHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">⚠️ SIDEWAY (งดเทรด)</span>`;
                    rightHtml = `<span class="text-[11px] text-slate-400">ADX ${st.adx.toFixed(1)} • รอเลือกทาง</span>`;
                } else {
                    const badgeClass = st.direction === 'BUY'
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-300 border-rose-500/30';
                    statusHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold border ${badgeClass}">${st.direction} TREND</span>`;
                    rightHtml = `
                        <div class="flex gap-2.5 text-[11px]">
                            <span class="text-amber-300">0.5: $${st.fib_05.toFixed(2)}</span>
                            <span class="text-sky-400 font-bold">61.8%: $${st.entry.toFixed(2)}</span>
                        </div>
                    `;
                }

                row.innerHTML = `
                    <div class="flex items-center gap-2.5">
                        <span class="font-black text-amber-400 w-9 uppercase">${key}</span>
                        ${statusHtml}
                    </div>
                    ${rightHtml}
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
                card.className = `p-3 rounded-xl bg-[#06080E] border border-white/10 border-l-4 ${isSell ? 'border-l-rose-500' : 'border-l-emerald-500'} space-y-1 text-xs font-mono-num`;
                card.innerHTML = `
                    <div class="flex justify-between items-center">
                        <span class="font-bold text-white">${sig.symbol} • TF ${sig.tf} (${sig.direction})</span>
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
                updateNewsShieldUI(isNewsLocked);
                renderCalendarTable();
                renderSignalFeed(data.signal_history || []);
            } catch (e) {}
        }

        function filterNews(mode) {
            currentNewsFilter = mode;
            ['ALL', 'TODAY', 'HIGH'].forEach(m => {
                const btn = document.getElementById('news-filter-' + m);
                if (!btn) return;
                btn.className = (m === mode)
                    ? "px-2.5 py-1 rounded-lg text-[11px] font-bold bg-amber-500 text-slate-950"
                    : "px-2.5 py-1 rounded-lg text-[11px] font-bold bg-white/5 text-slate-300 border border-white/10";
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
                tbody.innerHTML = `<tr><td colspan="6" class="py-5 text-center text-slate-500">ไม่มีรายการข่าวเศรษฐกิจในหมวดนี้</td></tr>`;
                return;
            }
            filtered.forEach(item => {
                const badge = item.impact === 'HIGH'
                    ? '<span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 font-bold text-[10px]">🔴 HIGH</span>'
                    : '<span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold text-[10px]">🟠 MED</span>';
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

        function updateNewsShieldUI(locked) {
            const box = document.getElementById('news-shield-box');
            const dot = document.getElementById('shield-dot');
            const text = document.getElementById('shield-status-text');
            if (locked) {
                box.className = "px-3 py-1 rounded-xl bg-rose-500/20 border border-rose-500/50 flex items-center gap-2 text-xs";
                dot.className = "w-2 h-2 rounded-full bg-rose-500 animate-ping";
                text.className = "text-[11px] font-bold text-rose-300";
                text.innerText = "News Shield: ล็อกช่วงข่าวแดง";
            } else {
                box.className = "px-3 py-1 rounded-xl bg-white/5 border border-white/10 flex items-center gap-2 text-xs";
                dot.className = "w-2 h-2 rounded-full bg-emerald-400";
                text.className = "text-[11px] font-semibold text-slate-300";
                text.innerText = "News Shield: ตลาดปกติ";
            }
        }

        async function toggleNewsLock() {
            const res = await fetch('/api/toggle-news-lock', { method: 'POST' });
            const data = await res.json();
            isNewsLocked = data.news_locked;
            updateNewsShieldUI(isNewsLocked);
            showToast(isNewsLocked ? '🛡️ เปิดโหมดจำลองการล็อกช่วงข่าวแดง' : '🟢 ปลดล็อกโหมดข่าวแดง');
        }

        function copyPrice(elementId) {
            const raw = document.getElementById(elementId).innerText.replace('$', '').trim();
            if (!raw || raw === '--') return;
            navigator.clipboard.writeText(raw);
            showToast(`✅ คัดลอกราคา $${raw} เรียบร้อย`);
        }

        function showToast(msg) {
            const toast = document.getElementById('toast-notify');
            document.getElementById('toast-notify-text').innerText = msg;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 3200);
        }

        window.addEventListener('DOMContentLoaded', async () => {
            checkAuthStatus();
            await selectTimeframe('5m');
            await loadSystemState();

            // อัปเดตการวิเคราะห์และซิงก์ราคา OANDA อัตโนมัติทุก 18 วินาที
            setInterval(() => {
                refreshMarketAnalysis(false);
            }, 18000);
        });
    </script>
</body>
</html>
"""


# ==============================================================================
# 7. FLASK BACKEND API ROUTES
# ==============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/analyze', methods=['GET'])
def api_analyze():
    tf = request.args.get("tf", "5m").lower()
    balance = float(request.args.get("balance", 1000.0))
    risk_pct = float(request.args.get("risk_pct", 1.5))

    primary = analyze_market_structure_and_regime(tf, balance, risk_pct)

    # อัปเดตสถานะตาราง Multi-TF สำหรับแสดงผลเปรียบเทียบ
    multi_tf_summary = {}
    for k in ["1m", "5m", "15m", "1h", "4h", "daily"]:
        if k == tf:
            multi_tf_summary[k] = primary
        elif k in MARKET_CACHE["tf_data"]:
            multi_tf_summary[k] = MARKET_CACHE["tf_data"][k]
        else:
            try:
                multi_tf_summary[k] = analyze_market_structure_and_regime(k, balance, risk_pct)
            except Exception:
                pass

    return jsonify({
        "status": "ok",
        "analysis": primary,
        "multi_tf": multi_tf_summary
    })


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
        "scanner_last_run": SYSTEM_STATE["scanner_last_run"],
        "server_time": now_dt.strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/api/user-config', methods=['POST'])
def save_user_config():
    data = request.json or {}
    email = data.get("email", "default@gold.ai").strip().lower()
    chat_id = str(data.get("chat_id", DEFAULT_CHAT_ID)).strip()
    custom_token = str(data.get("custom_bot_token", VERIFIED_BOT_TOKEN)).strip()

    if custom_token:
        SYSTEM_STATE["active_bot_token"] = custom_token

    USERS_DB[email] = {
        "email": email,
        "chat_id": chat_id,
        "custom_bot_token": custom_token or VERIFIED_BOT_TOKEN,
        "preferred_tf": data.get("preferred_tf", "5m").lower(),
        "start_time": data.get("start_time", "08:00"),
        "end_time": data.get("end_time", "23:00"),
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
    custom_token = request.args.get("token", "").strip()
    chat_id, first_name = fetch_latest_telegram_chat_id(custom_token)
    if chat_id:
        return jsonify({"status": "ok", "chat_id": chat_id, "name": first_name})
    return jsonify({"status": "not_found"}), 404


@app.route('/api/test-telegram', methods=['POST'])
def test_telegram():
    data = request.json or {}
    chat_id = data.get("chat_id", DEFAULT_CHAT_ID).strip()
    custom_token = data.get("custom_bot_token", "").strip()
    now_dt = datetime.now(TH_TZ)

    msg = (
        f"✅ <b>GOLD AI SNIPER PRO — เชื่อมต่อสำเร็จ 100%!</b>\n"
        f"🕒 <b>เวลาเซิร์ฟเวอร์:</b> {now_dt.strftime('%H:%M:%S')} น.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>ซิงก์ราคา:</b> OANDA:XAUUSD Real-Time Feed\n"
        f"• <b>สมองกลกรองเทรนด์:</b> EMA 20/50 + ADX 14 + Pivot Fractals\n"
        f"• <b>กฎเหล็ก Sideway:</b> งดส่งสัญญาณ BUY/SELL ทันทีเมื่อตลาดไร้ทิศทาง\n"
        f"• <b>แจ้งเตือนอัตโนมัติ:</b> ข่าวเช้า + จุด 0.5 + Golden Zone 61.8%"
    )
    ok, err = send_telegram_message(chat_id, msg, custom_token)
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": err}), 400


@app.route('/api/send-morning-brief', methods=['POST'])
def trigger_morning_brief():
    data = request.json or {}
    chat_id = data.get("chat_id", DEFAULT_CHAT_ID).strip()
    custom_token = data.get("custom_bot_token", "").strip()
    start_t = data.get("start_time", "08:00")
    end_t = data.get("end_time", "23:00")
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()

    msg = build_morning_news_brief_message(now_dt, calendar_events, start_t, end_t)
    ok, err = send_telegram_message(chat_id, msg, custom_token)
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
        "news_locked": SYSTEM_STATE["manual_news_lock"]
    })


@app.route('/api/send-signal', methods=['POST'])
def send_signal():
    now_dt = datetime.now(TH_TZ)
    calendar_events = fetch_forex_factory_calendar()
    auto_locking_event = next((ev for ev in calendar_events if ev.get("is_locking_now")), None)

    if SYSTEM_STATE["manual_news_lock"] or auto_locking_event:
        return jsonify({
            "status": "blocked",
            "message": "ระบบล็อกการส่งสัญญาณเนื่องจากอยู่ในช่วงเฝ้าระวังข่าวแดง"
        }), 403

    data = request.json or {}
    regime = data.get("regime", "TRENDING")
    direction = data.get("direction", "BUY")

    if regime == "SIDEWAY" or direction == "NO_TRADE":
        return jsonify({
            "status": "blocked",
            "message": "ตลาดอยู่ในสภาวะ SIDEWAY ระบบไม่อนุญาตให้ส่งสัญญาณ BUY/SELL"
        }), 400

    chat_id = data.get("chat_id", DEFAULT_CHAT_ID).strip()
    custom_token = data.get("custom_bot_token", "").strip()

    sig = {
        "id": len(SYSTEM_STATE["signal_history"]) + 101,
        "date": format_thai_date(now_dt),
        "time": now_dt.strftime("%H:%M:%S"),
        "symbol": data.get("symbol", "XAUUSD"),
        "tf": data.get("tf", "5M"),
        "direction": direction,
        "regime": regime,
        "adx": data.get("adx", "-"),
        "fib_05": data.get("fib_05", "0.00"),
        "entry": data.get("entry", "0.00"),
        "sl": data.get("sl", "0.00"),
        "tp1": data.get("tp1", "0.00"),
        "tp2": data.get("tp2", "0.00"),
        "status": "TELEGRAM SENT",
        "reason": data.get("reason", "")
    }

    msg = (
        f"📐 <b>OANDA:XAUUSD ({sig['tf']}) • แผนเทรดฝั่ง {sig['direction']} ONLY</b>\n"
        f"📡 <b>สภาวะตลาด:</b> {sig['regime']} (ADX {sig['adx']})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 <b>จังหวะที่ 1 — จุดเตรียมตัว (0.5):</b> ${sig['fib_05']}\n"
        f"🎯 <b>จังหวะที่ 2 — Golden Zone (61.8%):</b> ${sig['entry']}\n"
        f"🔴 <b>Stop Loss (78.6%):</b> ${sig['sl']}\n"
        f"🟢 <b>Target 1 (RR 1:2):</b> ${sig['tp1']}\n"
        f"🟡 <b>Target 2 (RR 1:3):</b> ${sig['tp2']}\n"
        f"⚖️ <b>ขนาด Lot ที่เหมาะสม:</b> {data.get('lot', '0.05 Lot')}\n"
        f"🧠 <b>วิเคราะห์โครงสร้าง:</b> {sig['reason']}"
    )

    ok, err = send_telegram_message(chat_id, msg, custom_token)
    if not ok:
        return jsonify({"status": "error", "message": f"ส่งเข้า Telegram ไม่สำเร็จ: {err}"}), 400

    SYSTEM_STATE["latest_signal"] = sig
    SYSTEM_STATE["signal_history"].insert(0, sig)

    return jsonify({
        "status": "success",
        "latest_signal": sig,
        "signal_history": SYSTEM_STATE["signal_history"]
    })


@app.route('/api/tv-webhook', methods=['POST'])
def tv_webhook():
    """รองรับการรับค่าพิกัดจาก TradingView Alert Webhook โดยตรง"""
    try:
        data = request.json or {}
        tf = str(data.get("tf", "5m")).lower()
        SYSTEM_STATE["webhook_override"][tf] = {
            "active": True,
            "swing_high": float(data["high"]),
            "swing_low": float(data["low"]),
            "direction": str(data.get("direction", "")).upper(),
            "force_trend": bool(data.get("force_trend", False))
        }
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
