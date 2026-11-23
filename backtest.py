"""Strateji karşılaştırması (geriye dönük test).

Her stratejiyi geçmiş veride ayrı ayrı çalıştırır, ayrıca puanlama sistemini
("KOMBİNE") ve "al ve tut"u da ekler, sonuçları tablo + HTML rapor olarak verir.

Kural (basit ve dürüst): sadece long. AL sinyalinde bir sonraki mumun açılışında gir,
SAT sinyalinde bir sonraki mumun açılışında çık. Her işlemde %0.1 komisyon.

Kullanım:
    python backtest.py                         # config'teki coinler, 2000 mum
    python backtest.py --candles 4000 --tf 4h
    python backtest.py --synthetic             # internetsiz deneme (sahte veri)
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import strategies as st

ROOT = Path(__file__).parent
FEE = 0.001


def simulate(df: pd.DataFrame, signal: pd.Series):
    opens = df["open"].to_numpy()
    sig = signal.to_numpy()
    equity, pos, entry = 1.0, False, 0.0
    curve, trades = [], []
    for i in range(len(df) - 1):
        # i. mumda sinyal → i+1 açılışında işlem
        if not pos and sig[i] > 0:
            pos, entry = True, opens[i + 1] * (1 + FEE)
        elif pos and sig[i] < 0:
            exit_p = opens[i + 1] * (1 - FEE)
            trades.append(exit_p / entry - 1)
            equity *= exit_p / entry
            pos = False
        mark = equity * (df["close"].iloc[i + 1] / entry) if pos else equity
        curve.append(mark)
    if pos:  # açık pozisyonu son fiyattan kapat
        r = df["close"].iloc[-1] * (1 - FEE) / entry
        trades.append(r - 1)
        equity *= r
    curve = np.array(curve) if curve else np.array([1.0])
    dd = (curve / np.maximum.accumulate(curve) - 1).min()
    t = np.array(trades)
    wins, losses = t[t > 0].sum(), -t[t < 0].sum()
    return {
        "İşlem": len(t),
        "Kazanma %": round(100 * (t > 0).mean(), 1) if len(t) else 0.0,
        "Getiri %": round(100 * (equity - 1), 1),
        "Maks. düşüş %": round(100 * dd, 1),
        "Kâr faktörü": round(wins / losses, 2) if losses > 0 else (np.inf if wins > 0 else 0.0),
    }


def synthetic(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0002, 0.012, n) + 0.004 * np.sin(np.arange(n) / 60)
    close = 30000 * np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.006, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.006, n))
    vol = rng.lognormal(10, 0.5, n)
    t = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=t)
    df["open_time"] = (t.view("int64") // 1_000_000)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", type=int, default=2000)
    ap.add_argument("--tf", default=None)
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    tf = args.tf or cfg["timeframe"]
    min_score = cfg["scoring"]["min_score"]
    rows = []

    symbols = ["SAHTE-1", "SAHTE-2"] if args.synthetic else cfg["symbols"]
    for k, symbol in enumerate(symbols):
        if args.synthetic:
            df = synthetic(args.candles, seed=k)
        else:
            from data import get_klines
            print(f"{symbol} indiriliyor...")
            df = get_klines(symbol, tf, args.candles)

        signals = st.run_all(df, cfg)
        for name in signals.columns:
            rows.append({"Coin": symbol, "Strateji": st.STRATEGIES[name][1], **simulate(df, signals[name])})

        score = st.combined_score(df, signals, cfg)
        combo = pd.Series(np.where(score >= min_score, 1, np.where(score <= -min_score, -1, 0)), index=df.index)
        rows.append({"Coin": symbol, "Strateji": f"KOMBİNE (puan ≥ {min_score})", **simulate(df, combo)})

        bh = df["close"].iloc[-1] / df["open"].iloc[0] - 1
        curve = df["close"] / df["close"].cummax() - 1
        rows.append({"Coin": symbol, "Strateji": "Al ve tut", "İşlem": 1, "Kazanma %": float(bh > 0) * 100,
                     "Getiri %": round(100 * bh, 1), "Maks. düşüş %": round(100 * curve.min(), 1),
                     "Kâr faktörü": np.nan})

    res = pd.DataFrame(rows)
    pd.set_option("display.width", 160)
    for sym, g in res.groupby("Coin", sort=False):
        print(f"\n=== {sym} ({tf}, {args.candles} mum) ===")
        print(g.drop(columns="Coin").sort_values("Getiri %", ascending=False).to_string(index=False))

    summary = (res.groupby("Strateji")
               .agg({"Getiri %": "mean", "Kazanma %": "mean", "Maks. düşüş %": "mean", "İşlem": "sum"})
               .round(1).sort_values("Getiri %", ascending=False))
    print("\n=== TÜM COİNLERİN ORTALAMASI ===")
    print(summary.to_string())

    res.to_csv(ROOT / "backtest_sonuclari.csv", index=False, encoding="utf-8-sig")
    html = f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<title>Strateji Karşılaştırması</title>
<style>body{{font-family:system-ui,sans-serif;margin:32px;color:#1d1d1f}}
table{{border-collapse:collapse;margin:12px 0 28px}}td,th{{padding:6px 12px;border-bottom:1px solid #ddd;text-align:right}}
th{{background:#f4f4f6}}td:first-child,th:first-child{{text-align:left}}</style></head><body>
<h1>Strateji Karşılaştırması</h1><p>Periyot: {tf} · {args.candles} mum · komisyon %0.1 · sadece long</p>
<h2>Ortalama (tüm coinler)</h2>{summary.to_html()}
<h2>Coin bazında</h2>{res.to_html(index=False)}
<p><i>Geçmiş performans gelecekteki sonuçları garanti etmez.</i></p></body></html>"""
    (ROOT / "backtest_rapor.html").write_text(html, encoding="utf-8")
    print("\nKaydedildi: backtest_sonuclari.csv, backtest_rapor.html")


if __name__ == "__main__":
    main()
