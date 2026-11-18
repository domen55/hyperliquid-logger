import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import app
import logger
import test_logger as tl

A = "0x" + "ab" * 20
B = "0x" + "CD" * 20  # mixed case on purpose


class WalletFunctionsTest(unittest.TestCase):
    def test_add_normalises_and_defaults_label(self):
        data = {"addresses": []}
        app.add_wallet(data, B, None, False)
        self.assertEqual(data["addresses"], [{"address": B.lower(), "label": B.lower()[:6] + "…" + B.lower()[-4:],
                                              "fills": False}])

    def test_add_validates(self):
        for bad in ("", "0x123", "0x" + "g" * 40, A + "00", "ab" * 20, None, 5):
            with self.assertRaises(app.WalletError) as cm:
                app.add_wallet({"addresses": []}, bad, "x", False)
            self.assertEqual(cm.exception.status, 400, bad)
        with self.assertRaises(app.WalletError):
            app.add_wallet({"addresses": []}, A, "x" * 41, False)

    def test_duplicate_is_409_even_against_string_entries(self):
        data = {"addresses": [A.upper().replace("0X", "0x")]}  # plain string entry, other case
        with self.assertRaises(app.WalletError) as cm:
            app.add_wallet(data, A, "again", False)
        self.assertEqual(cm.exception.status, 409)

    def test_remove(self):
        data = {"addresses": [A, {"address": B.lower(), "label": "b"}]}
        app.remove_wallet(data, A)
        self.assertEqual([x["address"] if isinstance(x, dict) else x for x in data["addresses"]], [B.lower()])
        with self.assertRaises(app.WalletError) as cm:
            app.remove_wallet(data, A)
        self.assertEqual(cm.exception.status, 404)


class EditConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_keeps_other_keys_and_leaves_no_temp_file(self):
        self.path.write_text(json.dumps({"interval_seconds": 60, "port": 1234, "addresses": []}))
        app.edit_config(self.path, lambda d: app.add_wallet(d, A, "A", True))
        saved = json.loads(self.path.read_text())
        self.assertEqual((saved["interval_seconds"], saved["port"]), (60, 1234))
        self.assertEqual(saved["addresses"][0]["fills"], True)
        self.assertEqual([p.name for p in Path(self.tmp.name).iterdir()], ["config.json"])

    def test_unparseable_file_is_not_overwritten(self):
        self.path.write_text("{ broken")
        with self.assertRaises(app.WalletError) as cm:
            app.edit_config(self.path, lambda d: app.add_wallet(d, A, "A", False))
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(self.path.read_text(), "{ broken")

    def test_failed_change_does_not_touch_the_file(self):
        self.path.write_text(json.dumps({"addresses": []}))
        before = self.path.read_text()
        with self.assertRaises(app.WalletError):
            app.edit_config(self.path, lambda d: app.remove_wallet(d, A))
        self.assertEqual(self.path.read_text(), before)


class WalletHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "config.json"
        cls.path.write_text(json.dumps({"interval_seconds": 60, "addresses": []}))
        app.EVENTS.clear()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(app.ConfigHolder(cls.path)))
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        self.path.write_text(json.dumps({"interval_seconds": 60, "addresses": []}))

    def post(self, path, body, headers=None, raw=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", path, raw if raw is not None else json.dumps(body), h)
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"null"))
        c.close()
        return out

    def addresses(self):
        return [a["address"] for a in json.loads(self.path.read_text())["addresses"]]

    def test_add_then_remove(self):
        status, body = self.post("/api/wallets", {"address": B, "label": "Mine", "fills": True})
        self.assertEqual(status, 200)
        self.assertEqual(body["wallets"][0]["label"], "Mine")
        self.assertEqual(self.addresses(), [B.lower()])
        status, body = self.post("/api/wallets/remove", {"address": B})
        self.assertEqual((status, body["wallets"]), (200, []))
        self.assertEqual(self.addresses(), [])

    def test_errors_leave_the_file_unchanged(self):
        before = self.path.read_text()
        self.assertEqual(self.post("/api/wallets", {"address": "0x12"})[0], 400)
        self.assertEqual(self.post("/api/wallets/remove", {"address": A})[0], 404)
        self.assertEqual(self.post("/api/wallets", None, raw="{not json")[0], 400)
        self.assertEqual(self.path.read_text(), before)
        self.assertEqual(self.post("/api/wallets", {"address": A})[0], 200)
        self.assertEqual(self.post("/api/wallets", {"address": A})[0], 409)

    def test_requests_not_from_the_page_are_refused(self):
        for headers in ({"Origin": "https://example.com"}, {"Host": "evil.example:80"},
                        {"Origin": f"http://127.0.0.1:{self.port + 1}"}, {"Content-Type": "text/plain"}):
            status, _ = self.post("/api/wallets", {"address": A}, headers)
            self.assertEqual(status, 403, headers)
        self.assertEqual(self.addresses(), [])

    def test_same_origin_is_allowed(self):
        status, _ = self.post("/api/wallets", {"address": A}, {"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        status, _ = self.post("/api/wallets/remove", {"address": A}, {"Origin": f"http://localhost:{self.port}",
                                                                      "Host": f"localhost:{self.port}"})
        self.assertEqual(status, 200)


class ConfigWakeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"
        self.path.write_text("{}")
        app.EVENTS.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def touch_later(self):
        import os
        st = self.path.stat()
        os.utime(self.path, (st.st_atime, st.st_mtime + 5))

    def test_change_during_the_round_skips_the_wait(self):
        import time
        started_mtime = self.path.stat().st_mtime  # what the round started with
        self.touch_later()                          # wallet added while the round was running
        t = time.time()
        app.wait_or_config_change(threading.Event(), 30, self.path, changed_since=started_mtime)
        self.assertLess(time.time() - t, 2)
        self.assertTrue([e for e in app.EVENTS if "changed" in e["msg"]])

    def test_change_during_the_wait_ends_it(self):
        import time
        threading.Timer(0.3, self.touch_later).start()
        t = time.time()
        app.wait_or_config_change(threading.Event(), 30, self.path)
        self.assertLess(time.time() - t, 3)

    def test_no_change_waits_for_the_stop_event(self):
        import time
        stop = threading.Event()
        threading.Timer(0.3, stop.set).start()
        t = time.time()
        app.wait_or_config_change(stop, 30, self.path)
        self.assertLess(time.time() - t, 3)


class EmptyWalletTest(unittest.TestCase):
    def post_empty(self, body):
        t = body["type"]
        if t == "perpDexs":
            return [None, {"name": "xyz"}]
        if t == "clearinghouseState":
            return tl.EMPTY
        if t == "openOrders":
            return []
        if t == "spotClearinghouseState":
            return {"balances": []}
        raise AssertionError(t)

    def setUp(self):
        self.db = logger.connect(":memory:")
        app.EVENTS.clear()
        app.STATE["errors"].clear()
        self.cfg = {"addresses": [{"address": "0xa", "label": "Typo", "fills": False}], "backfill_hours": 0}

    def test_main_dex_row_is_stored_even_when_empty(self):
        logger.snapshot(self.db, "0xa", post=self.post_empty, round_ms=1)
        rows = self.db.execute("SELECT dex, account_value FROM account_snapshot").fetchall()
        self.assertEqual(rows, [("", 0.0)])  # the empty builder dex is not stored

    def test_empty_wallet_warns_and_does_not_fail(self):
        app.collect_once(self.db, self.cfg, round_ms=1, post=self.post_empty)
        warn = [e for e in app.EVENTS if e["level"] == "WARNING" and e["kind"] == "snapshot"]
        self.assertEqual(len(warn), 1)
        self.assertIn("address", warn[0]["msg"])
        self.assertFalse([e for e in app.EVENTS if e["level"] == "ERROR"])
        self.assertIn("no positions", app.STATE["errors"]["0xa"])

    def test_note_clears_when_data_appears(self):
        app.collect_once(self.db, self.cfg, round_ms=1, post=self.post_empty)
        app.collect_once(self.db, self.cfg, round_ms=2, post=tl.fake_post)
        self.assertNotIn("0xa", app.STATE["errors"])


if __name__ == "__main__":
    unittest.main()
