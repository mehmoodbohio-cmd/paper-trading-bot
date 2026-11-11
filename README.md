# Paper Trading Bot (pretend money only)

A bot that trades **100 EUR of pretend money** in stocks and crypto, every 30 minutes,
and emails you before every trade with its reasons. It never connects to a broker,
so it can't spend real money.

## What it does, in simple words

1. **Big net, once a day:** looks at ~320 stocks (US + German) and 50 coins and gives
   each a score: is it trending up, is it stronger than the others, is it overheated
   (RSI), are unusual amounts being bought (volume)? The best 80 stocks also get a
   **company health check** (sales growth, profits, cash, debt, price vs. growth,
   analyst targets, insiders buying). It keeps the **top 10 stocks + top 5 coins**.
2. **Small net, every 30 minutes:** checks those 15 plus what it owns:
   - **news** (Loughran-McDonald finance dictionary, about 4,100 words, plus ~100 trading phrases, with "not" handling)
   - **short-term price action** (30-minute bars)
   - **market mood** (if the S&P 500, DAX or Bitcoin is crashing, it doesn't buy)
3. **Buys** only when confidence is 60% or more. Bigger bets when more confident, smaller bets when an asset is wild.
4. **Sells** on: stop-loss (-7% stocks / -10% crypto), trailing stop, bad news,
   trend break (only after holding 6+ hours), or dropping out of the scan.
5. **Safety rules:** max 6 positions, max 25% per position, no "twins" (two assets
   that move together), no buying 3 days before earnings, stops buying for the day after a -5% day.
6. **Emails:** one before every trade, a **daily summary at 21:00** (Berlin), and a
   **hidden gems report every Monday morning**.
7. **Trade journal:** 24 hours after each trade it checks whether the trade was right.

All settings are in `bot/config.py`.

## Setup (about 15 minutes)

### 1. Put the code on GitHub
1. Create a free account at github.com.
2. Click **New repository**, name it `paper-trading-bot`, choose **Private**, click **Create**.
3. Click **uploading an existing file** and drag in everything from this folder
   **including the hidden `.github` folder** (on Mac press Cmd+Shift+. to see it).
   If the upload page won't take the folder, create the file
   `.github/workflows/bot.yml` with **Add file > Create new file** and paste its contents.

### 2. Gmail App Password (so the bot can email you)
1. Your Google account needs 2-Step Verification turned on.
2. Go to myaccount.google.com/apppasswords, create one called "trading bot",
   and copy the 16-letter password.

### 3. Give the bot the email details
In your GitHub repo: **Settings > Secrets and variables > Actions > New repository secret**. Add three:

| Name | Value |
|---|---|
| `EMAIL_USER` | your Gmail address |
| `EMAIL_PASS` | the 16-letter app password |
| `EMAIL_TO` | where to send the emails (can be the same address) |

### 4. Switch it on
1. Open the **Actions** tab and enable workflows if GitHub asks.
2. Click **Paper trading bot > Run workflow** to start it right away.
3. From then on it runs by itself every 30 minutes.

Without the email secrets it still works, and saves the emails into the `outbox/` folder instead.

## Useful buttons (Actions > Paper trading bot > Run workflow)
- **extra = summary**: send the daily summary now
- **extra = gems**: send the hidden gems report now
- **reset = true**: start over with a fresh 100 EUR

## Where to look
- `state/portfolio.json`: cash, holdings, value history
- `state/journal.json`: every trade with reasons and whether it was right
- `reports/`: hidden gems reports

## Cost
Free. A private repo gets 2,000 free GitHub Actions minutes a month; this bot uses
roughly 80-100 a day, so a one-week test fits easily. For a full month, make the
repo public (unlimited minutes) or reduce the schedule to every hour.

## Honest limits
- Yahoo Finance data is free but unofficial; it can lag or briefly block cloud servers.
  The bot retries and emails you if data stops coming.
- GitHub sometimes starts scheduled runs a few minutes late.
- Fees are modelled as 0.25% per trade. A broker charging a flat 1 EUR would cost
  far more on 10-15 EUR positions.
- One week is too short to prove a strategy works. Compare it against "100 EUR in the
  S&P 500" in the daily summary: if it can't beat that, the strategy isn't adding value.

## Test it without internet
```
pip install -r requirements.txt
python tests/simulate_week.py
```
Runs a full week against a fake market and writes all emails to `outbox/`.
