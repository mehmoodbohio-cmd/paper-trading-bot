"""
News reader: scores headlines as good / bad / neutral.

How it works (simple version, no AI needed):
  1. Trading phrases are checked first ("beats estimates", "guidance cut"...).
     They are worth more than single words because they carry clear meaning.
  2. Every remaining word is checked against the Loughran-McDonald finance
     dictionary (about 4,100 words built from thousands of company reports).
  3. "not", "no", "never"... flip the meaning of the next few words,
     so "not profitable" counts as bad.
  4. Fresh headlines count more than old ones (half the weight every 12 hours).
"""

import json
import math
import re
import time
from pathlib import Path

_WORDS = json.loads((Path(__file__).parent / "data" / "lm_words.json").read_text())
POSITIVE = set(_WORDS["positive"])
NEGATIVE = set(_WORDS["negative"])
UNCERTAIN = set(_WORDS["uncertainty"])
LITIGIOUS = set(_WORDS["litigious"])

# Phrase -> strength (-3 .. +3). Checked before single words.
PHRASES = {
    # strong good news
    "beats estimates": 3, "beat estimates": 3, "tops estimates": 3, "beats expectations": 3,
    "better than expected": 3, "record revenue": 3, "record profit": 3, "record earnings": 3,
    "raises guidance": 3, "raised guidance": 3, "raises outlook": 3, "boosts forecast": 3,
    "price target raised": 2, "raises price target": 2, "upgraded to buy": 3, "upgrade to buy": 3,
    "upgraded to outperform": 3, "initiated at buy": 2, "strong buy": 2,
    "share buyback": 2, "stock buyback": 2, "buyback program": 2, "dividend increase": 2,
    "raises dividend": 2, "special dividend": 2, "fda approval": 3, "wins contract": 2,
    "awarded contract": 2, "strategic partnership": 2, "expands partnership": 2,
    "insider buying": 2, "all-time high": 1, "record high": 1, "short squeeze": 1,
    "etf approval": 2, "mainnet launch": 1, "added to s&p": 2, "joins s&p 500": 2,
    "smaller than expected": 3, "narrower than expected": 3, "better than feared": 3,
    "less than feared": 2, "not as bad as": 2,
    "losses narrow": 2, "smaller loss": 2, "loss narrows": 2, "turns profitable": 3,
    "returns to profit": 3, "margin expansion": 2, "demand surge": 2, "sold out": 1,
    # strong bad news
    "misses estimates": -3, "missed estimates": -3, "misses expectations": -3,
    "worse than expected": -3, "cuts guidance": -3, "lowers guidance": -3, "cut guidance": -3,
    "lowers outlook": -3, "profit warning": -3, "price target cut": -2, "lowers price target": -2,
    "downgraded to sell": -3, "downgrade to sell": -3, "downgraded to underperform": -3,
    "downgraded to neutral": -1, "sec investigation": -3, "sec charges": -3, "class action": -2,
    "files for bankruptcy": -3, "chapter 11": -3, "going concern": -3, "delisting": -3,
    "accounting irregularities": -3, "ceo resigns": -2, "cfo resigns": -2, "recall": -2,
    "data breach": -2, "hack": -2, "exploit": -2, "rug pull": -3, "insider selling": -1,
    "dividend cut": -3, "suspends dividend": -3, "layoffs": -1, "job cuts": -1,
    "share offering": -2, "stock offering": -2, "dilution": -2, "secondary offering": -2,
    "short seller": -2, "short report": -2, "fraud": -3, "default": -2, "sanctions": -1,
    "margin pressure": -2, "demand slowdown": -2, "weak demand": -2, "tariffs": -1,
    "losses widen": -2, "wider loss": -2, "wider than expected": -3,
    "larger than expected loss": -3, "weaker than expected": -3, "lower than expected": -2,
    "higher than expected": 0,   # ambiguous (costs vs. sales) -> neutral, words decide
}

NEGATORS = {"not", "no", "never", "without", "fails", "failed", "lacks", "neither", "nor"}
NEGATION_WINDOW = 3          # how many words after "not" get flipped
HALF_LIFE_HOURS = 12         # older news counts less


def _tokens(text):
    return re.findall(r"[a-z][a-z'\-&]*", text.lower())


def score_headline(text):
    """Return (score between -1 and +1, list of reasons)."""
    t = text.lower()
    total, reasons = 0.0, []

    for phrase, w in PHRASES.items():
        if phrase in t:
            total += w
            reasons.append(f"'{phrase}' ({'+' if w > 0 else ''}{w})")
            t = t.replace(phrase, " ")       # don't double count its words

    words = _tokens(t)
    flip_left = 0
    for word in words:
        if word in NEGATORS:
            flip_left = NEGATION_WINDOW
            continue
        sign = -1 if flip_left > 0 else 1
        if word in POSITIVE:
            total += 1 * sign
            reasons.append(("not " if sign < 0 else "") + word)
        elif word in NEGATIVE:
            total += -1 * sign
            reasons.append(("not " if sign < 0 else "") + word)
        elif word in LITIGIOUS:
            total -= 0.5
        elif word in UNCERTAIN:
            total -= 0.25
        flip_left = max(0, flip_left - 1)

    score = math.tanh(total / 3)            # squash into -1..+1
    return score, reasons


def score_news(items, now=None):
    """items: list of dicts with 'title' and 'time' (unix seconds).
    Returns (weighted score -1..+1, best headline summary or None)."""
    now = now or time.time()
    num = den = 0.0
    strongest = None
    for it in items:
        title = it.get("title") or ""
        if not title:
            continue
        s, why = score_headline(title)
        age_h = max(0.0, (now - it.get("time", now)) / 3600)
        w = 0.5 ** (age_h / HALF_LIFE_HOURS)
        num += s * w
        den += w
        if strongest is None or abs(s) * w > abs(strongest[0]) * strongest[3]:
            strongest = (s, title, why, w)
    if den == 0:
        return 0.0, None
    summary = None
    if strongest and abs(strongest[0]) > 0.15:
        mood = "good" if strongest[0] > 0 else "bad"
        summary = f"{mood} news: \"{strongest[1]}\" ({', '.join(strongest[2][:4])})"
    return num / den, summary
