"""Canlı tarayıcı: coinleri tarar, sinyal varsa Telegram'a yollar.

Kullanım:
    python main.py            # tara ve bildir
    python main.py --test     # Telegram bağlantısını test et
"""
import json
import sys
from pathlib import Path

import yaml

import indicators as ind
import strategies as st
from data import TF_MS, get_klines
from notifier import send_telegram

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"


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


def scan():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    state = load_state()
    tf_ms = TF_MS[cfg["timeframe"]]
    min_score = cfg["scoring"]["min_score"]
    cooldown_ms = cfg.get("cooldown_candles", 6) * tf_ms
    sent = 0

    for symbol in cfg["symbols"]:
        try:
            df = get_klines(symbol, cfg["timeframe"], cfg.get("candles", 300))
        except Exception as e:
            print(f"[hata] {e}")
            continue

        signals = st.run_all(df, cfg)
        score_series = st.combined_score(df, signals, cfg)
        score = score_series.iloc[-1]
        candle_ms = int(df["open_time"].iloc[-1])
        lookback = cfg["scoring"].get("lookback", 1)
        window = signals.tail(lookback)

        side = "AL" if score >= min_score else "SAT" if score <= -min_score else None
        print(f"{symbol}: puan={score:+.0f}  son mum={df.index[-1]}  → {side or '-'}")

        if side:
            direction = 1 if side == "AL" else -1
            fired = [st.STRATEGIES[c][1] for c in window.columns if (window[c] == direction).any()]
            key = f"{symbol}:{side}"
            last_sent = state.get(key, 0)
            if candle_ms - last_sent >= cooldown_ms:
                if send_telegram(build_message(symbol, side, score, fired, df, cfg)):
                    sent += 1
                    state[key] = candle_ms

        if cfg.get("notify_single_strategy"):
            last_row = signals.iloc[-1]
            for name, v in last_row.items():
                if v == 0:
                    continue
                key = f"{symbol}:{name}:{v}"
                if state.get(key) == candle_ms:
                    continue
                label = st.STRATEGIES[name][1]
                send_telegram(f"{'🟢 AL' if v > 0 else '🔴 SAT'} · {symbol} · {label} · {fmt_price(df['close'].iloc[-1])}")
                state[key] = candle_ms

    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))
    print(f"Bitti. Gönderilen sinyal: {sent}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = send_telegram("✅ Kripto sinyal botu bağlandı! Sinyaller buraya gelecek.")
        sys.exit(0 if ok else 1)
    scan()
