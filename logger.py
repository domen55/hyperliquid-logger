#!/usr/bin/env python3
"""Log a Hyperliquid wallet (account, perp positions, spot balances, fills) to SQLite.

Uses only the public Hyperliquid info API (https://api.hyperliquid.xyz/info) and the
Python standard library. Same data Hyperbot shows on /trader/<address>.

    python logger.py 0xecb6...2b00 0x3ff5...f705 --db hl.sqlite --interval 60
    python logger.py 0xecb6...2b00 --once            # single snapshot, then exit
"""
import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.request

API = "https://api.hyperliquid.xyz/info"

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_snapshot (
    ts_ms INTEGER NOT NULL,            -- time reported by Hyperliquid
    address TEXT NOT NULL,
    dex TEXT NOT NULL,                 -- '' = main perp dex, 'xyz' = HIP-3 dex (xyz:* coins) ...
    account_value REAL,                -- perp equity (marginSummary.accountValue)
    total_ntl_pos REAL,                -- total position value
    total_margin_used REAL,
    withdrawable REAL,
    leverage REAL,                     -- total_ntl_pos / account_value
    n_positions INTEGER,
    n_open_orders INTEGER,
    long_value REAL,
    short_value REAL,
    upnl REAL,
    round_ms INTEGER,                  -- start of the collection round (same for all rows of one round)
    PRIMARY KEY (address, dex, ts_ms)
);
CREATE TABLE IF NOT EXISTS position_snapshot (
    ts_ms INTEGER NOT NULL,
    address TEXT NOT NULL,
    coin TEXT NOT NULL,
    szi REAL,                          -- signed size, negative = short
    side TEXT,
    entry_px REAL,
    mark_px REAL,                      -- position_value / |szi|
    position_value REAL,
    upnl REAL,
    roe REAL,
    liq_px REAL,
    margin_used REAL,
    leverage REAL,
    leverage_type TEXT,
    cum_funding_all_time REAL,
    cum_funding_since_open REAL,
    round_ms INTEGER,
    PRIMARY KEY (address, ts_ms, coin)
);
CREATE TABLE IF NOT EXISTS spot_snapshot (
    ts_ms INTEGER NOT NULL,
    address TEXT NOT NULL,
    coin TEXT NOT NULL,
    total REAL,
    hold REAL,
    entry_ntl REAL,
    round_ms INTEGER,
    PRIMARY KEY (address, ts_ms, coin)
);
CREATE INDEX IF NOT EXISTS acc_round ON account_snapshot (address, round_ms);
CREATE INDEX IF NOT EXISTS pos_round ON position_snapshot (address, coin, round_ms);
CREATE INDEX IF NOT EXISTS pos_round_ms ON position_snapshot (address, round_ms);  -- one whole round
CREATE INDEX IF NOT EXISTS spot_round_ms ON spot_snapshot (address, round_ms);
CREATE TABLE IF NOT EXISTS fill (
    address TEXT NOT NULL,
    tid INTEGER NOT NULL,
    oid INTEGER,
    time_ms INTEGER NOT NULL,
    coin TEXT,
    side TEXT,
    dir TEXT,
    px REAL,
    sz REAL,
    start_position REAL,
    closed_pnl REAL,
    fee REAL,
    fee_token TEXT,
    crossed INTEGER,
    hash TEXT,
    PRIMARY KEY (address, tid)
);
CREATE INDEX IF NOT EXISTS fill_time ON fill (address, time_ms);
"""


def f(x, default=None):
    """Hyperliquid sends numbers as strings; None-safe float conversion."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


HOOK = None  # optional callable(dict): diagnostics for every API call (used by the dashboard's debug log)


def _hook(**event):
    if HOOK:
        try:
            HOOK(event)
        except Exception:  # diagnostics must never break collection
            pass


