# Stock Pattern Lab

NSE Momentum Lifecycle Scanner.

Lifecycle: Discovery -> Candidate -> True VCP -> Breakout -> BUY -> Defense -> EXIT

V1: daily Upstox historical-data scanner with candidate scoring, rules-based VCP detection, breakout checks and Telegram alerts.

Secrets required in GitHub Actions: UPSTOX_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.

Next: Nifty 500 benchmark, persistent lifecycle state, live Upstox WebSocket monitoring, defense/exit engine and cooldown.
