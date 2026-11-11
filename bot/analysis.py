"""
The brain. Turns raw prices and company numbers into scores from 0 to 1,
and always keeps the human-readable reasons so every decision can be explained.

  technical_scores()   -> trend, momentum, RSI, unusual volume   (charts + quant)
  fundamental_score()  -> growth, profits, cash, debt, valuation (company health)
  gem_score()          -> fundamentals-first score for the hidden gems report
"""

import numpy as np
import pandas as pd

THEMES = {
    "AI / data centers": ["artificial intelligence", " ai ", "data center", "machine learning", "gpu", "accelerat"],
    "Semiconductors / memory": ["semiconductor", "memory", "dram", "nand", "chip", "wafer"],
    "Power & grid": ["power generation", "electric grid", "transmission", "utility-scale", "cooling", "electrical"],
    "Nuclear": ["nuclear", "uranium", "reactor"],
    "Energy storage": ["battery", "energy storage"],
    "Space": ["satellite", "space", "launch vehicle"],
    "Defense / drones": ["defense", "drone", "unmanned", "military"],
    "Quantum computing": ["quantum"],
    "Cybersecurity": ["cybersecurity", "security platform", "threat"],
    "Robotics / automation": ["robot", "automation"],
    "Obesity / GLP-1": ["obesity", "glp-1", "weight management"],
    "Gene editing / biotech": ["gene editing", "crispr", "rna"],
}


# ---------------------------------------------------------------- indicators
def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def daily_volatility(close, days=20):
    return float(close.pct_change().tail(days).std() or 0.0)


def _pct_rank(series):
    return series.rank(pct=True).fillna(0.5)


# ---------------------------------------------------------------- technical
def technical_scores(daily):
    """daily: {ticker: DataFrame}. Returns {ticker: {score, parts, reasons, vol}}.
    Momentum is ranked against the other assets in the same scan (quant style)."""
    rows = {}
    for t, df in daily.items():
        c = df["Close"].dropna()
        if len(c) < 60:
            continue
        v = df["Volume"].fillna(0) if "Volume" in df else pd.Series(0, index=df.index)
        vol = daily_volatility(c)
        ma20, ma50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
        r20 = c.iloc[-1] / c.iloc[-21] - 1
        r60 = c.iloc[-1] / c.iloc[-61] - 1
        r120 = c.iloc[-1] / c.iloc[-121] - 1 if len(c) > 121 else r60
        vol_ratio = (v.tail(5).mean() / v.tail(50).mean()) if v.tail(50).mean() > 0 else 1.0
        rows[t] = dict(price=float(c.iloc[-1]), ma20=ma20, ma50=ma50, r20=r20, r60=r60, r120=r120,
                       rsi=float(rsi(c).iloc[-1]), vol=vol, vol_ratio=float(vol_ratio),
                       up5=c.iloc[-1] > c.iloc[-6],
                       high52=float(c.tail(252).max()))
    if not rows:
        return {}
    tab = pd.DataFrame(rows).T
    # Risk-adjusted momentum: a 20% rise in a calm stock beats 20% in a wild one
    raw_mom = (0.5 * tab.r60 + 0.3 * tab.r20 + 0.2 * tab.r120) / (tab.vol.astype(float) * np.sqrt(60) + 1e-9)
    mom_rank = _pct_rank(raw_mom.astype(float))

    out = {}
    for t, r in tab.iterrows():
        reasons = []
        trend = 0.5 * (r.price > r.ma50) + 0.5 * (r.ma20 > r.ma50)
        if trend == 1:
            reasons.append("uptrend (price above 50-day average, 20-day above 50-day)")
        elif trend == 0:
            reasons.append("downtrend (below its moving averages)")
        m = float(mom_rank[t])
        reasons.append(f"momentum stronger than {m:.0%} of the scan (3-month {r.r60:+.0%})")
        if 45 <= r.rsi <= 68:
            rsi_s = 1.0
        elif 68 < r.rsi <= 75 or 35 <= r.rsi < 45:
            rsi_s = 0.5
        else:
            rsi_s = 0.0
        if r.rsi > 75:
            reasons.append(f"RSI {r.rsi:.0f} = overbought, may be late to the party")
        else:
            reasons.append(f"RSI {r.rsi:.0f}")
        volume_s = float(np.clip((r.vol_ratio - 1) / 1.5, 0, 1)) if r.up5 else 0.0
        if volume_s > 0.3:
            reasons.append(f"unusual buying volume ({r.vol_ratio:.1f}x normal)")
        score = 0.35 * m + 0.25 * trend + 0.20 * rsi_s + 0.20 * volume_s
        out[t] = dict(score=float(score), reasons=reasons, vol=float(r.vol), price=float(r.price),
                      rsi=float(r.rsi), r60=float(r.r60), vol_ratio=float(r.vol_ratio),
                      off_high=float(r.price / r.high52 - 1),
                      parts=dict(momentum=m, trend=float(trend), rsi=rsi_s, volume=volume_s))
    return out


