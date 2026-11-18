# hyperliquid-logger

> **Run instructions (Slovenian): [NAVODILA.md](NAVODILA.md)** - start with `python app.py` or `start.cmd`, self-check with
> `python app.py --check` or `check.cmd`, errors and what to do about them. `--verbose` prints every event to the console.
> The Debug panel's "log file" link (`/api/log`) shows the tail of the log, also from before a restart.

## Local app: collector + dashboard

```
python app.py            # http://127.0.0.1:8765  (stop with Ctrl+C)
```

`config.json` sets the wallets and the collection interval (`interval_seconds`, default 300 = 5 min,
minimum 5). It is re-read before every round, so interval and wallets change without a restart
(`db` and `port` need one). The collector takes one snapshot per wallet per round and the dashboard
shows it over time: account cards, equity / position value / uPnL charts, the positions table
(size like `-12,256.0897 ETH`, change since the previous round) and, per position, size, value, uPnL
and mark/entry price history. Time range 1 h ... all; the page refreshes every 30 s.
A round is written in one transaction, so the dashboard never shows half a round.

**Wallets:** the **Wallets** button opens a panel to add a wallet (address, optional label, "collect fills") or remove one
(two clicks). It edits `config.json` (so editing the file by hand still works) and the collector starts a new round at
once. Removing keeps the stored history. A wallet with no activity at all gets a warning ("is the address right?").
Because the server writes the file, `POST /api/wallets` accepts only requests from the dashboard page itself
(Host/Origin check). The **Range** selector sets the period of the charts only, not the trend columns.

**Trends per position:** the positions table has **15 min / 2 h / 1 day** columns showing how the position changed
since the round that long ago. The selector above the table picks the metric: size (default), position value or uPnL.
A cell shows the change and its percentage (green/red by sign; "new" = opened within the window; the tooltip has
`then -> now` and the age of the reference round). A dash means not enough history yet (the 1-day column fills after a
day of collecting) or a collection gap longer than 1.5 x the window.

**Debug / logs** (`log_dir`, `log_level` in config.json): the **Debug** button on the dashboard opens a live
event tail (round start/end with duration, per-wallet snapshot, every position change `ETH size -12,255.5 -> -12,256.1`,
errors; tick "HTTP calls" to also see every Hyperliquid request with its latency). The same events go to the console and
to `logs/hyperliquid-logger.log` (rotating, 2 MB x 5; set `log_level` to `INFO` to leave out the HTTP lines).
Saving config.json starts a new round immediately, so a new `interval_seconds` applies at once.
Tests: `python -m unittest`.

## CLI logger only (no dashboard)

Logs a Hyperliquid wallet over time into SQLite: the same data Hyperbot shows at
`hyperbot.network/trader/<address>`, taken straight from the public API
(`https://api.hyperliquid.xyz/info`, no key). Python 3.9+, standard library only.

```
python logger.py 0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00 --db hl.sqlite --interval 60
python logger.py <addr1> <addr2> --no-fills        # several wallets, skip fills
python logger.py <addr> --once                      # single snapshot
python -m unittest                                  # tests (no network)
```

| Table | Content | Key |
|---|---|---|
| `account_snapshot` | equity, total position value, margin, withdrawable, leverage, uPnL, long/short value, number of open orders; one row per perp dex | address, dex, ts_ms |
| `position_snapshot` | per position: size (`szi`, negative = short), entry, mark, position value, uPnL, ROE, liq. price, margin, leverage, funding | address, ts_ms, coin |
| `spot_snapshot` | spot balances (total, hold, entry notional) | address, ts_ms, coin |
| `fill` | executions (`userFillsByTime`, resumes after the newest stored fill, deduplicated by `tid`) | address, tid |

Notes:
- **Perp dexes:** `xyz:*` coins (stocks, commodities) live on the HIP-3 dex `xyz`, not the main dex.
  The logger queries every dex from `perpDexs`; without this Wintermute shows 86 positions instead of the page's 133.
- Account equity on the page = perp (all dexes) + spot. Spot is stored as coin balances (not USD-valued).
- Fills start from "now" on the first run; use `--backfill-hours N` for history. Skip them for busy market makers with `--no-fills`.
- Hyperliquid reports numbers as strings; they are stored as REAL.
