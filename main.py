#!/usr/bin/env python3
"""Offline BTC/USDC 240-minute-ahead forecaster for make.fun btc-cent-forecast-01.

Reads every ``<id>.in`` case from ``$MAKEFUN_INPUT_DIR`` (default ``/input/``) and
writes ``<id>.out`` to ``$MAKEFUN_OUTPUT_DIR`` (default ``/output/``).  Standard
library only, no network, deterministic: two runs on one case write identical bytes.

v1 model (starting point from the brief):
    forecast = 0.7 * EWMA(prices, halflife=80) + 0.3 * median(last 5 closes)
EWMA is the exponentially weighted mean of the one-minute closes with a half-life
of 80 minutes, normalised by the sum of the weights and using every close the case
holds (no bias correction at the start).
"""

import json
import os
import statistics

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

MIN_PRICE = 0.00001
MAX_PRICE = 9999999.99999
HALFLIFE = 80.0


def ewma(prices, halflife):
    """Exponentially weighted mean of ``prices`` with the given half-life.

    Weight of the close ``k`` minutes before the checkpoint is ``(1-alpha)**k``
    with ``alpha = 1 - 0.5**(1/halflife)``; the result is normalised by the sum of
    the weights actually used, so it stays unbiased on short histories too.
    """
    if not prices:
        raise ValueError("empty price series")
    alpha = 1.0 - 0.5 ** (1.0 / halflife)
    decay = 1.0 - alpha
    num = 0.0
    den = 0.0
    w = 1.0
    for p in reversed(prices):
        num += p * w
        den += w
        w *= decay
    return num / den


def forecast(prices):
    """The 240-minute-ahead guess from one minute-close series."""
    if not prices:
        raise ValueError("empty price series")
    level = ewma(prices, HALFLIFE)
    short = statistics.median(prices[-5:]) if len(prices) >= 1 else prices[-1]
    return 0.7 * level + 0.3 * short


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