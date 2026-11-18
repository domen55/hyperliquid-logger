#!/usr/bin/env python3
"""Local app: collector (every N seconds, configurable) + dashboard on http://127.0.0.1:<port>.

    python app.py                 # reads config.json next to this file
    python app.py --config my.json

config.json (re-read before every collection round, so interval/addresses can be changed
without a restart; db and port need a restart):
    {"addresses": [{"address": "0x...", "label": "Wintermute", "fills": false}],
     "interval_seconds": 300, "db": "hyperliquid.sqlite", "port": 8765,
     "log_dir": "logs", "log_level": "DEBUG"}

Events (rounds, snapshots, position changes, every API call, errors) go to the console, to
<log_dir>/hyperliquid-logger.log (rotating) and to the "Debug" drawer of the dashboard.
"""
import argparse
import collections
import itertools
import json
import logging
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
from logging.handlers import RotatingFileHandler
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import logger

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/chart.js": ("chart.umd.min.js", "application/javascript")}
MAX_POINTS = 3000
STATE = {"errors": {}, "last_round_ms": 0, "rounds": 0, "last_duration_ms": None,
         "next_round_ms": None, "started_ms": int(time.time() * 1000), "log_file": None}

# ---------------------------------------------------------------- events / logging
LOG = logging.getLogger("hl")
EVENTS = collections.deque(maxlen=3000)   # in-memory tail for the dashboard
_EV_LOCK = threading.Lock()
_EV_ID = itertools.count(1)


def emit(level, kind, msg, **data):
    """One event: ring buffer (dashboard) + logging (console / file)."""
    ev = {"id": next(_EV_ID), "ts": int(time.time() * 1000), "level": level, "kind": kind, "msg": msg, "data": data}
    with _EV_LOCK:
        EVENTS.append(ev)
    shown = {k: v for k, v in data.items() if k != "traceback"}  # the traceback stays in the event, not in one log line
    LOG.log(getattr(logging, level), "%-8s %s", kind, msg,
            extra={"kind": kind, "data_json": json.dumps(shown) if shown else ""})
    return ev


class LineFormatter(logging.Formatter):
    """`time LEVEL kind message`, plus the event's data as JSON for the log file (not for the console)."""

    def __init__(self, with_data):
        super().__init__("%(asctime)s %(levelname)-7s %(message)s")
        self.with_data = with_data

    def format(self, record):
        line = super().format(record)
        data = getattr(record, "data_json", "")
        return f"{line}  {data}" if self.with_data and data else line


def events_after(after_id, limit=500):
    with _EV_LOCK:
        out = [e for e in EVENTS if e["id"] > after_id]
    return out[-limit:]


def _on_http(e):
    """logger.HOOK: every Hyperliquid API call becomes an event."""
    if e["kind"] == "http":
        emit("DEBUG", "http", f"{e['type']} dex={e['dex'] or '-'} {e['ms']} ms {e['bytes']} B",
             type=e["type"], dex=e["dex"], ms=e["ms"], bytes=e["bytes"], attempt=e["attempt"])
    else:
        emit("WARNING", "http", f"{e['type']} dex={e['dex'] or '-'} FAILED {e['error']} (attempt {e['attempt']})",
             type=e["type"], dex=e["dex"], ms=e["ms"], error=e["error"], attempt=e["attempt"])


class ConsoleFilter(logging.Filter):
    """A calm console: position changes and HTTP calls only with --verbose (they stay in the log and Debug panel)."""
    QUIET_KINDS = ("position", "http")

    def __init__(self, verbose=False):
        super().__init__()
        self.verbose = verbose

    def filter(self, record):
        return (self.verbose or record.levelno >= logging.WARNING
                or getattr(record, "kind", "") not in self.QUIET_KINDS)


def explain_error(e):
    """A plain-language hint for the errors people actually meet, or None."""
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 429:
            return "rate limited by Hyperliquid (HTTP 429): raise interval_seconds or track fewer wallets; calls are retried"
        if e.code >= 500:
            return f"Hyperliquid server error (HTTP {e.code}): usually temporary, the next round tries again"
        return f"Hyperliquid answered HTTP {e.code}"
    if isinstance(e, sqlite3.OperationalError):
        text = str(e).lower()
        if "locked" in text:
            return "the database is locked: another program, or a second copy of this app, is using hyperliquid.sqlite"
        if "readonly" in text or "disk" in text or "unable to open" in text:
            return "cannot write to the database file: check folder permissions and free disk space"
        return None
    if isinstance(e, json.JSONDecodeError):
        return "unexpected answer from the API (not JSON): usually temporary"
    if isinstance(e, KeyError):
        return f"unexpected API response format (missing field {e})"
    if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout, socket.gaierror)):
        return "cannot reach api.hyperliquid.xyz: check the internet connection, VPN or firewall"
    return None


