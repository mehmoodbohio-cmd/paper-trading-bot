"""
Data layer: everything the bot knows about the market comes through here.
Uses Yahoo Finance (free) via the yfinance library.
Every call is wrapped so one broken ticker never crashes the bot.
"""

import datetime as dt
import time

import pandas as pd


def _split_batch(df, tickers):
    """yf.download returns one wide table; split it into one table per ticker."""
    out = {}
    if df is None or df.empty:
        return out
    if isinstance(df.columns, pd.MultiIndex):
        level0 = set(df.columns.get_level_values(0))
        for t in tickers:
            if t in level0:
                sub = df[t].dropna(how="all")
                if not sub.empty and "Close" in sub:
                    out[t] = sub
    elif len(tickers) == 1:
        out[tickers[0]] = df.dropna(how="all")
    return out


class YahooData:
    def __init__(self):
        import yfinance as yf
        self.yf = yf

    def _download(self, tickers, period, interval):
        out = {}
        for i in range(0, len(tickers), 100):          # batches of 100
            chunk = tickers[i:i + 100]
            try:
                df = self.yf.download(chunk, period=period, interval=interval, group_by="ticker",
                                      auto_adjust=True, progress=False, threads=True)
                out.update(_split_batch(df, chunk))
            except Exception as e:
                print(f"[data] download failed for a batch: {e}")
        return out

    def daily(self, tickers, period="1y"):
        return self._download(list(tickers), period, "1d")

    def intraday(self, tickers):
        return self._download(list(tickers), "5d", "30m")

    def fx_eurusd(self):
        try:
            df = self.yf.download("EURUSD=X", period="5d", interval="1d", progress=False, auto_adjust=True)
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            return float(close.dropna().iloc[-1])
        except Exception:
            return 1.08   # fallback, roughly right

    def fundamentals(self, ticker):
        """Company health numbers. Missing values come back as None."""
        try:
            t = self.yf.Ticker(ticker)
            info = t.info or {}
        except Exception:
            return {}
        f = {k: info.get(k) for k in [
            "shortName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
            "pegRatio", "priceToSalesTrailing12Months", "revenueGrowth", "earningsGrowth",
            "profitMargins", "grossMargins", "operatingMargins", "freeCashflow", "totalCash",
            "totalDebt", "debtToEquity", "returnOnEquity", "recommendationMean",
            "numberOfAnalystOpinions", "targetMeanPrice", "currentPrice", "heldPercentInsiders",
            "shortPercentOfFloat", "longBusinessSummary"]}
        # Revenue trend: is growth speeding up quarter after quarter?
        try:
            q = t.quarterly_income_stmt
            if q is not None and "Total Revenue" in q.index:
                rev = q.loc["Total Revenue"].dropna().sort_index()
                f["quarterly_revenue"] = [float(x) for x in rev.values[-6:]]
        except Exception:
            pass
        # Insiders buying their own shares
        try:
            ip = t.insider_purchases
            if ip is not None and not ip.empty:
                row = ip[ip.iloc[:, 0].astype(str).str.contains("Net Shares Purchased", case=False)]
                if not row.empty:
                    f["insider_net_shares"] = float(row["Shares"].iloc[0])
        except Exception:
            pass
        # Analyst upgrades vs downgrades in the last 90 days
        try:
            ud = t.upgrades_downgrades
            if ud is not None and not ud.empty:
                recent = ud[ud.index >= pd.Timestamp.now(tz=ud.index.tz) - pd.Timedelta(days=90)]
                f["upgrades_90d"] = int((recent["Action"] == "up").sum())
                f["downgrades_90d"] = int((recent["Action"] == "down").sum())
        except Exception:
            pass
        return f

    def news(self, ticker):
        """Latest headlines as [{'title': str, 'time': unix_seconds}]."""
        try:
            raw = self.yf.Ticker(ticker).news or []
        except Exception:
            return []
        items = []
        for n in raw:
            c = n.get("content", n)                    # newer yfinance nests under 'content'
            title = c.get("title")
            ts = c.get("providerPublishTime") or c.get("pubDate") or c.get("displayTime")
            if isinstance(ts, str):
                try:
                    ts = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    ts = time.time()
            if title:
                items.append({"title": title, "time": float(ts or time.time())})
        return items

    def next_earnings(self, ticker):
        """Date of the next earnings report, or None."""
        try:
            cal = self.yf.Ticker(ticker).calendar
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if dates:
                d = dates[0]
                return d if isinstance(d, dt.date) else None
        except Exception:
            pass
        return None
