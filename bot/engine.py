"""
The trader. Every run (every 30 minutes) it:
  1. Does the big daily scan if it hasn't today          (net #1: ~370 assets)
  2. Checks the market mood (is everything crashing?)
  3. Checks each holding: stop-loss, trailing stop, bad news, trend break
  4. Looks for buys among the shortlist                  (net #2: ~15 assets)
  5. Emails you BEFORE each paper trade, with the reasons
  6. Grades old trades in the journal (was the bot right 24h later?)
  7. Sends the daily summary / weekly hidden gems report when due
All money is pretend. Nothing here connects to a broker.
"""

import datetime as dt
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from . import analysis as A
from . import config as C
from . import dashboard, notify, reports
from .news import score_news
from .universe import (MARKET_BENCHMARKS, all_crypto, all_stocks, asset_class, currency, pretty)

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
BERLIN = ZoneInfo("Europe/Berlin")
NEW_YORK = ZoneInfo("America/New_York")


# ================================================================ state
def _load(name, default):
    p = STATE_DIR / name
    return json.loads(p.read_text()) if p.exists() else default


def _save(name, obj):
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / name).write_text(json.dumps(obj, indent=1, default=str))


def new_portfolio(now):
    return dict(cash=C.STARTING_CASH_EUR, positions={}, started=now.isoformat(), day=None,
                day_start_value=C.STARTING_CASH_EUR, last_scan=None, last_summary=None,
                last_gems=None, recent_sells={}, history=[], fees_paid=0.0, benchmarks_start={})


# ================================================================ market hours
def market_open(ticker, now):
    cls = asset_class(ticker)
    if cls == "crypto":
        return True
    if cls == "eu_stock":
        t = now.astimezone(BERLIN)
        return t.weekday() < 5 and dt.time(9, 0) <= t.time() <= dt.time(17, 30)
    t = now.astimezone(NEW_YORK)
    return t.weekday() < 5 and dt.time(9, 30) <= t.time() <= dt.time(16, 0)


def to_eur(price, ticker, fx):
    return price / fx if currency(ticker) == "USD" else price


# ================================================================ daily scan (net #1)
def daily_scan(data, now, fund_cache):
    print("[scan] downloading 1 year of daily prices for the whole universe...")
    stocks, coins = all_stocks(), all_crypto()
    daily = data.daily(stocks + coins, period="1y")
    tech_s = A.technical_scores({t: d for t, d in daily.items() if t in stocks})
    tech_c = A.technical_scores({t: d for t, d in daily.items() if t in coins})
    print(f"[scan] scored {len(tech_s)} stocks and {len(tech_c)} coins on charts")

    # Fundamental deep dive on the best-looking stocks
    top = sorted(tech_s, key=lambda t: tech_s[t]["score"], reverse=True)[:C.FUNDAMENTAL_DEEP_DIVE]
    today = now.astimezone(BERLIN).date().isoformat()
    combined = {}
    for t in top:
        cached = fund_cache.get(t)
        if not cached or cached.get("_date") != today:
            f = data.fundamentals(t)
            f["_date"] = today
            fund_cache[t] = f
            time.sleep(0.2)                        # be polite to Yahoo
        fs, good, risks = A.fundamental_score(fund_cache[t])
        tech = tech_s[t]
        score = 0.6 * tech["score"] + 0.4 * fs if fs is not None else 0.95 * tech["score"]
        combined[t] = dict(score=score, tech=tech["score"], fund=fs, reasons=tech["reasons"],
                           good=good, risks=risks, vol=tech["vol"])
    for t, tech in tech_c.items():
        combined[t] = dict(score=tech["score"], tech=tech["score"], fund=None,
                           reasons=tech["reasons"], good=[], risks=[], vol=tech["vol"])

    best_s = sorted([t for t in combined if t in stocks], key=lambda t: combined[t]["score"], reverse=True)
    best_c = sorted([t for t in combined if t in coins], key=lambda t: combined[t]["score"], reverse=True)
    shortlist = best_s[:C.SHORTLIST_STOCKS] + best_c[:C.SHORTLIST_CRYPTO]
    scan = dict(date=today, shortlist=shortlist,
                scores={t: combined[t] for t in shortlist},
                all_scores={t: round(v["score"], 3) for t, v in combined.items()},
                tech_all={t: v for t, v in {**tech_s, **tech_c}.items()},
                counts=dict(stocks=len(tech_s), crypto=len(tech_c)))
    return scan


