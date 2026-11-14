# btc-cent-forecast

Offline BTC/USDC price forecaster for the make.fun competition
`btc-cent-forecast-01`. Given 4,320 one-minute closes up to a checkpoint (72 hours of
price), it guesses the close 240 minutes (4 hours) later.

Python 3, standard library only, no network, deterministic.

## Model

```
forecast = last + BETA * (mean(last 240 closes) - last)
         = 0.85 * last + 0.15 * mean(last 240 closes)      (BETA = 0.15)
```

`last` is the checkpoint close. The guess is mostly **persistence** (the martingale
answer for a random walk) with a small pull toward the recent **4-hour mean**.

Why this shape, from the practice recording:

- A variance-ratio (Lo–MacKinlay) test puts the 1-minute return variance ratio at
  ~1.0 for lags up to ~30 minutes but **0.54 at 240 min** and **0.38 at 480 min**:
  the series is essentially a random walk minute to minute but **mean-reverts on a
  multi-hour scale**. So a small multi-hour mean-reversion tilt, not a short EWMA,
  is the right correction.
- The original brief's `0.7*EWMA(halflife=80) + 0.3*median(5)` (v1) was both too
  short (it chases minute noise) and weighted too heavily; it fought genuine trends
  and scored **8% worse** than persistence on the pseudo-checkpoints.

The weight is deliberately light: the edge is real but modest and regime-dependent,
and a strong trend can overwhelm it, so persistence dominates the forecast.

## Run

```sh
# forecast the practice cases into ./out
mkdir -p out
MAKEFUN_INPUT_DIR=../makefun-kit-btc/btc-cent-forecast-01-kit/input \
MAKEFUN_OUTPUT_DIR=out python3 main.py
```

With the environment unset it reads `/input/` and writes `/output/`, as the grader
does. It processes every `*.in` in the input directory (name order) and writes one
`<id>.out` per case: `{"forecasts":[{"case":"<id>","price":<number>}]}`.

### Local practice check (no sealed answers)

```sh
python3 check.py [INPUT_DIR] [OUTPUT_DIR]
```

`check.py` validates every output against the contract and backtests against
persistence two ways: the six pseudo-checkpoints (cut the last 240 minutes off each
case) and a dense sliding backtest on the continuous 72-hour series the practice
windows are cut from (961 checkpoints with full history and a known target).

## Results vs persistence (MAE, dollars)

| Backtest | persistence | this model | gap |
|---|---|---|---|
| dense 961-checkpoint backtest | 525.51 | **514.50** | **-2.1%** |
| six pseudo-checkpoints | 434.14 | 437.27 | +0.7% |

The dense backtest is the reliable number (the 6 pseudo-checkpoints are a handful of
overlapping points and sit within noise of each other). The 240-minute move has a
standard deviation of ~$589, and the overlapping backtest has an effective sample of
only ~20 independent 240-minute blocks, so a ~2% gap is real in expectation but not
large; heavier smoothing looked better in-sample yet generalised worse, so it was
rejected.

## Iteration log

- **v1** — `0.7*EWMA(80) + 0.3*median(5)` from the brief. Dense +0.2%, pseudo +8.0%
  (worse than persistence).
- **v2** — replace the short EWMA with a 4-hour-mean tilt (`BETA=0.20`), motivated by
  the variance-ratio test. Dense **-2.5%**; pseudo +1.0%.
- **v3** — temper `BETA` to 0.15 for robustness: keeps most of the gain (dense
  **-2.1%**) with a smaller worst case in a strong trend and less pseudo regression.

## License

MIT (see `LICENSE`).