def setup_logging(cfg, verbose=False):
    log_dir = Path(cfg["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)
    LOG.handlers.clear()
    LOG.setLevel(logging.DEBUG)
    LOG.propagate = False
    fh = RotatingFileHandler(log_dir / "hyperliquid-logger.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(getattr(logging, str(cfg["log_level"]).upper(), logging.DEBUG))
    fh.setFormatter(LineFormatter(with_data=True))
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.addFilter(ConsoleFilter(verbose))
    ch.setFormatter(LineFormatter(with_data=False))
    LOG.addHandler(fh)
    LOG.addHandler(ch)
    STATE["log_file"] = str(log_dir / "hyperliquid-logger.log")
    logger.HOOK = _on_http



def load_config(path):
    cfg = {"addresses": [], "interval_seconds": 300, "db": "hyperliquid.sqlite",
           "fills": False, "backfill_hours": 0, "port": 8765,
           "log_dir": "logs", "log_level": "DEBUG"}
    cfg.update(json.loads(Path(path).read_text(encoding="utf-8")))
    addrs = []
    for a in cfg["addresses"]:
        a = {"address": a} if isinstance(a, str) else dict(a)
        a["address"] = a["address"].lower()
        a.setdefault("label", a["address"][:6] + "…" + a["address"][-4:])
        a.setdefault("fills", cfg["fills"])
        addrs.append(a)
    cfg["addresses"] = addrs
    cfg["interval_seconds"] = max(5.0, float(cfg["interval_seconds"]))
    p = Path(cfg["db"])
    base = Path(path).resolve().parent
    cfg["db"] = str(p if p.is_absolute() else base / p)
    d = Path(cfg["log_dir"])
    cfg["log_dir"] = str(d if d.is_absolute() else base / d)
    return cfg


class ConfigHolder:
    """Configuration for the (threaded) web server: re-read on every call, but a half-edited or invalid
    config.json must not break the API, so the last valid configuration is served instead. The failure is
    reported once per change of the file. An invalid file at the first call raises (nothing to fall back to)."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._cfg = None
        self._reported_mtime = None

    def _mtime(self):
        try:
            return Path(self.path).stat().st_mtime
        except OSError:
            return 0

    def get(self):
        with self._lock:
            try:
                self._cfg = load_config(self.path)
                self._reported_mtime = None
            except Exception as e:
                if self._cfg is None:
                    raise
                m = self._mtime()
                if m != self._reported_mtime:
                    self._reported_mtime = m
                    emit("ERROR", "config", f"config.json is invalid, the API keeps the last valid configuration: {e!r}")
            return self._cfg


# ---------------------------------------------------------------- wallet management (config.json edits)
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_CONFIG_WRITE_LOCK = threading.Lock()


class WalletError(Exception):
    """A rejected wallet change; `status` is the HTTP status to answer with."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _entry_address(entry):
    return (entry if isinstance(entry, str) else entry.get("address", "")).lower()


def add_wallet(data, address, label=None, fills=False):
    if not isinstance(address, str) or not ADDR_RE.match(address.strip()):
        raise WalletError(400, "address must be 0x followed by 40 hex digits")
    address = address.strip().lower()
    if label is not None and not isinstance(label, str):
        raise WalletError(400, "label must be text")
    label = (label or "").strip()
    if len(label) > 40:
        raise WalletError(400, "label is longer than 40 characters")
    addresses = data.setdefault("addresses", [])
    if any(_entry_address(e) == address for e in addresses):
        raise WalletError(409, "this wallet is already tracked")
    addresses.append({"address": address, "label": label or address[:6] + "…" + address[-4:], "fills": bool(fills)})


def remove_wallet(data, address):
    address = str(address or "").strip().lower()
    addresses = data.get("addresses", [])
    kept = [e for e in addresses if _entry_address(e) != address]
    if len(kept) == len(addresses):
        raise WalletError(404, "this wallet is not tracked")
    data["addresses"] = kept


def wallets_view(data):
    out = []
    for e in data.get("addresses", []):
        e = {"address": e} if isinstance(e, str) else dict(e)
        ad = e["address"].lower()
        out.append({"address": ad, "label": e.get("label") or ad[:6] + "…" + ad[-4:],
                    "fills": bool(e.get("fills", data.get("fills", False)))})
    return out


def edit_config(path, change):
    """Read config.json, apply `change(dict)`, write it back atomically. An unparseable file is never overwritten."""
    path = Path(path)
    with _CONFIG_WRITE_LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise WalletError(400, f"config.json cannot be read, fix it first: {e}")
        if not isinstance(data, dict):
            raise WalletError(400, "config.json must contain a JSON object")
        change(data)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for attempt in range(5):  # Windows: the file may be open in another thread for a moment
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
        return data


# ---------------------------------------------------------------- collector

def positions_map(db, address):
    rnd = latest_round(db, address)
    if rnd is None:
        return {}
    return dict(db.execute("SELECT coin,szi FROM position_snapshot WHERE address=? AND round_ms=?", (address, rnd)))


def emit_changes(label, address, before, after):
    """Position events between two rounds: the quickest way to see that live data arrives. Returns their count."""
    n = 0
    for coin, szi in after.items():
        if coin not in before:
            n += 1
            emit("INFO", "position", f"{label}: {coin} OPENED size {szi:,.4f}", address=address, coin=coin, new=szi)
        elif before[coin] != szi:
            n += 1
            emit("INFO", "position",
                 f"{label}: {coin} size {before[coin]:,.4f} -> {szi:,.4f} ({szi - before[coin]:+,.4f})",
                 address=address, coin=coin, old=before[coin], new=szi)
    for coin, szi in before.items():
        if coin not in after:
            n += 1
            emit("INFO", "position", f"{label}: {coin} CLOSED (was {szi:,.4f})", address=address, coin=coin, old=szi)
    return n


def collect_once(db, cfg, round_ms=None, post=None):
    """One collection round over all configured wallets."""
    kw = {"post": post} if post else {}
    round_ms = round_ms or int(time.time() * 1000)
    t_round = time.time()
    STATE["rounds"] += 1
    emit("INFO", "round", f"round #{STATE['rounds']} start ({len(cfg['addresses'])} wallets)", round=STATE["rounds"])
    for a in cfg["addresses"]:
        ad, label, t0 = a["address"], a["label"], time.time()
        try:
            before = positions_map(db, ad)
            ts, n = logger.snapshot(db, ad, round_ms=round_ms, **kw)
            s = q_summary(db, ad)
            empty = n == 0 and not s["equity"] and not s["n_open_orders"] and not s["spot"]
            if empty:
                emit("WARNING", "snapshot", f"{label}: no positions, zero equity, no open orders and no spot balances - "
                     "is the address right?", address=ad)
            else:
                emit("INFO", "snapshot",
                     f"{label}: {n} positions, equity ${s['equity']:,.0f}, position value ${s['position_value']:,.0f}, "
                     f"uPnL ${s['upnl']:+,.0f}, {s['n_open_orders']} open orders ({(time.time() - t0) * 1000:.0f} ms)",
                     address=ad, positions=n, equity=s["equity"], position_value=s["position_value"], upnl=s["upnl"],
                     open_orders=s["n_open_orders"], exchange_ts=ts, ms=round((time.time() - t0) * 1000))
            if before:
                changes = emit_changes(label, ad, before, positions_map(db, ad))
                if changes:
                    emit("INFO", "changes", f"{label}: {changes} position change{'s' if changes != 1 else ''} "
                         "(details: Debug panel, log file or --verbose)", address=ad, changes=changes)
            if a["fills"]:
                nf = logger.pull_fills(db, ad, int(cfg["backfill_hours"] * 3600_000), **kw)
                emit("INFO", "fills", f"{label}: {nf} new fills", address=ad, new_fills=nf)
            if empty:
                STATE["errors"][ad] = "no positions, equity or balances yet - is the address right?"
            else:
                STATE["errors"].pop(ad, None)
        except Exception as e:  # network trouble must not kill the loop
            hint = explain_error(e)
            STATE["errors"][ad] = hint or repr(e)
            emit("ERROR", "error", f"{label}: {hint} ({e!r})" if hint else f"{label}: {e!r}", address=ad,
                 traceback=traceback.format_exc())
    STATE["last_round_ms"] = round_ms
    STATE["last_duration_ms"] = round((time.time() - t_round) * 1000)
    emit("INFO", "round", f"round #{STATE['rounds']} done in {STATE['last_duration_ms']} ms", round=STATE["rounds"],
         ms=STATE["last_duration_ms"])


def config_mtime(path):
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0


def wait_or_config_change(stop, seconds, config_path, changed_since=None):
    """Sleep until the next round; wake early when config.json is saved (so a new interval or wallet applies at
    once). `changed_since` is the file's mtime when the finished round started: a save made while that round
    was running ends the wait immediately instead of one interval later."""
    m0 = config_mtime(config_path) if changed_since is None else changed_since
    end = time.time() + seconds
    STATE["next_round_ms"] = int(end * 1000)
    while not stop.is_set():
        if config_mtime(config_path) != m0:
            emit("INFO", "config", "config.json changed, starting a new round now")
            return
        if time.time() >= end:
            return
        stop.wait(min(1.0, max(0.0, end - time.time())))


def collect_loop(config_path, stop):
    cfg = load_config(config_path)
    db = logger.connect(cfg["db"])
    emit("INFO", "start", f"collector started, interval {cfg['interval_seconds']:.0f} s, db {cfg['db']}",
         interval=cfg["interval_seconds"], wallets=[a["label"] for a in cfg["addresses"]])
    while not stop.is_set():
        started = time.time()
        round_mtime = config_mtime(config_path)  # a save after this point is seen when the round ends
        try:
            new = load_config(config_path)
            if new["interval_seconds"] != cfg["interval_seconds"]:
                emit("INFO", "config", f"interval {cfg['interval_seconds']:.0f} s -> {new['interval_seconds']:.0f} s")
            cfg = new
        except Exception as e:
            emit("ERROR", "config", f"config error, keeping the previous one: {e!r}")
        try:
            collect_once(db, cfg)
        except Exception as e:  # never let the collector thread die silently
            emit("ERROR", "error", f"round failed: {explain_error(e) or repr(e)}", traceback=traceback.format_exc())
        wait_or_config_change(stop, max(1.0, cfg["interval_seconds"] - (time.time() - started)), config_path,
                              changed_since=round_mtime)


# ---------------------------------------------------------------- queries

def downsample(rows, limit=MAX_POINTS):
    if len(rows) <= limit:
        return rows
    step = -(-len(rows) // limit)
    return rows[::step] + ([rows[-1]] if (len(rows) - 1) % step else [])


def latest_round(db, address):
    return db.execute("SELECT MAX(round_ms) FROM account_snapshot WHERE address=?", (address,)).fetchone()[0]


def q_summary(db, address):
    rnd = latest_round(db, address)
    if rnd is None:
        return None
    eq, ntl, margin, upnl, lv, sv, npos, nord = db.execute(
        "SELECT SUM(account_value),SUM(total_ntl_pos),SUM(total_margin_used),SUM(upnl),SUM(long_value),"
        "SUM(short_value),SUM(n_positions),SUM(n_open_orders) FROM account_snapshot "
        "WHERE address=? AND round_ms=?", (address, rnd)).fetchone()
    spot = [dict(coin=c, total=t, hold=h) for c, t, h in db.execute(
        "SELECT coin,total,hold FROM spot_snapshot WHERE address=? AND round_ms=? ORDER BY total DESC",
        (address, rnd))]
    return {"round_ms": rnd, "equity": eq, "position_value": ntl, "margin_used": margin, "upnl": upnl,
            "long_value": lv, "short_value": sv, "leverage": (ntl / eq) if eq else None,
            "n_positions": npos, "n_open_orders": nord, "spot": spot}


def q_positions(db, address):
    rnd = latest_round(db, address)
    if rnd is None:
        return []
    prev = db.execute("SELECT MAX(round_ms) FROM account_snapshot WHERE address=? AND round_ms<?",
                      (address, rnd)).fetchone()[0]
    prev_szi = {}
    if prev:
        prev_szi = dict(db.execute("SELECT coin,szi FROM position_snapshot WHERE address=? AND round_ms=?",
                                   (address, prev)))
    trend_rounds = trend_references(db, address, rnd)
    cols = ("coin", "szi", "side", "entry_px", "mark_px", "position_value", "upnl", "roe", "liq_px",
            "leverage", "leverage_type", "margin_used")
    out = []
    for r in db.execute(f"SELECT {','.join(cols)} FROM position_snapshot WHERE address=? AND round_ms=? "
                        "ORDER BY position_value DESC", (address, rnd)):
        d = dict(zip(cols, r))
        d["szi_prev"] = prev_szi.get(d["coin"])
        d["trend"] = {}
        for name, ref in trend_rounds.items():
            if ref is None:
                d["trend"][name] = None
                continue
            base_ms, then = ref
            szi, pv, upnl = then.get(d["coin"], (0.0, 0.0, 0.0))  # absent then = opened within the window
            d["trend"][name] = {"base_ms": base_ms, "szi": szi, "position_value": pv, "upnl": upnl,
                                "opened": d["coin"] not in then}
        out.append(d)
    return out


TREND_WINDOWS_MS = {"15m": 15 * 60_000, "2h": 2 * 3600_000, "1d": 86400_000}
TREND_MAX_AGE = 1.5  # a reference round older than this many windows is a collection gap, not a trend


def trend_references(db, address, latest):
    """{window: (base_round_ms, {coin: (szi, position_value, upnl)}) or None}: the newest round at or before
    latest - window, or None when there is none or it is too old to represent that window."""
    out = {}
    for name, window in TREND_WINDOWS_MS.items():
        base = db.execute("SELECT MAX(round_ms) FROM account_snapshot WHERE address=? AND round_ms<=?",
                          (address, latest - window)).fetchone()[0]
        if base is None or latest - base > window * TREND_MAX_AGE:
            out[name] = None
            continue
        rows = db.execute("SELECT coin,szi,position_value,upnl FROM position_snapshot WHERE address=? AND round_ms=?",
                          (address, base))
        out[name] = (base, {c: (s, pv, u) for c, s, pv, u in rows})
    return out


def q_account_series(db, address, since_ms):
    rows = db.execute(
        "SELECT round_ms,SUM(account_value),SUM(total_ntl_pos),SUM(upnl),SUM(total_margin_used) "
        "FROM account_snapshot WHERE address=? AND round_ms>=? GROUP BY round_ms ORDER BY round_ms",
        (address, since_ms)).fetchall()
    return {"cols": ["t", "equity", "position_value", "upnl", "margin_used"], "rows": downsample(rows)}


def q_series(db, address, coin, since_ms):
    rows = db.execute(
        "SELECT round_ms,szi,position_value,upnl,mark_px,entry_px,liq_px,roe FROM position_snapshot "
        "WHERE address=? AND coin=? AND round_ms>=? ORDER BY round_ms", (address, coin, since_ms)).fetchall()
    return {"cols": ["t", "szi", "position_value", "upnl", "mark_px", "entry_px", "liq_px", "roe"],
            "rows": downsample(rows)}


def q_status(db, cfg):
    return {"interval_seconds": cfg["interval_seconds"], "now_ms": int(time.time() * 1000),
            "collector": {k: STATE[k] for k in ("rounds", "last_duration_ms", "next_round_ms", "started_ms", "log_file")},
            "addresses": [{"address": a["address"], "label": a["label"],
                           "last_round_ms": latest_round(db, a["address"]),
                           "error": STATE["errors"].get(a["address"])} for a in cfg["addresses"]]}


def tail_text(path, lines=300, max_bytes=200_000):
    """The last `lines` lines of a text file, reading at most `max_bytes` from its end."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - max_bytes))
            data = f.read()
    except OSError:
        return f"(no log file yet at {path})\n"
    out = data.decode("utf-8", errors="replace").splitlines()
    if size > max_bytes:
        out = out[1:]  # the first line is cut in the middle
    return "\n".join(out[-lines:]) + "\n"


# ---------------------------------------------------------------- http

def make_handler(holder):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, code, obj):
            self.send(code, json.dumps(obj).encode(), "application/json")

        def allowed_write(self):
            """Only the page itself may change the configuration (Host/Origin check + JSON content type)."""
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            return (self.headers.get("Host") in hosts and (origin is None or origin in {f"http://{h}" for h in hosts})
                    and ctype == "application/json")

        def do_POST(self):
            u = urlparse(self.path)
            if u.path not in ("/api/wallets", "/api/wallets/remove"):
                return self.send(404, b"unknown endpoint", "text/plain")
            if not self.allowed_write():
                emit("WARNING", "web", f"refused {u.path}: request is not from the dashboard page "
                     f"(Host={self.headers.get('Host')}, Origin={self.headers.get('Origin')})")
                return self.send_json(403, {"error": "forbidden: not a request from the dashboard page"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 10_000:
                    raise WalletError(400, "request too large")
                body = json.loads(self.rfile.read(n) or b"null")
                if not isinstance(body, dict):
                    raise WalletError(400, "a JSON object is expected")
                if u.path == "/api/wallets":
                    data = edit_config(holder.path, lambda d: add_wallet(d, body.get("address"), body.get("label"),
                                                                         body.get("fills", False)))
                    emit("INFO", "config", f"wallet added from the dashboard: {body.get('address')}")
                else:
                    data = edit_config(holder.path, lambda d: remove_wallet(d, body.get("address")))
                    emit("INFO", "config", f"wallet removed from the dashboard: {body.get('address')}")
                self.send_json(200, {"wallets": wallets_view(data)})
            except WalletError as e:
                self.send_json(e.status, {"error": str(e)})
            except ValueError:
                self.send_json(400, {"error": "invalid JSON"})
            except Exception as e:
                emit("ERROR", "web", f"{u.path}: {e!r}")
                self.send_json(500, {"error": repr(e)})

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in FILES:
                name, ctype = FILES[u.path]
                return self.send(200, (STATIC / name).read_bytes(), ctype)
            if not u.path.startswith("/api/"):
                return self.send(404, b"not found", "text/plain")
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/api/log":
                n = max(1, min(int(q.get("lines", 300)), 2000))
                return self.send(200, tail_text(str(STATE["log_file"] or ""), n).encode("utf-8"),
                                 "text/plain; charset=utf-8")
            db = None
            try:
                cfg = holder.get()  # last valid configuration, even while config.json is being edited
                db = sqlite3.connect(f"file:{cfg['db']}?mode=ro", uri=True)
                since = int(q.get("since", 0))
                a = q.get("address", "").lower()
                if u.path == "/api/status":
                    data = q_status(db, cfg)
                elif u.path == "/api/events":
                    evs = events_after(int(q.get("after", 0)), int(q.get("limit", 500)))
                    data = {"events": evs, "last_id": evs[-1]["id"] if evs else int(q.get("after", 0))}
                elif u.path == "/api/summary":
                    data = q_summary(db, a)
                elif u.path == "/api/positions":
                    data = q_positions(db, a)
                elif u.path == "/api/account_series":
                    data = q_account_series(db, a, since)
                elif u.path == "/api/series":
                    data = q_series(db, a, q.get("coin", ""), since)
                else:
                    return self.send(404, b"unknown endpoint", "text/plain")
                self.send(200, json.dumps(data).encode(), "application/json")
            except Exception as e:
                emit("ERROR", "web", f"{u.path}: {e!r}")
                self.send(500, json.dumps({"error": repr(e)}).encode(), "application/json")
            finally:
                if db is not None:
                    db.close()

    return H


class StartupError(Exception):
    """The app cannot start; the message says why and what to do."""


class LocalServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR would let a second copy bind the same port instead of failing.
    allow_reuse_address = os.name != "nt"


def bind_server(port, handler):
    try:
        return LocalServer(("127.0.0.1", int(port)), handler)
    except OSError as e:
        raise StartupError(
            f"port {port} is already in use ({e.strerror or e}). Another copy of the app is probably running: "
            f'open http://127.0.0.1:{port}, stop that copy, or change "port" in config.json.') from e


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--no-collect", action="store_true", help="only serve the dashboard")
    ap.add_argument("--verbose", action="store_true", help="print every position change and HTTP call to the console")
    ap.add_argument("--check", action="store_true", help="self-check (config, port, database, API, wallets), then exit")
    a = ap.parse_args(argv)
    if a.check:
        import check
        sys.exit(check.run(a.config))
    try:
        holder = ConfigHolder(a.config)
        cfg = holder.get()
        setup_logging(cfg, a.verbose)
        logger.connect(cfg["db"]).close()  # make sure the file and schema exist before serving
        srv = bind_server(cfg["port"], make_handler(holder))  # before the collector: two copies must never both write
    except StartupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: cannot start with config file {a.config}: {e}", file=sys.stderr)
        sys.exit(1)
    stop = threading.Event()
    if not a.no_collect:
        threading.Thread(target=collect_loop, args=(a.config, stop), daemon=True).start()
    emit("INFO", "start", f"dashboard http://127.0.0.1:{cfg['port']}  interval {cfg['interval_seconds']:.0f} s  "
         f"wallets: {', '.join(w['label'] for w in cfg['addresses']) or 'none'}  db {cfg['db']}  log {STATE['log_file']}"
         "  (Ctrl+C stops; --check = self-check, --verbose = every event)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        emit("INFO", "start", "stopped")
    finally:
        stop.set()


if __name__ == "__main__":
    main()
