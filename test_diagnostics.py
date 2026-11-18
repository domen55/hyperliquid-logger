import contextlib
import http.client
import io
import json
import logging
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

import app
import check
import logger
import test_logger as tl

ADDR = "0x" + "ab" * 20


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ExplainErrorTest(unittest.TestCase):
    def hint(self, e):
        return (app.explain_error(e) or "").lower()

    def test_known_causes_get_a_hint(self):
        self.assertIn("reach", self.hint(urllib.error.URLError("dns failure")))
        self.assertIn("reach", self.hint(TimeoutError("timed out")))
        self.assertIn("reach", self.hint(ConnectionResetError()))
        http_err = lambda code: urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))
        self.assertIn("rate", self.hint(http_err(429)))
        self.assertIn("server", self.hint(http_err(503)))
        self.assertIn("http 404", self.hint(http_err(404)))
        self.assertIn("locked", self.hint(sqlite3.OperationalError("database is locked")))
        self.assertIn("write", self.hint(sqlite3.OperationalError("attempt to write a readonly database")))
        self.assertIn("not json", self.hint(json.JSONDecodeError("bad", "x", 0)))
        self.assertIn("missing field", self.hint(KeyError("marginSummary")))

    def test_unknown_error_has_no_hint(self):
        self.assertIsNone(app.explain_error(RuntimeError("something odd")))


class ConsoleTest(unittest.TestCase):
    def record(self, level, kind):
        r = logging.LogRecord("hl", level, "", 0, "m", (), None)
        r.kind = kind
        return r

    def test_quiet_console_hides_position_and_http_info(self):
        f = app.ConsoleFilter(verbose=False)
        self.assertFalse(f.filter(self.record(logging.INFO, "position")))
        self.assertFalse(f.filter(self.record(logging.DEBUG, "http")))
        self.assertTrue(f.filter(self.record(logging.INFO, "snapshot")))
        self.assertTrue(f.filter(self.record(logging.INFO, "changes")))

    def test_warnings_and_errors_always_shown(self):
        f = app.ConsoleFilter(verbose=False)
        self.assertTrue(f.filter(self.record(logging.WARNING, "http")))
        self.assertTrue(f.filter(self.record(logging.ERROR, "error")))

    def test_verbose_shows_everything(self):
        f = app.ConsoleFilter(verbose=True)
        self.assertTrue(f.filter(self.record(logging.INFO, "position")))
        self.assertTrue(f.filter(self.record(logging.DEBUG, "http")))


class LineFormatTest(unittest.TestCase):
    def render(self, with_data):
        r = logging.LogRecord("hl", logging.INFO, "", 0, "snapshot hello", (), None)
        r.data_json = '{"a": 1}'
        return app.LineFormatter(with_data).format(r)

    def test_data_json_only_in_the_file_format(self):
        self.assertTrue(self.render(True).endswith('snapshot hello  {"a": 1}'))
        self.assertTrue(self.render(False).endswith("snapshot hello"))


class CollectDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.db = logger.connect(":memory:")
        app.EVENTS.clear()
        app.STATE["errors"].clear()
        self.cfg = {"addresses": [{"address": "0xa", "label": "Test", "fills": False}], "backfill_hours": 0}

    def post_with_btc(self, szi, ts):
        cs = json.loads(json.dumps(tl.CS))
        cs["time"] = ts
        cs["assetPositions"][0]["position"]["szi"] = str(szi)
        return lambda b: cs if b["type"] == "clearinghouseState" and not b.get("dex") else tl.fake_post(b)

    def test_summary_line_counts_position_changes(self):
        app.collect_once(self.db, self.cfg, round_ms=1, post=self.post_with_btc(-2, 1000))
        app.collect_once(self.db, self.cfg, round_ms=2, post=self.post_with_btc(-3, 2000))
        summary = [e for e in app.EVENTS if e["kind"] == "changes"]
        self.assertEqual(len(summary), 1)
        self.assertIn("1 position change", summary[0]["msg"])

    def test_error_has_hint_and_traceback(self):
        def down(body):
            raise urllib.error.URLError("no route")

        app.collect_once(self.db, self.cfg, round_ms=1, post=down)
        err = [e for e in app.EVENTS if e["level"] == "ERROR"][0]
        self.assertIn("reach", err["msg"].lower())
        self.assertIn("Traceback", err["data"]["traceback"])
        self.assertIn("reach", app.STATE["errors"]["0xa"].lower())