# ---------------------------------------------------------------- fundamental
def _tier(x, cuts):
    """cuts = [(threshold, points), ...] high to low; returns points of first threshold passed."""
    for thr, pts in cuts:
        if x >= thr:
            return pts
    return 0.0


def fundamental_score(f):
    """Company health 0..1 from whatever numbers Yahoo has. Returns (score, good[], risks[])."""
    checks, good, risks = [], [], []

    def add(points, good_msg=None, bad_msg=None):
        checks.append(points)
        if points >= 0.7 and good_msg:
            good.append(good_msg)
        if points <= 0.3 and bad_msg:
            risks.append(bad_msg)

    g = f.get("revenueGrowth")
    if g is not None:
        add(_tier(g, [(0.25, 1), (0.10, 0.7), (0.0, 0.4)]),
            f"sales growing {g:+.0%} a year", f"sales {'shrinking' if g < 0 else 'barely growing'} ({g:+.0%})")
    eg = f.get("earningsGrowth")
    if eg is not None:
        add(_tier(eg, [(0.25, 1), (0.10, 0.7), (0.0, 0.4)]),
            f"profits growing {eg:+.0%}", f"profits falling ({eg:+.0%})")
    pm = f.get("profitMargins")
    if pm is not None:
        add(1.0 if pm > 0.15 else 0.6 if pm > 0 else 0.2,
            f"keeps {pm:.0%} of sales as profit", f"loses money (margin {pm:.0%})")
    fcf = f.get("freeCashflow")
    if fcf is not None:
        add(1.0 if fcf > 0 else 0.0, "generates cash", "burns cash")
    de = f.get("debtToEquity")
    if de is not None:
        add(1.0 if de < 50 else 0.6 if de < 150 else 0.2, "low debt", f"high debt (debt/equity {de:.0f}%)")

    # Valuation vs growth: PEG < 1 means cheap for how fast it grows
    peg = f.get("pegRatio")
    if peg is None and f.get("forwardPE") and eg and eg > 0:
        peg = f["forwardPE"] / (eg * 100)
    if peg is not None and peg > 0:
        add(1.0 if peg < 1 else 0.6 if peg < 2 else 0.2,
            f"cheap for its growth (PEG {peg:.1f})", f"expensive for its growth (PEG {peg:.1f})")
    elif f.get("forwardPE") is not None and f["forwardPE"] < 0:
        add(0.2, None, "not profitable on forward estimates")

    tgt, px = f.get("targetMeanPrice"), f.get("currentPrice")
    if tgt and px:
        up = tgt / px - 1
        add(_tier(up, [(0.25, 1), (0.10, 0.6), (0.0, 0.3)]),
            f"analysts' average target {up:+.0%} above price", f"trades above analyst targets ({up:+.0%})")
    rec = f.get("recommendationMean")
    if rec and (f.get("numberOfAnalystOpinions") or 0) >= 3:
        add(1.0 if rec <= 2 else 0.6 if rec <= 2.5 else 0.2, "analysts rate it a buy", "analysts are lukewarm")

    qr = f.get("quarterly_revenue")
    if qr and len(qr) >= 3 and all(x > 0 for x in qr[-3:]):
        g1, g2 = qr[-2] / qr[-3] - 1, qr[-1] / qr[-2] - 1
        add(1.0 if g2 > g1 and g2 > 0 else 0.5 if g2 > 0 else 0.1,
            f"growth speeding up ({g1:+.0%} -> {g2:+.0%} quarter on quarter)",
            f"revenue fell last quarter ({g2:+.0%})")
    ins = f.get("insider_net_shares")
    if ins is not None:
        add(1.0 if ins > 0 else 0.3, "insiders buying their own shares", None)
    up, down = f.get("upgrades_90d"), f.get("downgrades_90d")
    if up is not None and (up or down):
        add(1.0 if up > down else 0.5 if up == down else 0.1,
            f"{up} analyst upgrades vs {down} downgrades (90 days)", f"more downgrades ({down}) than upgrades ({up})")
    sp = f.get("shortPercentOfFloat")
    if sp and sp > 0.15:
        risks.append(f"{sp:.0%} of shares sold short: many investors bet against it")

    if not checks:
        return None, [], []
    # Confidence shrinks toward neutral when we have few data points
    n = len(checks)
    raw = float(np.mean(checks))
    return 0.5 + (raw - 0.5) * min(1.0, n / 6), good, risks


