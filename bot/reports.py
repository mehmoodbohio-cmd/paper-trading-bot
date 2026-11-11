"""Daily summary email and the weekly hidden gems report."""

import datetime as dt
import time

from . import analysis as A
from . import config as C
from zoneinfo import ZoneInfo
from .universe import MARKET_BENCHMARKS, all_stocks, currency, pretty


BERLIN = ZoneInfo("Europe/Berlin")


def _eur(price, t, fx):
    return price / fx if currency(t) == "USD" else price


def daily_summary(pf, journal, scan, daily, fx, now, price_now):
    now = now.astimezone(BERLIN)
    today = now.date().isoformat()
    value = pf["cash"]
    hold_lines = []
    for t, p in pf["positions"].items():
        px = price_now(t) or p["last_price"]
        v = p["units"] * _eur(px, t, fx)
        value += v
        pnl = v - p["cost_eur"]
        hold_lines.append(f"  HOLD {pretty(t):7s} {v:7.2f} EUR  {pnl:+6.2f} EUR ({pnl / p['cost_eur']:+.1%})  "
                          f"bought {p['opened'][:16].replace('T', ' ')}\n"
                          f"       why still holding: stop-loss/trailing stop not hit, news and trend still OK")
    total = value - C.STARTING_CASH_EUR
    day = value - pf["day_start_value"]

    todays = [j for j in journal if j["time"][:10] == today]
    trade_lines = []
    for j in todays:
        trade_lines.append(f"  {j['time'][11:16]} UTC  {j['side']:4s} {pretty(j['ticker']):7s} {j['eur']:7.2f} EUR"
                           f"  - {j['reasons'][0]}")

    graded = [j for j in journal if j["check"]]
    right = sum(1 for j in graded if j["check"]["right"])

    bench_lines = []
    for name, t in MARKET_BENCHMARKS.items():
        start = pf["benchmarks_start"].get(t)
        if start and t in daily:
            last = float(daily[t]["Close"].dropna().iloc[-1])
            bench_lines.append(f"  100 EUR in {pretty(t)} would now be {100 * last / start:.2f} EUR")

    body = f"""DAILY SUMMARY - {now:%A %d %B %Y}   (pretend money)

PORTFOLIO
  Value now:        {value:.2f} EUR
  Today:            {day:+.2f} EUR ({day / pf['day_start_value']:+.1%})
  Since start:      {total:+.2f} EUR ({total / C.STARTING_CASH_EUR:+.1%})
  Cash:             {pf['cash']:.2f} EUR
  Fees paid so far: {pf['fees_paid']:.2f} EUR

COMPARE: would doing nothing have been better?
{chr(10).join(bench_lines) or '  (not enough data yet)'}

TODAY'S TRADES ({len(todays)})
{chr(10).join(trade_lines) or '  none - no setup was good enough'}

HOLDING
{chr(10).join(hold_lines) or '  nothing - all in cash'}

STRATEGY IN ONE PARAGRAPH
  Each day the bot scanned {scan.get('counts', {}).get('stocks', '?')} stocks and {scan.get('counts', {}).get('crypto', '?')} coins,
  scored them on trend, momentum, RSI, unusual volume and (for the best 80 stocks)
  company health, and kept the top 15. Every 30 minutes it checked those 15 plus
  its holdings against short-term price action, news and market mood. It buys only
  when confidence is above {C.MIN_CONFIDENCE_TO_BUY:.0%}, sizes bets by confidence and volatility,
  and sells on stop-loss, trailing stop, bad news, or a broken trend.

MARKET MOOD
{chr(10).join(f'  {k}: {v[0]} - {v[1]}' for k, v in pf.get('mood', {}).items())}

TODAY'S SHORTLIST
  {', '.join(pretty(t) for t in scan.get('shortlist', []))}

WHY IT DIDN'T BUY SOME (latest run)
{chr(10).join('  ' + s for s in pf.get('last_skipped', [])[:8]) or '  -'}

TRADE JOURNAL: was the bot right 24h later?
  {right}/{len(graded)} trades went the right way{f' ({right / len(graded):.0%})' if graded else ''}
"""
    subject = f"Daily summary {now:%d %b}: {value:.2f} EUR ({total / C.STARTING_CASH_EUR:+.1%} since start)"
    return subject, body


def hidden_gems(data, scan, fund_cache, now):
    """Fundamentals-first scan of every stock. Mega caps are excluded."""
    today = now.astimezone(BERLIN).date().isoformat()
    tech = scan.get("tech_all", {})
    results = []
    for t in all_stocks():
        f = fund_cache.get(t)
        if not f or (now.astimezone(BERLIN).date() - dt.date.fromisoformat(f.get("_date", "2000-01-01"))).days > 7:
            f = data.fundamentals(t)
            f["_date"] = today
            fund_cache[t] = f
            time.sleep(0.2)
        g = A.gem_score(f, tech.get(t))
        if g and len(g["good"]) >= 3:
            results.append((g["score"], t, f, g))
    results.sort(reverse=True, key=lambda x: x[0])

    lines = [f"HIDDEN GEMS REPORT - week of {now:%d %B %Y}",
             "",
             "Companies (not mega caps) showing the early signs: growing faster, healthy",
             "finances, reasonable price for their growth, analysts warming up, and price",
             "starting to turn. This is a research list, not a buy list: check each one yourself.",
             ""]
    for i, (score, t, f, g) in enumerate(results[:C.GEMS_TOP_N], 1):
        cap = f"{g['cap'] / 1e9:.1f}B" if g["cap"] else "?"
        tt = tech.get(t)
        chart = ""
        if tt:
            chart = (f"   Chart:  RSI {tt['rsi']:.0f}, 3-month {tt['r60']:+.0%}, "
                     f"{tt['off_high']:+.0%} from 1-year high, volume {tt['vol_ratio']:.1f}x normal\n")
        lines += [
            f"{i}. {f.get('shortName') or t} ({t})  - gem score {score:.2f}",
            f"   {f.get('sector') or ''} / {f.get('industry') or ''}, market cap {cap}",
            "   Why it's on the list:",
            *[f"     + {x}" for x in g["good"][:6]],
            f"   Big trends it's part of: {', '.join(g['themes']) or 'none detected'}",
            chart.rstrip("\n") if chart else "   Chart:  no data",
            "   What could go wrong:",
            *([f"     - {x}" for x in g["risks"][:4]] or ["     - no red flags in the numbers; check debt, competition and valuation yourself"]),
            "",
        ]
    if not results:
        lines.append("No stock passed the checks this week.")
    lines.append(f"Scanned {len(all_stocks())} stocks. Data: Yahoo Finance. Numbers can lag or be incomplete.")
    return f"Hidden gems: top {min(len(results), C.GEMS_TOP_N)} this week", "\n".join(lines)
