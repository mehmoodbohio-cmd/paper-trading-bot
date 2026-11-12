"""All the knobs in one place. Change these to change how the bot behaves.

RISK_MODE switches a whole set of settings at once:
  "careful"     small bets, tight stops, only buys strong setups
  "aggressive"  bigger bets, buys more readily, lets trades swing more
"""

RISK_MODE = "aggressive"

STARTING_CASH_EUR = 100.0

# --- Costs (paper trading still pays realistic costs) ---
FEE_PCT = 0.0025          # 0.25% per trade (fee + spread)
MIN_TRADE_EUR = 8.0       # never open a position smaller than this

FUNDAMENTAL_DEEP_DIVE = 80  # how many stocks get the (slower) fundamental check daily

# --- Reports (Berlin time) ---
DAILY_SUMMARY_HOUR = 21
GEMS_WEEKDAY = 0          # Monday
GEMS_HOUR = 8
GEMS_TOP_N = 10

PRESETS = {
    "careful": dict(
        SHORTLIST_STOCKS=10, SHORTLIST_CRYPTO=5,
        MAX_POSITIONS=6, MAX_POSITION_PCT=0.25,
        TARGET_DAILY_VOL=0.02,          # wild assets get much smaller positions
        MIN_CONFIDENCE_TO_BUY=0.60,
        STOP_LOSS={"crypto": 0.10, "us_stock": 0.07, "eu_stock": 0.07},
        TRAILING_STOP={"crypto": 0.12, "us_stock": 0.08, "eu_stock": 0.08},
        DAILY_LOSS_LIMIT=0.05,
        MAX_CORRELATION=0.80,
        EARNINGS_BLACKOUT_DAYS=3,
        MIN_HOLD_HOURS=6, COOLDOWN_HOURS=24,
        BAD_NEWS_SELL=-0.50, BAD_NEWS_NO_BUY=-0.15,
        CAUTIOUS_PENALTY=0.05,          # confidence taken off when the market looks shaky
        RISK_OFF_BLOCKS_BUYS=True,
    ),
    "aggressive": dict(
        SHORTLIST_STOCKS=12, SHORTLIST_CRYPTO=8,   # wider net
        MAX_POSITIONS=5, MAX_POSITION_PCT=0.40,    # fewer, bigger bets
        TARGET_DAILY_VOL=0.05,          # barely shrinks bets on wild coins/small caps
        MIN_CONFIDENCE_TO_BUY=0.50,     # buys more readily
        STOP_LOSS={"crypto": 0.15, "us_stock": 0.10, "eu_stock": 0.10},     # room to swing
        TRAILING_STOP={"crypto": 0.18, "us_stock": 0.12, "eu_stock": 0.12}, # let winners run
        DAILY_LOSS_LIMIT=0.10,
        MAX_CORRELATION=0.85,
        EARNINGS_BLACKOUT_DAYS=1,       # will hold through earnings, just not buy the day before
        MIN_HOLD_HOURS=6, COOLDOWN_HOURS=12,
        BAD_NEWS_SELL=-0.60, BAD_NEWS_NO_BUY=-0.30,
        CAUTIOUS_PENALTY=0.0,           # ignores "cautious" markets
        RISK_OFF_BLOCKS_BUYS=True,      # still stays out when a market is actually crashing
    ),
}

globals().update(PRESETS[RISK_MODE])
