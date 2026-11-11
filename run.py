"""
Entry point.
  python run.py                 normal 30-minute run (what GitHub runs)
  python run.py --summary       also send the daily summary now
  python run.py --gems          also send the hidden gems report now
  python run.py --reset         start over with a fresh 100 EUR
"""

import argparse
import shutil

from bot.engine import STATE_DIR, run
from bot.data import YahooData

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--gems", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset and STATE_DIR.exists():
        shutil.rmtree(STATE_DIR)
        print("State wiped: starting fresh with 100 EUR.")
    run(YahooData(), force_summary=a.summary, force_gems=a.gems)
