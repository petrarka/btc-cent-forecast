#!/usr/bin/env python3
"""Local practice harness for the BTC/USDC forecaster (no network, stdlib only).

Two jobs:

1. Contract check -- every ``<id>.out`` in the output directory must be a regular
   UTF-8 JSON file of at most 1 MiB with exactly one key ``forecasts`` holding one
   row ``{"case": <id>, "price": <finite 0 < p < 1e7>}``.

2. Backtest without the sealed answers.  For every case we cut the last 240 minutes
   of history, treat the close 240 minutes before the end as an inner checkpoint,
   predict 240 minutes ahead and compare the absolute error against persistence
   (the inner checkpoint's own close).  We also rebuild the continuous price series
   the practice windows are cut from and run a dense sliding backtest (every minute
   that has 4320 minutes of history behind it and a known close 240 minutes ahead),
   which is a far larger and more reliable sample than the six case endpoints.

Usage:
    python3 check.py [INPUT_DIR] [OUTPUT_DIR]

Defaults: INPUT_DIR from $MAKEFUN_INPUT_DIR or the kit's input/, OUTPUT_DIR from
$MAKEFUN_OUTPUT_DIR or ./out.
"""

import json
import math
import os
import sys

from main import forecast, clean_price

KIT_INPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "makefun-kit-btc", "btc-cent-forecast-01-kit", "input",
)


def resolve_dirs(argv):
    in_dir = argv[1] if len(argv) > 1 else os.environ.get("MAKEFUN_INPUT_DIR")
    out_dir = argv[2] if len(argv) > 2 else os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not in_dir:
        for cand in (KIT_INPUT, "input", "/input"):
            if os.path.isdir(cand):
                in_dir = cand
                break
    if not out_dir:
        out_dir = "out"
    return in_dir, out_dir


def load_cases(in_dir):
    cases = []
    for name in sorted(os.listdir(in_dir)):
        if not name.endswith(".in"):
            continue
        with open(os.path.join(in_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        cases.append((name[:-3], case))
    return cases


def check_contract(out_dir, cases):
    """Return a list of problems with the produced output files (empty == valid)."""
    problems = []
    for case_id, _ in cases:
        path = os.path.join(out_dir, case_id + ".out")
        if not os.path.isfile(path):
            problems.append("%s: missing output" % case_id)
            continue
        size = os.path.getsize(path)
        if size > 1_048_576:
            problems.append("%s: output too large (%d bytes)" % (case_id, size))
            continue
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        try:
            obj = json.loads(raw)
        except ValueError as exc:
            problems.append("%s: not JSON (%s)" % (case_id, exc))
            continue
        if not isinstance(obj, dict) or set(obj.keys()) != {"forecasts"}:
            problems.append("%s: top level must be exactly {'forecasts': ...}" % case_id)
            continue
        rows = obj["forecasts"]
        if not isinstance(rows, list) or len(rows) != 1:
            problems.append("%s: forecasts must be a one-row list" % case_id)
            continue
        row = rows[0]
        if not isinstance(row, dict) or set(row.keys()) != {"case", "price"}:
            problems.append("%s: row must be exactly {'case','price'}" % case_id)
            continue
        if row["case"] != case_id:
            problems.append("%s: row names %r" % (case_id, row["case"]))
        price = row["price"]
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            problems.append("%s: price is not a number" % case_id)
        elif not math.isfinite(price) or not (0 < price < 10_000_000):
            problems.append("%s: price %r out of bounds" % (case_id, price))
    return problems


def pseudo_backtest(cases):
    """Per-case: cut the last 240 minutes, predict the final close, compare to persistence."""
    rows = []
    for case_id, case in cases:
        prices = case["markets"][0]["prices"]
        if len(prices) <= 240:
            continue
        history = prices[:-240]
        inner = prices[-241]          # last close available at the inner checkpoint
        actual = prices[-1]           # the close 240 minutes later
        guess = clean_price(forecast(history))
        rows.append(
            {
                "case": case_id,
                "inner": inner,
                "actual": actual,
                "model": guess,
                "model_err": abs(guess - actual),
                "pers_err": abs(inner - actual),
            }
        )
    return rows


def reconstruct(cases):
    """Stitch the practice windows into one continuous series if they line up.

    Consecutive cases are 240 minutes apart and hold 4320 closes, so case k's last
    4080 closes equal case k+1's first 4080.  Returns (series, checkpoint_indices)
    or (None, None) if the windows do not line up.
    """
    if len(cases) < 2:
        return None, None
    series = list(cases[0][1]["markets"][0]["prices"])
    for _, case in cases[1:]:
        prices = case["markets"][0]["prices"]
        # each window overlaps the previous one in all but its last 240 closes
        overlap = len(prices) - 240
        if prices[:overlap] != series[-overlap:]:
            return None, None
        series.extend(prices[overlap:])
    # checkpoints are the last close of each case window
    checkpoints = []
    pos = 0
    for _, case in cases:
        n = len(case["markets"][0]["prices"])
        pos += n if not checkpoints else 240
        checkpoints.append(pos - 1)
    return series, checkpoints


def dense_backtest(series, checkpoint_indices, history=4320, horizon=240):
    """MAE of the model vs persistence over every minute with full history and a known target."""
    model_err = []
    pers_err = []
    n = len(series)
    for i in range(history - 1, n - horizon):
        window = series[i - history + 1: i + 1]
        actual = series[i + horizon]
        guess = clean_price(forecast(window))
        model_err.append(abs(guess - actual))
        pers_err.append(abs(series[i] - actual))
    return model_err, pers_err


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    in_dir, out_dir = resolve_dirs(sys.argv)
    cases = load_cases(in_dir)
    if not cases:
        print("no *.in cases found in %s" % in_dir)
        return 1

    print("== contract check (%d cases) ==" % len(cases))
    problems = check_contract(out_dir, cases)
    if problems:
        for p in problems:
            print("  FAIL", p)
    else:
        print("  OK: all %d outputs valid" % len(cases))

    print("\n== pseudo-checkpoint backtest (cut last 240 min per case) ==")
    rows = pseudo_backtest(cases)
    print("  %-6s %12s %12s %12s %12s" % ("case", "inner", "actual", "model_err", "pers_err"))
    for r in rows:
        print(
            "  %-6s %12.2f %12.2f %12.2f %12.2f"
            % (r["case"], r["inner"], r["actual"], r["model_err"], r["pers_err"])
        )
    if rows:
        mm = mean([r["model_err"] for r in rows])
        pm = mean([r["pers_err"] for r in rows])
        print("  mean MAE  model $%.2f  persistence $%.2f  (%+.1f%%)"
              % (mm, pm, (mm - pm) / pm * 100.0))

    print("\n== dense sliding backtest (reconstructed continuous series) ==")
    series, checkpoints = reconstruct(cases)
    if series is None:
        print("  skipped: practice windows do not line up")
    else:
        model_err, pers_err = dense_backtest(series, checkpoints)
        mm = mean(model_err)
        pm = mean(pers_err)
        print("  series length %d, %d checkpoints" % (len(series), len(model_err)))
        print("  mean MAE  model $%.2f  persistence $%.2f  (%+.1f%%)"
              % (mm, pm, (mm - pm) / pm * 100.0))
        print("  (note: consecutive targets overlap, so treat the gap as indicative, not exact)")

    return 0


if __name__ == "__main__":
    sys.exit(main())