"""Canlı tarayıcı: coinleri tarar, sinyal varsa Telegram'a yollar.

Kullanım:
    python main.py            # tara ve bildir
    python main.py --test     # Telegram bağlantısını test et
"""
import csv
import json
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

import indicators as ind
import strategies as st
from data import TF_MS, get_all_symbols, get_klines
from notifier import send_telegram

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
LOG_DIR = ROOT / "kayitlar"

COMBINED_COLS = ["mum_zamani_utc", "tarama_zamani_utc", "coin", "yon", "puan", "fiyat", "rsi", "atr",
                 "ornek_stop", "ornek_hedef", "tetikleyenler", "bildirildi", "periyot"]
SINGLE_COLS = ["mum_zamani_utc", "coin", "strateji", "yon", "fiyat", "periyot"]


def _r(x):
    return float(f"{x:.6g}")


def append_rows(path, cols, rows):
    if not rows:
        return
    LOG_DIR.mkdir(exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerows(rows)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def fmt_price(p):
    return f"{p:,.2f}" if p >= 1 else f"{p:.6f}"


def build_message(symbol, side, score, fired, df, cfg):
    last = df.iloc[-1]
    close = last["close"]
    a = ind.atr(df, 14).iloc[-1]
    r = ind.rsi(df["close"], 14).iloc[-1]
    emoji = "🟢" if side == "AL" else "🔴"
    # ATR tabanlı örnek stop/hedef seviyeleri (bilgi amaçlı)
    if side == "AL":
        stop, target = close - 1.5 * a, close + 3 * a
    else:
        stop, target = close + 1.5 * a, close - 3 * a
    lines = [
        f"{emoji} <b>{side} sinyali — {symbol}</b> ({cfg['timeframe']})",
        f"Fiyat: <b>{fmt_price(close)}</b>",
        f"Puan: <b>{score:+.0f}</b>  (eşik ±{cfg['scoring']['min_score']})",
        "Tetikleyenler: " + ", ".join(fired),
        f"RSI: {r:.1f}  |  ATR: {fmt_price(a)}",
        f"Örnek stop: {fmt_price(stop)}  |  Örnek hedef: {fmt_price(target)}",
        f"Mum: {df.index[-1].strftime('%d.%m %H:%M')} UTC",
        "<i>Otomatik teknik sinyal, yatırım tavsiyesi değildir.</i>",
    ]
    return "\n".join(lines)


def resolve_symbols(cfg):
    if isinstance(cfg["symbols"], str) and cfg["symbols"].upper() == "ALL":
        u = cfg.get("universe", {})
        syms = get_all_symbols(u.get("min_quote_volume", 0), u.get("max_symbols", 0), u.get("exclude", []))
        print(f"Taranacak coin sayısı: {len(syms)}")
        return syms
    return list(cfg["symbols"])


def analyze(symbol, cfg):
    """Tek coin: veri çek, stratejileri çalıştır, sonucu döndür (bildirim göndermez)."""
    try:
        df = get_klines(symbol, cfg["timeframe"], cfg.get("candles", 300))
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}
    if len(df) < 210:  # yeni listelenmiş coin, EMA200 için yeterli geçmiş yok
        return {"symbol": symbol, "error": f"yetersiz veri ({len(df)} mum)"}
    signals = st.run_all(df, cfg)
    score = st.combined_score(df, signals, cfg).iloc[-1]
    min_score = cfg["scoring"]["min_score"]
    side = "AL" if score >= min_score else "SAT" if score <= -min_score else None
    res = {"symbol": symbol, "df": df, "signals": signals, "score": score, "side": side,
           "candle_ms": int(df["open_time"].iloc[-1])}
    if side:
        d = 1 if side == "AL" else -1
        window = signals.tail(cfg["scoring"].get("lookback", 1))
        res["fired"] = [st.STRATEGIES[c][1] for c in window.columns if (window[c] == d).any()]
    return res


def summary_message(items, cfg):
    lines = [f"📊 <b>{len(items)} yeni sinyal</b> ({cfg['timeframe']})", ""]
    for side, emoji in (("AL", "🟢"), ("SAT", "🔴")):
        group = [r for r in items if r["side"] == side]
        if not group:
            continue
        lines.append(f"{emoji} <b>{side}</b>")
        for r in group:
            price = fmt_price(r["df"]["close"].iloc[-1])
            lines.append(f"• <b>{r['symbol']}</b> {price} · puan {r['score']:+.0f} · {', '.join(r['fired'])}")
        lines.append("")
    lines.append("<i>Otomatik teknik sinyal, yatırım tavsiyesi değildir.</i>")
    text = "\n".join(lines)
    # Telegram mesaj sınırı 4096 karakter
    return [text[i:i + 3900] for i in range(0, len(text), 3900)]


