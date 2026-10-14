import requests
from urllib.parse import quote

from config import settings


def _chat_ids():
    raw = settings.TELEGRAM_CHAT_ID
    return [x.strip() for x in raw.split(",") if x.strip()]


def send(message, chart_symbol=None):
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        print(message)
        return

    payload = {
        "text": message,
    }

    if chart_symbol:
        symbol = str(chart_symbol).strip().upper()
        chart_url = (
            "https://www.tradingview.com/chart/?symbol="
            + quote(f"NSE:{symbol}", safe="")
        )
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {
                    "text": "📈 Chart",
                    "url": chart_url,
                }
            ]]
        }

    for chat_id in _chat_ids():
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    **payload,
                },
                timeout=20,
            )
            if not r.ok:
                print(
                    f"Telegram send failed for chat_id={chat_id}: "
                    f"HTTP {r.status_code} | {r.text}"
                )
                continue
        except Exception as exc:
            print(f"Telegram send failed for chat_id={chat_id}: {exc}")
            continue


def format_result(r, state):
    return (
        f"{state} | {r['symbol']}\n"
        f"Price ₹{r['price']:.2f} | Score {r['score']}/7\n"
        f"Pivot ₹{r['pivot']:.2f} | ATR {r['atr_pct']:.1f}%\n"
        f"RS20 {r['rs20']:.1f}% | 52W distance {r['from_52w_high']:.1f}%\n"
        f"Swing {r['swing_return']:.1f}% | RVOL {r['rvol']:.1f}x\n"
        f"VCP={r['vcp']} | Breakout={r['vcp_breakout']} | Pocket Pivot={r['pocket_pivot']}"
    )