class TailTextTest(unittest.TestCase):
    def test_last_lines_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.log"
            p.write_text("\n".join(f"line {i}" for i in range(1000)) + "\n", encoding="utf-8")
            self.assertEqual(app.tail_text(p, 3).splitlines(), ["line 997", "line 998", "line 999"])
            self.assertEqual(len(app.tail_text(p, 5000).splitlines()), 1000)
            self.assertLessEqual(len(app.tail_text(p, 5000, max_bytes=200).encode()), 200)

    def test_missing_file(self):
        self.assertIn("no log file", app.tail_text(Path("does-not-exist.log"), 10))


class LogEndpointTest(unittest.TestCase):
    def test_api_log_serves_the_tail(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "config.json"
            cfg.write_text(json.dumps({"addresses": []}))
            log = Path(d) / "app.log"
            log.write_text("a\nb\nc\nd\n", encoding="utf-8")
            old = app.STATE["log_file"]
            app.STATE["log_file"] = str(log)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(app.ConfigHolder(cfg)))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
                c.request("GET", "/api/log?lines=2")
                r = c.getresponse()
                self.assertEqual((r.status, r.read().decode().splitlines()), (200, ["c", "d"]))
                self.assertIn("text/plain", r.getheader("Content-Type"))
            finally:
                srv.shutdown()
                srv.server_close()
                app.STATE["log_file"] = old


class StartupFailuresTest(unittest.TestCase):
    def tearDown(self):
        for h in list(app.LOG.handlers):
            h.close()
        app.LOG.handlers.clear()

    def run_main(self, cfg_path):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            app.main(["--config", str(cfg_path)])
        return cm.exception.code, err.getvalue()

    def test_invalid_config_is_one_clear_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text("{ broken")
            code, text = self.run_main(p)
        self.assertEqual(code, 1)
        self.assertIn("config.json", text)
        self.assertNotIn("Traceback", text)

    def test_port_in_use_exits_before_collecting(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        try:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "config.json"
                p.write_text(json.dumps({"addresses": [ADDR], "port": busy.getsockname()[1], "db": "x.sqlite",
                                         "log_dir": "logs"}))
                app.EVENTS.clear()
                code, text = self.run_main(p)
                for h in list(app.LOG.handlers):
                    h.close()
                app.LOG.handlers.clear()
        finally:
            busy.close()
        self.assertEqual(code, 1)
        self.assertIn("already in use", text)
        self.assertFalse([e for e in app.EVENTS if e["kind"] == "round"])  # the collector never started


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = self.dir / "config.json"
        self.write_cfg({})

    def tearDown(self):
        self.tmp.cleanup()

    def write_cfg(self, extra):
        data = {"addresses": [{"address": ADDR, "label": "W"}], "port": free_port(), "db": "t.sqlite", "log_dir": "logs"}
        data.update(extra)
        self.cfg.write_text(json.dumps(data))

    def run_check(self, post=tl.fake_post):
        lines = []
        code = check.run(self.cfg, out=lines.append, post=post)
        return code, "\n".join(lines)

    def test_everything_ok(self):
        code, text = self.run_check()
        self.assertEqual(code, 0, text)
        for part in ("Python", "config", "port", "database", "Hyperliquid API", "W:"):
            self.assertTrue(any(l.startswith("OK") and part in l for l in text.splitlines()), (part, text))
        self.assertNotIn("FAIL", text)

    def test_api_down_fails_and_skips_wallets(self):
        def down(body):
            raise urllib.error.URLError("no route")

        code, text = self.run_check(post=down)
        self.assertEqual(code, 1)
        api = [l for l in text.splitlines() if "Hyperliquid API" in l][0]
        self.assertTrue(api.startswith("FAIL"))
        self.assertIn("reach", text.lower())
        self.assertIn("not checked", text)

    def test_invalid_config_fails(self):
        self.cfg.write_text("{ broken")
        code, text = self.run_check()
        self.assertEqual(code, 1)
        self.assertTrue(any(l.startswith("FAIL") and "config" in l for l in text.splitlines()), text)

    def test_port_in_use_is_only_a_warning(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        try:
            self.write_cfg({"port": busy.getsockname()[1]})
            code, text = self.run_check()
        finally:
            busy.close()
        self.assertEqual(code, 0, text)  # probably this very app, already running
        self.assertTrue(any(l.startswith("WARN") and "port" in l for l in text.splitlines()), text)

    def test_recent_log_errors_are_listed(self):
        (self.dir / "logs").mkdir()
        (self.dir / "logs" / "hyperliquid-logger.log").write_text(
            "2026-11-18 10:00:00,000 INFO    start    x\n2026-11-18 10:01:00,000 ERROR   error    Test: boom\n",
            encoding="utf-8")
        code, text = self.run_check()
        self.assertTrue(any(l.startswith("WARN") and "boom" in l for l in text.splitlines()), text)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