def scan():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    state = load_state()
    tf_ms = TF_MS[cfg["timeframe"]]
    cooldown_ms = cfg.get("cooldown_candles", 6) * tf_ms

    symbols = resolve_symbols(cfg)
    with ThreadPoolExecutor(max_workers=cfg.get("workers", 8)) as pool:
        results = list(pool.map(lambda s: analyze(s, cfg), symbols))

    errors = [r for r in results if "error" in r]
    ok = [r for r in results if "error" not in r]
    for r in ok:
        if r["side"]:
            print(f"{r['symbol']}: puan={r['score']:+.0f} → {r['side']}")
    if errors:
        print(f"Atlanan {len(errors)} coin: " + ", ".join(f"{e['symbol']} ({e['error'][:40]})" for e in errors[:15]))

    # Bekleme süresi dolmuş yeni sinyaller (en güçlü puan önce)
    new = [r for r in ok if r["side"] and r["candle_ms"] - state.get(f"{r['symbol']}:{r['side']}", 0) >= cooldown_ms]
    new.sort(key=lambda r: -abs(r["score"]))

    sent = 0
    if new:
        if len(new) <= cfg.get("max_individual_messages", 5):
            for r in new:
                if send_telegram(build_message(r["symbol"], r["side"], r["score"], r["fired"], r["df"], cfg)):
                    sent += 1
                    state[f"{r['symbol']}:{r['side']}"] = r["candle_ms"]
        else:
            if all([send_telegram(part) for part in summary_message(new, cfg)]):
                sent = len(new)
                for r in new:
                    state[f"{r['symbol']}:{r['side']}"] = r["candle_ms"]

    if cfg.get("notify_single_strategy"):
        for r in ok:
            for name, v in r["signals"].iloc[-1].items():
                key = f"{r['symbol']}:{name}:{v}"
                if v == 0 or state.get(key) == r["candle_ms"]:
                    continue
                label = st.STRATEGIES[name][1]
                send_telegram(f"{'🟢 AL' if v > 0 else '🔴 SAT'} · {r['symbol']} · {label} · {fmt_price(r['df']['close'].iloc[-1])}")
                state[key] = r["candle_ms"]

    # ---- Bütün sinyalleri kaydet ----
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    sent_keys = {f"{r['symbol']}:{r['side']}" for r in new if state.get(f"{r['symbol']}:{r['side']}") == r["candle_ms"]}
    combined_rows, single_rows = [], []
    for r in ok:
        df, ts = r["df"], r["df"].index[-1].strftime("%Y-%m-%d %H:%M")
        close = df["close"].iloc[-1]
        if r["side"]:
            a = ind.atr(df, 14).iloc[-1]
            k = 1 if r["side"] == "AL" else -1
            combined_rows.append({
                "mum_zamani_utc": ts, "tarama_zamani_utc": now.strftime("%Y-%m-%d %H:%M"),
                "coin": r["symbol"], "yon": r["side"], "puan": int(r["score"]), "fiyat": _r(close),
                "rsi": round(ind.rsi(df["close"], 14).iloc[-1], 1), "atr": _r(a),
                "ornek_stop": _r(close - k * 1.5 * a), "ornek_hedef": _r(close + k * 3 * a),
                "tetikleyenler": " | ".join(r["fired"]),
                "bildirildi": "evet" if f"{r['symbol']}:{r['side']}" in sent_keys else "hayır (bekleme süresi)",
                "periyot": cfg["timeframe"],
            })
        for name, v in r["signals"].iloc[-1].items():
            if v != 0:
                single_rows.append({"mum_zamani_utc": ts, "coin": r["symbol"], "strateji": st.STRATEGIES[name][1],
                                    "yon": "AL" if v > 0 else "SAT", "fiyat": _r(close), "periyot": cfg["timeframe"]})
    # Aynı mum iki kez taranırsa (GitHub gecikmesi) tekrar yazma
    last_logged = state.get("_son_kayitli_mum", 0)
    newest = max((r["candle_ms"] for r in ok), default=0)
    if newest > last_logged:
        append_rows(LOG_DIR / f"sinyaller_{month}.csv", COMBINED_COLS, combined_rows)
        append_rows(LOG_DIR / f"strateji_sinyalleri_{month}.csv", SINGLE_COLS, single_rows)
        state["_son_kayitli_mum"] = newest
        print(f"Kaydedildi: {len(combined_rows)} kombine, {len(single_rows)} tekil strateji sinyali")

    # Eski kayıtları temizle (dosya şişmesin)
    horizon = max((r["candle_ms"] for r in ok), default=0) - 30 * cooldown_ms
    state = {k: v for k, v in state.items() if v >= horizon or k.startswith("_")}
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))
    print(f"Bitti. Taranan: {len(ok)}, atlanan: {len(errors)}, gönderilen sinyal: {sent}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = send_telegram("✅ Kripto sinyal botu bağlandı! Sinyaller buraya gelecek.")
        sys.exit(0 if ok else 1)
    scan()
