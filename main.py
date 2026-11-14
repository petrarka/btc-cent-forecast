#!/usr/bin/env python3
"""Offline BTC/USDC 240-minute-ahead forecaster for make.fun btc-cent-forecast-01.

Reads every ``<id>.in`` case from ``$MAKEFUN_INPUT_DIR`` (default ``/input/``) and
writes ``<id>.out`` to ``$MAKEFUN_OUTPUT_DIR`` (default ``/output/``).  Standard
library only, no network, deterministic: two runs on one case write identical bytes.

v3 model -- light mean-reversion tilt toward the 4-hour mean, tempered weight:

    forecast = last + BETA * (mean(last 240 closes) - last)
             = (1 - BETA) * last + BETA * mean(last 240 closes)

Why this shape.  A variance-ratio (Lo-MacKinlay) test on the practice recording puts
the 1-minute return variance ratio at ~1.0 for lags up to ~30 min but at 0.54 for
240 min and 0.38 for 480 min: the series is essentially a random walk minute to
minute but mean-reverts on a multi-hour scale.  So the best point forecast is mostly
persistence (the martingale answer) with a small pull toward the recent 4-hour mean,
not toward a 1.3-hour EWMA.  v1's EWMA(halflife=80) was both too short (it chases
noise, not the multi-hour mean) and weighted too heavily (0.7), which made it fight
genuine trends and score 8% worse than persistence on the pseudo-checkpoints.

v2 used BETA=0.20, the in-sample optimum on the dense backtest (-2.5%).  v3 tempers
it to 0.15: the 4-hour mean reversion is real but the edge is modest and regime
dependent (a strong trend can overwhelm it), so a slightly lighter weight keeps most
of the gain (-2.1%) with a smaller worst case if the final window trends hard.
"""

import json
import os

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

MIN_PRICE = 0.00001
MAX_PRICE = 9999999.99999

# Weight on the 4-hour mean; the rest stays on the checkpoint close.
BETA = 0.15
# Window of closes averaged for the anchor (minutes); the reversion timescale.
ANCHOR = 240


def forecast(prices):
    """The 240-minute-ahead guess from one minute-close series."""
    if not prices:
        raise ValueError("empty price series")
    last = prices[-1]
    window = prices[-ANCHOR:] if len(prices) > ANCHOR else prices
    anchor = sum(window) / len(window)
    return last + BETA * (anchor - last)


def clean_price(x):
    """Clamp to the price grid and round to its 5 decimals."""
    if x < MIN_PRICE:
        x = MIN_PRICE
    elif x > MAX_PRICE:
        x = MAX_PRICE
    return round(x, 5)


def process(in_path, out_path, case_id):
    with open(in_path, "r", encoding="utf-8") as fh:
        case = json.load(fh)
    markets = case.get("markets")
    if not isinstance(markets, list) or len(markets) != 1:
        raise ValueError("%s does not hold exactly one market" % case_id)
    prices = markets[0].get("prices")
    if not isinstance(prices, list) or not prices:
        raise ValueError("market %s has no prices" % case_id)
    price = clean_price(forecast(prices))
    out = {"forecasts": [{"case": case_id, "price": price}]}
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out, separators=(",", ":")) + "\n")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for name in sorted(os.listdir(INPUT_DIR)):
        if not name.endswith(".in"):
            continue
        case_id = name[: -len(".in")]
        process(
            os.path.join(INPUT_DIR, name),
            os.path.join(OUTPUT_DIR, case_id + ".out"),
            case_id,
        )


if __name__ == "__main__":
    main()