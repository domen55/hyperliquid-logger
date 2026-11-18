"""Self-check: `python app.py --check` (or check.cmd).

Prints one OK / WARN / FAIL line per thing that can go wrong when running the logger, with a hint on failure.
It does not start the collector or the server and writes nothing to the real database (wallets are probed
into an in-memory one). Exit status 0 = nothing failed, 1 = something failed.
"""
import socket
import sys
import time
from pathlib import Path

import app
import logger


def run(config_path, out=print, post=None):
    post = post or logger.post
    failed = 0

    def say(tag, msg, hint=None):
        out(f"{tag:<5}{msg}")
        if hint:
            out(f"      -> {hint}")

    def fail(msg, hint=None):
        nonlocal failed
        failed += 1
        say("FAIL", msg, hint)

    out(f"Hyperliquid logger self-check, {time.strftime('%Y-%m-%d %H:%M:%S')}")
    v = sys.version_info
    if v >= (3, 9):
        say("OK", f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor}.{v.micro}", "Python 3.9 or newer is needed")

    try:
        cfg = app.load_config(config_path)
    except Exception as e:
        fail(f"config {config_path}: {e}", "fix the JSON (a missing comma or quote is the usual cause) and run the check again")
        out("Result: 1 problem found")
        return 1
    n = len(cfg["addresses"])
    if n:
        say("OK", f"config {config_path}: {n} wallet(s), interval {cfg['interval_seconds']:.0f} s, port {cfg['port']}")
    else:
        say("WARN", f"config {config_path}: no wallets yet", "add one with the Wallets button on the page, or in config.json")

    port = int(cfg["port"])
    s = socket.socket()
    try:
        s.bind((cfg["host"], port))
        say("OK", f"port {port} is free")
    except OSError:
        say("WARN", f"port {port} is in use",
            f"if this is the app already running, open http://127.0.0.1:{port}; otherwise another program uses the "
            'port: change "port" in config.json')
    finally:
        s.close()
    say("OK", "dashboard: " + ", ".join(app.dashboard_urls(cfg["host"], port, app.lan_ips())))
    note = app.exposure_notice(cfg)
    if note:
        say("WARN", note)

    try:
        db = logger.connect(cfg["db"])
        rounds, last = db.execute("SELECT COUNT(DISTINCT round_ms), MAX(round_ms) FROM account_snapshot").fetchone()
        db.close()
        size = Path(cfg["db"]).stat().st_size / 1e6
        when = (f", last round {time.strftime('%H:%M:%S', time.localtime(last / 1000))} "
                f"({(time.time() - last / 1000) / 60:.0f} min ago)") if last else ""
        say("OK", f"database {cfg['db']}: {size:.1f} MB, {rounds} rounds{when}")
    except Exception as e:
        fail(f"database {cfg['db']}: {e}", app.explain_error(e) or "check the folder permissions and free disk space")

    dexs = None
    try:
        t = time.time()
        dexs = logger.list_dexs(post)
        say("OK", f"Hyperliquid API reachable ({len(dexs)} perp dexes, {(time.time() - t) * 1000:.0f} ms)")
    except Exception as e:
        fail(f"Hyperliquid API: {e!r}", app.explain_error(e) or "see the log file for the full error")

    for a in cfg["addresses"]:
        if dexs is None:
            say("WARN", f"{a['label']}: not checked (the API is unreachable)")
            continue
        try:
            mem = logger.connect(":memory:")
            _, positions = logger.snapshot(mem, a["address"], post=post, dexs=dexs)
            sm = app.q_summary(mem, a["address"])
            if not positions and not sm["equity"] and not sm["n_open_orders"] and not sm["spot"]:
                say("WARN", f"{a['label']}: no positions, equity or balances", "is the address right? " + a["address"])
            else:
                say("OK", f"{a['label']}: {positions} positions, equity ${sm['equity']:,.0f}, "
                          f"{sm['n_open_orders']} open orders, {len(sm['spot'])} spot balances")
        except Exception as e:
            fail(f"{a['label']}: {e!r}", app.explain_error(e) or "see the log file for the full error")

    log = Path(cfg["log_dir"]) / "hyperliquid-logger.log"
    if log.exists():
        errors = [l for l in app.tail_text(log, 400).splitlines() if " ERROR " in l]
        if errors:
            say("WARN", f"log {log}: {len(errors)} error(s) in the last 400 lines, latest:")
            for l in errors[-3:]:
                say("WARN", "log: " + l[:170])
        else:
            say("OK", f"log {log}: no errors in the last 400 lines")
    else:
        say("OK", f"log file will be created at {log}")

    out("Result: all OK" if not failed else f"Result: {failed} problem(s) found")
    return 1 if failed else 0