def post(body, retries=5):
    data = json.dumps(body).encode()
    delay = 1.0
    info = {"type": body.get("type"), "dex": body.get("dex")}
    for attempt in range(retries):
        t0 = time.time()
        req = urllib.request.Request(API, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            out = json.loads(raw)
            _hook(kind="http", ms=round((time.time() - t0) * 1000), bytes=len(raw), attempt=attempt + 1, **info)
            return out
        except urllib.error.HTTPError as e:
            _hook(kind="http_error", error=f"HTTP {e.code}", ms=round((time.time() - t0) * 1000),
                  attempt=attempt + 1, **info)
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
        except (OSError, ValueError) as e:  # URLError, timeouts, resets, bad JSON
            _hook(kind="http_error", error=repr(e), ms=round((time.time() - t0) * 1000),
                  attempt=attempt + 1, **info)
            if attempt == retries - 1:
                raise
        time.sleep(delay)
        delay *= 2


def connect(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")  # dashboard reads while the collector writes
    db.executescript(SCHEMA)
    return db


def list_dexs(post=post):
    """Names of all perp dexes: '' (main) plus HIP-3 builder dexes (xyz, flx, ...)."""
    return [""] + [d["name"] for d in post({"type": "perpDexs"}) if d]


def snapshot(db, address, post=post, dexs=None, round_ms=None):
    """Store account + positions (every perp dex) + spot as ONE transaction, so a reader
    (the dashboard) never sees half a round. Returns (ts_ms, n_positions)."""
    dexs = list_dexs(post) if dexs is None else dexs
    round_ms = round_ms or int(time.time() * 1000)
    parts = [_fetch_dex(address, dex, post, round_ms) for dex in dexs]  # network first, no DB writes
    spot = post({"type": "spotClearinghouseState", "user": address})
    ts0 = parts[0][0]
    with db:
        for ts, acc, rows in parts:
            if acc:
                db.execute("INSERT OR IGNORE INTO account_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", acc)
            db.executemany(
                "INSERT OR IGNORE INTO position_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.executemany(
            "INSERT OR IGNORE INTO spot_snapshot VALUES (?,?,?,?,?,?,?)",
            [(ts0, address, b["coin"], f(b["total"]), f(b["hold"]), f(b.get("entryNtl")), round_ms)
             for b in spot.get("balances", [])],
        )
    return ts0, sum(len(rows) for _, _, rows in parts)


def _fetch_dex(address, dex, post, round_ms):
    """-> (ts_ms, account_row or None for an empty dex, [position rows])"""
    cs = post({"type": "clearinghouseState", "user": address, "dex": dex})
    n_orders = len(post({"type": "openOrders", "user": address, "dex": dex}))
    ts = int(cs["time"])
    ms = cs["marginSummary"]
    rows, long_v, short_v, upnl = [], 0.0, 0.0, 0.0
    for ap in cs["assetPositions"]:
        p = ap["position"]
        szi, pv = f(p["szi"], 0.0), f(p["positionValue"], 0.0)
        if szi > 0:
            long_v += pv
        else:
            short_v += pv
        upnl += f(p["unrealizedPnl"], 0.0)
        lev = p.get("leverage") or {}
        cf = p.get("cumFunding") or {}
        rows.append((
            ts, address, p["coin"], szi, "long" if szi > 0 else "short", f(p["entryPx"]),
            (pv / abs(szi)) if szi else None, pv, f(p["unrealizedPnl"]), f(p["returnOnEquity"]),
            f(p["liquidationPx"]), f(p["marginUsed"]), lev.get("value"), lev.get("type"),
            f(cf.get("allTime")), f(cf.get("sinceOpen")), round_ms,
        ))
    av, ntl = f(ms["accountValue"], 0.0), f(ms["totalNtlPos"], 0.0)
    if not rows and not av and not n_orders and dex != "":
        return ts, None, rows  # empty dex: nothing worth storing
    acc = (ts, address, dex, av, ntl, f(ms["totalMarginUsed"]), f(cs["withdrawable"]),
           (ntl / av) if av else None, len(rows), n_orders, long_v, short_v, upnl, round_ms)
    return ts, acc, rows


def pull_fills(db, address, backfill_ms=0, max_pages=10, post=post):
    """Fetch new fills since the newest stored one (userFillsByTime, 2000 per page)."""
    last = db.execute("SELECT MAX(time_ms) FROM fill WHERE address=?", (address,)).fetchone()[0]
    start = (last + 1) if last else int(time.time() * 1000) - backfill_ms
    total = 0
    for _ in range(max_pages):
        page = post({"type": "userFillsByTime", "user": address, "startTime": start})
        if not page:
            break
        with db:
            db.executemany(
                "INSERT OR IGNORE INTO fill VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(address, x["tid"], x.get("oid"), x["time"], x["coin"], x["side"], x.get("dir"),
                  f(x["px"]), f(x["sz"]), f(x.get("startPosition")), f(x.get("closedPnl")),
                  f(x.get("fee")), x.get("feeToken"), int(bool(x.get("crossed"))), x.get("hash"))
                 for x in page],
            )
        total += len(page)
        newest = max(x["time"] for x in page)
        if len(page) < 2000:
            break
        start = newest + 1
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("addresses", nargs="+", help="wallet addresses (0x...)")
    ap.add_argument("--db", default="hyperliquid.sqlite")
    ap.add_argument("--interval", type=float, default=60, help="seconds between snapshots")
    ap.add_argument("--once", action="store_true", help="one snapshot and exit")
    ap.add_argument("--no-fills", action="store_true", help="skip fills (busy market makers)")
    ap.add_argument("--backfill-hours", type=float, default=0, help="fills history on first run")
    a = ap.parse_args()

    db = connect(a.db)
    addrs = [x.lower() for x in a.addresses]
    while True:
        started = time.time()
        for ad in addrs:
            try:
                ts, n = snapshot(db, ad)
                msg = f"{time.strftime('%H:%M:%S')} {ad[:8]} snapshot ts={ts} positions={n}"
                if not a.no_fills:
                    msg += f" new_fills={pull_fills(db, ad, int(a.backfill_hours * 3600_000))}"
                print(msg, flush=True)
            except Exception as e:  # keep the loop alive on network errors
                print(f"{time.strftime('%H:%M:%S')} {ad[:8]} ERROR {e!r}", flush=True)
        if a.once:
            break
        time.sleep(max(0.0, a.interval - (time.time() - started)))


if __name__ == "__main__":
    main()
