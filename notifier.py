"""Telegram bildirimi."""
import os

import requests


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[uyarı] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID tanımlı değil, mesaj sadece ekrana yazıldı:\n" + text)
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=15,
    )
    if not r.ok:
        print("[hata] Telegram:", r.status_code, r.text)
    return r.ok