def themes_for(f):
    text = f" {(f.get('longBusinessSummary') or '').lower()} {(f.get('industry') or '').lower()} "
    return [name for name, kws in THEMES.items() if any(k in text for k in kws)]


def gem_score(f, tech):
    """Hidden gems = strong fundamentals, not a mega cap, price starting to turn up."""
    fs, good, risks = fundamental_score(f)
    if fs is None:
        return None
    cap = f.get("marketCap") or 0
    if cap > 200e9:
        return None                                 # everyone already knows these
    small = 1.0 if 0 < cap < 20e9 else 0.5 if cap < 60e9 else 0.1
    themes = themes_for(f)
    turning = 0.0
    risks = list(risks)
    if tech:
        turning = 0.5 * tech["parts"]["trend"] + 0.5 * tech["parts"]["volume"]
        if tech["rsi"] > 75:
            risks.append(f"price ran up very fast (RSI {tech['rsi']:.0f}); a pullback is common after this")
        if tech["off_high"] < -0.5:
            risks.append(f"still {tech['off_high']:.0%} below its 1-year high: something went badly wrong before")
    score = 0.65 * fs + 0.15 * small + 0.10 * turning + 0.10 * (1.0 if themes else 0.0)
    return dict(score=score, fund=fs, good=good, risks=risks, themes=themes, cap=cap, turning=turning)


# ---------------------------------------------------------------- helpers
def correlation(a, b, days=60):
    ra, rb = a.pct_change().tail(days), b.pct_change().tail(days)
    joined = pd.concat([ra, rb], axis=1, join="inner").dropna()
    if len(joined) < 20:
        return 0.0
    return float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))


def intraday_signal(df30):
    """Short-term check on 30-minute bars. Returns (score 0..1, reason)."""
    c = df30["Close"].dropna()
    if len(c) < 25:
        return 0.5, "not enough 30-min data"
    ema20 = c.ewm(span=20).mean()
    above = c.iloc[-1] > ema20.iloc[-1]
    mom2h = c.iloc[-1] / c.iloc[-5] - 1
    if above and mom2h > 0:
        return 1.0, f"short-term: above its 10-hour average and up {mom2h:+.1%} in 2h"
    if above:
        return 0.6, "short-term: above its 10-hour average, pausing"
    if mom2h > 0:
        return 0.4, f"short-term: bouncing {mom2h:+.1%} but still below 10-hour average"
    return 0.1, f"short-term: falling ({mom2h:+.1%} in 2h), below 10-hour average"
