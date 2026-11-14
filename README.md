# btc-cent-forecast

Offline BTC/USDC price forecaster for make.fun competition btc-cent-forecast-01.

`main.py` (Python 3, stdlib only, no network) reads each `*.in` case from
`$MAKEFUN_INPUT_DIR` (default `/input/`) — 4320 one-minute closes up to a
checkpoint — and writes `$MAKEFUN_OUTPUT_DIR/<id>.out` (default `/output/`) with
`{"forecasts":[{"case":"<id>","price":<guess 240 min ahead>}]}`. Deterministic,
well under the 8 s / 1 CPU / 1024 MB sandbox limit.

Model: exponential smoothing of minute closes blended with a short robust median
(see main.py header and check.py for the local practice harness).
MIT License.
