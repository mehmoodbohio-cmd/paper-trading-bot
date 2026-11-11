"""All the knobs in one place. Change these to change how the bot behaves."""

STARTING_CASH_EUR = 100.0

# --- Costs (paper trading still pays realistic costs) ---
FEE_PCT = 0.0025          # 0.25% per trade (fee + spread). A €1 flat fee would eat
                          # ~7% of a €15 position, so we model a percentage broker/exchange.
MIN_TRADE_EUR = 8.0       # never open a position smaller than this

# --- The two nets ---
SHORTLIST_STOCKS = 10     # best stocks kept after the daily big scan
SHORTLIST_CRYPTO = 5      # best coins kept after the daily big scan
FUNDAMENTAL_DEEP_DIVE = 80  # how many stocks get the (slower) fundamental check daily

# --- Position sizing (Medallion idea: many small bets, sized by confidence) ---
MAX_POSITIONS = 6
MAX_POSITION_PCT = 0.25   # no single bet bigger than 25% of the portfolio
TARGET_DAILY_VOL = 0.02   # calm assets get bigger positions, wild ones smaller
MIN_CONFIDENCE_TO_BUY = 0.60   # 0..1, below this the bot holds cash

# --- Risk rules ---
STOP_LOSS = {"crypto": 0.10, "us_stock": 0.07, "eu_stock": 0.07}
TRAILING_STOP = {"crypto": 0.12, "us_stock": 0.08, "eu_stock": 0.08}
DAILY_LOSS_LIMIT = 0.05   # down 5% today -> no new buys until tomorrow
MAX_CORRELATION = 0.80    # "no twins": skip assets that move like something we hold
EARNINGS_BLACKOUT_DAYS = 3  # don't buy a stock this close to its earnings report
MIN_HOLD_HOURS = 6        # soft exits (trend wobble) wait this long; stop-loss & bad news never wait
COOLDOWN_HOURS = 24      # after selling something, don't rebuy it for a day
BAD_NEWS_SELL = -0.50     # news score that forces a sell
BAD_NEWS_NO_BUY = -0.15   # news score that blocks a buy

# --- Reports (Berlin time) ---
DAILY_SUMMARY_HOUR = 21
GEMS_WEEKDAY = 0          # Monday
GEMS_HOUR = 8
GEMS_TOP_N = 10