# ================================================================ the 30-minute run
def run(data, now=None, force_summary=False, force_gems=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    berlin = now.astimezone(BERLIN)
    today = berlin.date().isoformat()

    pf = _load("portfolio.json", None) or new_portfolio(now)
    journal = _load("journal.json", [])
    fund_cache = _load("fundamentals_cache.json", {})
    scan = _load("scan.json", {})
    fx = data.fx_eurusd()
    log = []

    # ---- 1. big daily scan
    if scan.get("date") != today:
        fresh = daily_scan(data, now, fund_cache)
        _save("fundamentals_cache.json", fund_cache)
        if fresh["counts"]["stocks"] + fresh["counts"]["crypto"] < 50:
            # Yahoo probably failed or rate-limited us: keep yesterday's list, retry next run
            print("[scan] too little data came back - will retry next run")
            if pf.get("data_alert") != today:
                notify.send("Data problem", f"The daily scan only got data for "
                            f"{fresh['counts']} assets. Keeping the previous shortlist and retrying "
                            "every 30 minutes. If this keeps happening, Yahoo may be blocking the server.",
                            when=berlin)
                pf["data_alert"] = today
            if not scan:
                _save("portfolio.json", pf)
                return dict(value=pf["cash"], trades=[], skipped=[], mood={}, log=["no data"])
        else:
            scan = fresh
            _save("scan.json", scan)
            log.append(f"Daily scan done: {len(scan['shortlist'])} on the shortlist")

    held = list(pf["positions"])
    watch = list(dict.fromkeys(scan["shortlist"] + held))
    bench = list(dict.fromkeys(MARKET_BENCHMARKS.values()))
    daily = data.daily(watch + bench, period="6mo")
    intra = data.intraday(watch)

    def price_now(t):
        if t in intra and len(intra[t]):
            return float(intra[t]["Close"].dropna().iloc[-1])
        if t in daily and len(daily[t]):
            return float(daily[t]["Close"].dropna().iloc[-1])
        return None

    def value():
        v = pf["cash"]
        for t, p in pf["positions"].items():
            px = price_now(t) or p["last_price"]
            v += p["units"] * to_eur(px, t, fx)
        return v

    # ---- new day bookkeeping
    if pf["day"] != today:
        pf["day"], pf["day_start_value"] = today, value()
        pf["trades_today"] = 0
    if not pf["benchmarks_start"]:
        for name, t in MARKET_BENCHMARKS.items():
            if t in daily:
                pf["benchmarks_start"][t] = float(daily[t]["Close"].dropna().iloc[-1])

    # ---- 2. market mood
    mood = {}
    for name, t in MARKET_BENCHMARKS.items():
        d = daily.get(t)
        if d is None or len(d) < 50:
            mood[name] = ("unknown", "no data")
            continue
        c = d["Close"].dropna()
        ma50, chg = c.rolling(50).mean().iloc[-1], c.iloc[-1] / c.iloc[-2] - 1
        if c.iloc[-1] < ma50 and chg < -0.01:
            mood[name] = ("risk-off", f"{pretty(t)} below 50-day average and down {chg:+.1%} today")
        elif chg < -0.025:
            mood[name] = ("risk-off", f"{pretty(t)} dropping hard today ({chg:+.1%})")
        elif c.iloc[-1] < ma50:
            mood[name] = ("cautious", f"{pretty(t)} below its 50-day average")
        else:
            mood[name] = ("ok", f"{pretty(t)} healthy ({chg:+.1%} today)")
    mood_key = {"us_stock": "stocks", "eu_stock": "eu_stocks", "crypto": "crypto"}

    news_cache = {}

    def news_for(t):
        if t not in news_cache:
            news_cache[t] = score_news(data.news(t), now=now.timestamp())
        return news_cache[t]

    trades_made = []

    def execute(side, t, units, px, reasons, confidence=None):
        px_eur = to_eur(px, t, fx)
        gross = units * px_eur
        fee = gross * C.FEE_PCT
        p = pf["positions"].get(t)
        pnl_line = ""
        if side == "SELL" and p:
            pnl = gross - fee - p["cost_eur"]
            pnl_line = f"\nResult: {pnl:+.2f} EUR ({pnl / p['cost_eur']:+.1%}) after fees"
        body = (f"PAPER TRADE ALERT (pretend money)\n\n"
                f"Action:  {side} {pretty(t)} ({t})\n"
                f"Amount:  {units:.6g} units at {px:,.4g} {currency(t)}  =  {gross:.2f} EUR\n"
                f"Fee:     {fee:.2f} EUR"
                + (f"\nConfidence: {confidence:.0%}" if confidence is not None else "")
                + pnl_line + "\n\nWhy:\n" + "\n".join(f"  - {r}" for r in reasons)
                + f"\n\nCash after trade: {pf['cash'] + (gross - fee if side == 'SELL' else -(gross + fee)):.2f} EUR")
        notify.send(f"{side} {pretty(t)} {gross:.2f} EUR", body, when=berlin)   # email first...
        if side == "BUY":                                                        # ...then execute
            pf["cash"] -= gross + fee
            pf["positions"][t] = dict(units=units, entry_price=px, cost_eur=gross + fee, peak=px,
                                      last_price=px, opened=now.isoformat(), reasons=reasons)
        else:
            pf["cash"] += gross - fee
            pf["positions"].pop(t, None)
            pf["recent_sells"][t] = now.isoformat()
        pf["fees_paid"] += fee
        pf["trades_today"] = pf.get("trades_today", 0) + 1
        journal.append(dict(id=len(journal) + 1, time=now.isoformat(), ticker=t, side=side, price=px,
                            eur=round(gross, 2), fee=round(fee, 3), confidence=confidence,
                            reasons=reasons, check=None))
        trades_made.append((side, t, gross, reasons))

    # ---- 3. check holdings (sell rules)
    for t in list(pf["positions"]):
        p = pf["positions"][t]
        px = price_now(t)
        if px is None:
            continue
        p["last_price"] = px
        p["peak"] = max(p["peak"], px)
        if not market_open(t, now):
            continue
        cls = asset_class(t)
        chg = px / p["entry_price"] - 1
        drop_from_peak = px / p["peak"] - 1
        reasons = []
        if chg <= -C.STOP_LOSS[cls]:
            reasons.append(f"stop-loss: down {chg:.1%} from buy price (limit {C.STOP_LOSS[cls]:.0%})")
        elif drop_from_peak <= -C.TRAILING_STOP[cls] and p["peak"] > p["entry_price"]:
            reasons.append(f"trailing stop: fell {drop_from_peak:.1%} from its high, locking in profit")
        else:
            ns, headline = news_for(t)
            held_h = (now - dt.datetime.fromisoformat(p["opened"])).total_seconds() / 3600
            if ns <= C.BAD_NEWS_SELL:
                reasons.append(f"bad news (score {ns:+.2f}): {headline}")
            elif held_h < C.MIN_HOLD_HOURS:
                pass                                    # give the trade time to work
            else:
                isig, iwhy = A.intraday_signal(intra[t]) if t in intra else (0.5, "")
                d = daily.get(t)
                below_ma20 = d is not None and len(d) > 20 and px < d["Close"].rolling(20).mean().iloc[-1]
                if isig <= 0.1 and below_ma20:
                    reasons.append(f"trend broke: {iwhy}, and below its 20-day average")
                elif t not in scan["shortlist"] and scan["all_scores"].get(t, 0) < 0.35:
                    reasons.append(f"dropped out of today's scan (score {scan['all_scores'].get(t, 0):.2f})")
                elif mood[mood_key[cls]][0] == "risk-off" and chg < 0:
                    reasons.append(f"market mood risk-off ({mood[mood_key[cls]][1]}) and position losing")
        if reasons:
            execute("SELL", t, p["units"], px, reasons)

    # ---- 4. look for buys
    equity = value()
    day_pnl = equity / pf["day_start_value"] - 1
    buy_block = None
    if day_pnl <= -C.DAILY_LOSS_LIMIT:
        buy_block = f"daily loss limit hit ({day_pnl:.1%} today) - no new buys until tomorrow"

    candidates = []
    skipped = []
    if not buy_block:
        held_daily = {h: daily[h]["Close"].dropna() for h in pf["positions"] if h in daily}
        for t in scan["shortlist"]:
            if t in pf["positions"] or not market_open(t, now) or t not in intra:
                continue
            cls = asset_class(t)
            mk = mood[mood_key[cls]]
            if mk[0] == "risk-off":
                skipped.append(f"{pretty(t)}: market mood risk-off")
                continue
            last_sell = pf["recent_sells"].get(t)
            if last_sell and (now - dt.datetime.fromisoformat(last_sell)).total_seconds() < C.COOLDOWN_HOURS * 3600:
                continue
            if cls != "crypto":
                ed = data.next_earnings(t)
                if ed and 0 <= (ed - berlin.date()).days <= C.EARNINGS_BLACKOUT_DAYS:
                    skipped.append(f"{pretty(t)}: earnings report on {ed}")
                    continue
            twin = None
            if t in daily:
                for h, hc in held_daily.items():
                    rho = A.correlation(daily[t]["Close"].dropna(), hc)
                    if rho > C.MAX_CORRELATION:
                        twin = (h, rho)
                        break
            if twin:
                skipped.append(f"{pretty(t)}: moves like {pretty(twin[0])} which we hold (corr {twin[1]:.2f})")
                continue
            ns, headline = news_for(t)
            if ns < C.BAD_NEWS_NO_BUY:
                skipped.append(f"{pretty(t)}: negative news ({ns:+.2f})")
                continue
            isig, iwhy = A.intraday_signal(intra[t])
            s = scan["scores"][t]
            conf = 0.55 * s["score"] + 0.25 * isig + 0.20 * (ns + 1) / 2
            if mk[0] == "cautious":
                conf -= 0.05
            reasons = [f"daily scan score {s['score']:.2f} (charts {s['tech']:.2f}"
                       + (f", company health {s['fund']:.2f})" if s["fund"] is not None else ")")]
            reasons += s["reasons"][:3] + s["good"][:3] + [iwhy]
            reasons.append(headline if headline else f"news: nothing important ({ns:+.2f})")
            if s["risks"]:
                reasons.append("risks: " + "; ".join(s["risks"][:2]))
            reasons.append(f"market mood: {mk[1]}")
            if conf >= C.MIN_CONFIDENCE_TO_BUY:
                candidates.append((conf, t, reasons, s["vol"]))
            else:
                skipped.append(f"{pretty(t)}: confidence {conf:.0%} below {C.MIN_CONFIDENCE_TO_BUY:.0%}")

    for conf, t, reasons, vol in sorted(candidates, reverse=True):
        if len(pf["positions"]) >= C.MAX_POSITIONS:
            break
        # Size: bigger when more confident, smaller when the asset is wild
        conf_scale = 0.5 + 0.5 * min(1.0, (conf - C.MIN_CONFIDENCE_TO_BUY) / (1 - C.MIN_CONFIDENCE_TO_BUY))
        vol_scale = min(1.0, C.TARGET_DAILY_VOL / max(vol, 1e-4))
        size = equity * C.MAX_POSITION_PCT * conf_scale * vol_scale
        size = min(size, pf["cash"] / (1 + C.FEE_PCT))
        if size < C.MIN_TRADE_EUR:
            skipped.append(f"{pretty(t)}: position would be only {size:.2f} EUR")
            continue
        px = price_now(t)
        units = size / to_eur(px, t, fx)
        reasons = reasons + [f"size {size:.2f} EUR = {size / equity:.0%} of portfolio "
                             f"(confidence x{conf_scale:.2f}, volatility x{vol_scale:.2f})"]
        execute("BUY", t, units, px, reasons, confidence=conf)
        held_daily = {h: daily[h]["Close"].dropna() for h in pf["positions"] if h in daily}
        # re-check the "no twins" rule against what we just bought
        candidates = [c for c in candidates if c[1] not in held_daily]

    # ---- 6. grade old trades (trade journal)
    for j in journal:
        if j["check"] is None:
            age = (now - dt.datetime.fromisoformat(j["time"])).total_seconds()
            px = price_now(j["ticker"])
            if age >= 24 * 3600 and px:
                move = px / j["price"] - 1
                right = move > 0 if j["side"] == "BUY" else move < 0
                j["check"] = dict(time=now.isoformat(), price=px, move=move, right=bool(right))

    equity = value()
    bench_now = {}
    for name, t in MARKET_BENCHMARKS.items():
        start = pf["benchmarks_start"].get(t)
        if start and t in daily and len(daily[t]):
            bench_now[pretty(t)] = round(100 * float(daily[t]["Close"].dropna().iloc[-1]) / start, 2)
    pf["history"].append(dict(t=now.isoformat(), v=round(equity, 2), b=bench_now))
    pf["live_prices"] = {t: price_now(t) for t in pf["positions"]}
    pf["fx"] = fx
    pf["mood"] = {k: list(v) for k, v in mood.items()}
    pf["last_skipped"] = skipped[:15]

    # ---- 7. reports
    if force_summary or (berlin.hour >= C.DAILY_SUMMARY_HOUR and pf["last_summary"] != today):
        subject, body = reports.daily_summary(pf, journal, scan, daily, fx, now, price_now)
        notify.send(subject, body, when=berlin)
        pf["last_summary"] = today
    week = f"{berlin.isocalendar()[0]}-W{berlin.isocalendar()[1]}"
    if force_gems or (berlin.weekday() == C.GEMS_WEEKDAY and berlin.hour >= C.GEMS_HOUR
                      and pf["last_gems"] != week):
        subject, body = reports.hidden_gems(data, scan, fund_cache, now)
        notify.send(subject, body, when=berlin)
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports" / f"gems_{today}.md").write_text(body)
        _save("fundamentals_cache.json", fund_cache)
        pf["last_gems"] = week

    _save("portfolio.json", pf)
    _save("journal.json", journal)
    try:
        dashboard.build(pf, journal, scan, now, buy_block)
    except Exception as e:                        # the page must never stop the trading
        print(f"[dashboard] failed: {e}")
    print(f"[run {berlin:%a %d %b %H:%M}] value {equity:.2f} EUR | cash {pf['cash']:.2f} | "
          f"holding {', '.join(pretty(t) for t in pf['positions']) or 'nothing'} | "
          f"trades this run: {len(trades_made)}" + (f" | {buy_block}" if buy_block else ""))
    return dict(value=equity, trades=trades_made, skipped=skipped, mood=mood, log=log)
