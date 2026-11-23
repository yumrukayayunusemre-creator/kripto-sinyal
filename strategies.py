"""Stratejiler. Her biri her mum için +1 (AL), -1 (SAT) veya 0 döndürür.

Sinyaller "olay" bazlıdır: ör. RSI 30'un altından YUKARI döndüğü mumda AL verir,
30'un altında kaldığı her mumda tekrar tekrar vermez.
"""
import numpy as np
import pandas as pd

import indicators as ind


def _cross_up(a: pd.Series, b) -> pd.Series:
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a > b) & (a.shift() <= b.shift())


def _cross_down(a: pd.Series, b) -> pd.Series:
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a < b) & (a.shift() >= b.shift())


def _to_signal(buy: pd.Series, sell: pd.Series) -> pd.Series:
    sig = np.where(buy.fillna(False), 1, np.where(sell.fillna(False), -1, 0))
    return pd.Series(sig, index=buy.index)


def rsi(df, period=14, oversold=30, overbought=70, **_):
    r = ind.rsi(df["close"], period)
    # Aşırı satımdan çıkışta AL, aşırı alımdan dönüşte SAT
    return _to_signal(_cross_up(r, oversold), _cross_down(r, overbought))


def ema_cross(df, fast=9, slow=21, **_):
    f, s = ind.ema(df["close"], fast), ind.ema(df["close"], slow)
    return _to_signal(_cross_up(f, s), _cross_down(f, s))


def bollinger_volume(df, period=20, std=2.0, volume_period=20, volume_mult=1.8, **_):
    up, mid, lo = ind.bollinger(df["close"], period, std)
    vol_spike = df["volume"] > ind.sma(df["volume"], volume_period) * volume_mult
    # Hacimli kırılım: üst bandı hacimle yukarı kırarsa AL, alt bandı hacimle aşağı kırarsa SAT
    buy = (df["close"] > up) & (df["close"].shift() <= up.shift()) & vol_spike
    sell = (df["close"] < lo) & (df["close"].shift() >= lo.shift()) & vol_spike
    return _to_signal(buy, sell)


def macd(df, fast=12, slow=26, signal=9, **_):
    line, sig, _h = ind.macd(df["close"], fast, slow, signal)
    return _to_signal(_cross_up(line, sig), _cross_down(line, sig))


def supertrend(df, period=10, multiplier=3.0, **_):
    d = ind.supertrend(df, period, multiplier)
    return _to_signal((d == 1) & (d.shift() == -1), (d == -1) & (d.shift() == 1))


def stoch_rsi(df, rsi_period=14, stoch_period=14, k=3, d=3, oversold=20, overbought=80, **_):
    k_line, d_line = ind.stoch_rsi(df["close"], rsi_period, stoch_period, k, d)
    buy = _cross_up(k_line, d_line) & (k_line < oversold)
    sell = _cross_down(k_line, d_line) & (k_line > overbought)
    return _to_signal(buy, sell)


def donchian_breakout(df, period=20, **_):
    hi = df["high"].rolling(period).max().shift()
    lo = df["low"].rolling(period).min().shift()
    # Sadece ilk kırılım mumunda sinyal (trend boyunca her mumda değil)
    return _to_signal(_cross_up(df["close"], hi), _cross_down(df["close"], lo))


STRATEGIES = {
    "rsi": (rsi, "RSI dönüşü"),
    "ema_cross": (ema_cross, "EMA kesişimi"),
    "bollinger_volume": (bollinger_volume, "Bollinger + hacim patlaması"),
    "macd": (macd, "MACD kesişimi"),
    "supertrend": (supertrend, "Supertrend dönüşü"),
    "stoch_rsi": (stoch_rsi, "Stochastic RSI"),
    "donchian_breakout": (donchian_breakout, "Donchian kırılımı"),
}


def run_all(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Açık olan tüm stratejilerin sinyal sütunlarını döndürür."""
    out = pd.DataFrame(index=df.index)
    for name, params in cfg["strategies"].items():
        if not params.get("enabled", True) or name not in STRATEGIES:
            continue
        fn, _label = STRATEGIES[name]
        out[name] = fn(df, **{k: v for k, v in params.items() if k not in ("enabled", "weight")})
    return out


def combined_score(df: pd.DataFrame, signals: pd.DataFrame, cfg: dict) -> pd.Series:
    """Ağırlıklı oyların (lookback penceresindeki) toplamı."""
    lookback = cfg["scoring"].get("lookback", 1)
    score = pd.Series(0.0, index=df.index)
    for name in signals.columns:
        w = cfg["strategies"][name].get("weight", 1)
        s = signals[name]
        # Pencere içindeki en son sinyal yönü sayılır
        recent = s.replace(0, np.nan).ffill(limit=lookback - 1).fillna(0) if lookback > 1 else s
        score += w * recent
    if cfg["scoring"].get("trend_filter", False):
        trend = ind.ema(df["close"], 200)
        score = score.where(~((score > 0) & (df["close"] < trend)), 0)
        score = score.where(~((score < 0) & (df["close"] > trend)), 0)
    return score
