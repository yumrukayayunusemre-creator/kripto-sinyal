"""Fiyat verisi: Binance'in herkese açık piyasa verisi (API anahtarı gerekmez).

GitHub sunucuları ABD'de olduğu için ana api.binance.com engellenebilir;
bu yüzden önce data-api.binance.vision, olmazsa OKX denenir.
"""
import time

import pandas as pd
import requests

OKX_BARS = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1Dutc"}
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def _binance(symbol, interval, limit, end_ms=None):
    params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
    if end_ms:
        params["endTime"] = end_ms
    r = requests.get("https://data-api.binance.vision/api/v3/klines", params=params, timeout=15)
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows).iloc[:, :7]
    df.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
    return df


def _okx(symbol, interval, limit, end_ms=None):
    inst = symbol.replace("USDT", "-USDT")
    params = {"instId": inst, "bar": OKX_BARS[interval], "limit": min(limit, 300)}
    if end_ms:
        params["after"] = end_ms
    r = requests.get("https://www.okx.com/api/v5/market/history-candles", params=params, timeout=15)
    r.raise_for_status()
    rows = r.json()["data"][::-1]
    df = pd.DataFrame([x[:6] for x in rows], columns=["open_time", "open", "high", "low", "close", "volume"])
    df["close_time"] = df["open_time"].astype("int64") + TF_MS[interval] - 1
    return df


def _clean(df):
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = df["open_time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.drop_duplicates("open_time").sort_values("open_time").set_index("time")


def get_klines(symbol: str, interval: str = "1h", limit: int = 300, closed_only: bool = True) -> pd.DataFrame:
    """Son `limit` mumu döndürür. closed_only=True ise henüz kapanmamış mumu atar."""
    last_err = None
    for fetch in (_binance, _okx):
        try:
            frames, end, need = [], None, limit + 1
            while need > 0:
                part = fetch(symbol, interval, need, end)
                if part.empty:
                    break
                frames.insert(0, part)
                need -= len(part)
                end = int(part["open_time"].astype("int64").min()) - 1
                time.sleep(0.2)
            df = _clean(pd.concat(frames))
            if closed_only:
                now_ms = int(time.time() * 1000)
                df = df[df["close_time"] < now_ms]
            return df.tail(limit)
        except Exception as e:  # bir kaynak olmazsa diğerini dene
            last_err = e
    raise RuntimeError(f"{symbol} verisi alınamadı: {last_err}")
