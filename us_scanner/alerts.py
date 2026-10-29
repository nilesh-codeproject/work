import os
from urllib.parse import quote
import requests

def send(message, chart_symbol=None):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_ids = [x.strip() for x in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if x.strip()]
    if not token or not chat_ids:
        print(message)
        return
    payload = {"text": message}
    if chart_symbol:
        symbol = str(chart_symbol).strip().upper()
        payload["reply_markup"] = {"inline_keyboard": [[{
            "text": "📈 Chart",
            "url": "https://www.tradingview.com/chart/?symbol=" + quote(f"NASDAQ:{symbol}", safe="")
        }]]}
    for chat_id in chat_ids:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, **payload},
                timeout=20,
            )
            r.raise_for_status()
        except requests.RequestException as exc:
            print(f"Telegram send failed: {exc}")
