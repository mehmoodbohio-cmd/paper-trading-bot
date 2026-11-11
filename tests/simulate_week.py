"""
Offline test: runs the real bot for a simulated week against a FAKE market
(made-up prices, headlines and company numbers). No internet needed.
  python tests/simulate_week.py
"""

import datetime as dt
import hashlib
import random
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import engine  # noqa: E402

GOOD = ["{n} beats estimates as demand surges", "{n} raises guidance after record revenue",
        "Analyst upgrade: {n} upgraded to buy, price target raised", "{n} wins contract with major cloud provider",
        "{n} reports losses smaller than expected"]
BAD = ["{n} misses estimates, cuts guidance", "SEC investigation into {n} accounting",
       "{n} downgraded to sell on weak demand", "{n} faces class action lawsuit"]
NEUTRAL = ["{n} to present at industry conference", "What to watch for {n} this week", "{n} names new board member"]


def _seed(t):
    return int(hashlib.md5(t.encode()).hexdigest()[:8], 16)


class FakeData:
    def __init__(self):
        self.now = None
        self._series = {}

    def _bars(self, t):
        """30-minute price bars for the past 400 days up to the end of the sim."""
        if t not in self._series:
            rng = np.random.default_rng(_seed(t))
            idx = pd.date_range("2025-10-01", "2026-11-25", freq="30min", tz="UTC")
            crypto = t.endswith("-USD") and t != "EURUSD=X"
            vol = rng.uniform(0.004, 0.012) if crypto else rng.uniform(0.002, 0.006)
            drift = rng.normal(0.00002, 0.00006)
            # regime changes make some assets trend, some fall
            shocks = rng.normal(drift, vol, len(idx))
            shocks += np.repeat(rng.normal(0, 0.0004, len(idx) // 960 + 1), 960)[:len(idx)]
            price = 50 * np.exp(np.cumsum(shocks))
            volume = rng.lognormal(12, 0.4, len(idx)) * (1 + 3 * (rng.random(len(idx)) < 0.01))
            self._series[t] = pd.DataFrame({"Close": price, "Volume": volume}, index=idx)
        return self._series[t]

    def _until_now(self, t):
        b = self._bars(t)
        return b[b.index <= self.now]

    def daily(self, tickers, period="1y"):
        out = {}
        for t in tickers:
            b = self._until_now(t)
            d = b.resample("1D").agg({"Close": "last", "Volume": "sum"}).dropna()
            out[t] = d.tail(250 if period == "1y" else 126)
        return out

    def intraday(self, tickers):
        return {t: self._until_now(t).tail(5 * 48) for t in tickers}

    def fx_eurusd(self):
        return 1.08

    def fundamentals(self, t):
        r = random.Random(_seed(t))
        rev = [1e9]
        for _ in range(5):
            rev.append(rev[-1] * (1 + r.uniform(-0.05, 0.15)))
        price = float(self._until_now(t)["Close"].iloc[-1])
        return dict(shortName=f"{t} Corp", sector=r.choice(["Technology", "Energy", "Healthcare"]),
                    industry=r.choice(["Semiconductors", "Software", "Utilities", "Biotech"]),
                    marketCap=r.choice([2e9, 8e9, 30e9, 90e9, 500e9]),
                    revenueGrowth=r.uniform(-0.1, 0.5), earningsGrowth=r.uniform(-0.3, 0.6),
                    profitMargins=r.uniform(-0.2, 0.35), freeCashflow=r.choice([-1e8, 2e8, 5e8]),
                    debtToEquity=r.uniform(5, 250), forwardPE=r.uniform(8, 60),
                    targetMeanPrice=price * r.uniform(0.8, 1.5), currentPrice=price,
                    recommendationMean=r.uniform(1.5, 3.2), numberOfAnalystOpinions=r.randint(0, 30),
                    quarterly_revenue=rev, insider_net_shares=r.choice([-5000, 0, 12000]),
                    upgrades_90d=r.randint(0, 4), downgrades_90d=r.randint(0, 3),
                    longBusinessSummary=r.choice(["Makes memory chips for AI data centers.",
                                                  "Builds nuclear reactors.", "Sells shoes."]))

    def news(self, t):
        r = random.Random(_seed(t) + int(self.now.timestamp() // 21600))   # changes every 6h
        pool = r.choice([GOOD, BAD, NEUTRAL, NEUTRAL, NEUTRAL])
        return [{"title": r.choice(pool).format(n=t), "time": self.now.timestamp() - r.randint(0, 40000)}
                for _ in range(3)]

    def next_earnings(self, t):
        r = random.Random(_seed(t))
        return dt.date(2026, 11, 1) + dt.timedelta(days=r.randint(0, 60))


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    for d in ["state", "outbox", "reports"]:
        shutil.rmtree(root / d, ignore_errors=True)
    data = FakeData()
    start = dt.datetime(2026, 11, 11, 9, 0, tzinfo=dt.timezone.utc)
    t = start
    while t < start + dt.timedelta(days=7):
        data.now = t
        engine.run(data, now=t)
        t += dt.timedelta(minutes=30)
    print("\nEmails written to outbox/:", len(list((root / "outbox").glob("*.txt"))))
