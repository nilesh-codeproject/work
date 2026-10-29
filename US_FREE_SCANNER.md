# US Free Scanner

Branch: `Nilesh_US_Free_Scanner`

## Flow

1. Pre-market workflow downloads the broad US common-stock universe from Nasdaq Trader.
2. Alpaca historical bars are used to score the full universe.
3. The strongest 30 candidates are written to `us_candidates.csv` and uploaded as an artifact.
4. The live workflow downloads that artifact.
5. At the US open, Alpaca's free IEX WebSocket monitors up to 30 candidates.
6. A BUY alert requires an ORB break, projected RVOL >= 1.30x, prior-day breakout >= 0.5%, and current price above the prior close.
7. Telegram alerts include a `📈 Chart` inline button.

## GitHub secrets

Add these repository secrets before running the workflows:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` can reuse the same values already used by the India scanner.

## Workflows

`US Free Pre-Market Scanner` is scheduled and also supports manual dispatch.

`US Free Live Alerts` supports manual dispatch and has two UTC schedules to cover US daylight/standard-time opens. The live process exits unless it starts near 09:30 ET.

GitHub's six-hour job limit means this free version intentionally stops around 15:25 ET rather than running through the final part of the session.

## Data limitation

The free Alpaca Basic stock feed is IEX-only and supports 30 simultaneous WebSocket symbols. IEX is a single US exchange rather than a consolidated all-exchange feed, so the live alert is a candidate-monitoring system, not full-market consolidated surveillance.