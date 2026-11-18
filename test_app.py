import json
import tempfile
import unittest
from pathlib import Path

import app
import logger
import test_logger as tl


class AppQueriesTest(unittest.TestCase):
    def setUp(self):
        self.db = logger.connect(":memory:")
        tl.fake_post.calls, tl.fake_post.pages = [], []

    def round(self, ts, szi, rnd, drop_eth=False):
        """One collection round where the BTC size is `szi` (optionally without the ETH position)."""
        cs = json.loads(json.dumps(tl.CS))
        cs["time"] = ts
        cs["assetPositions"][0]["position"]["szi"] = str(szi)
        if drop_eth:
            cs["assetPositions"] = cs["assetPositions"][:1]
        base = tl.fake_post
        logger.snapshot(self.db, "0xa", post=lambda b: cs if b["type"] == "clearinghouseState" and not b.get("dex")
                        else base(b), round_ms=rnd)

    def test_summary_positions_and_delta(self):
        self.round(1000, -2, 10_000)
        self.round(2000, -3, 20_000)
        s = app.q_summary(self.db, "0xa")
        self.assertEqual((s["round_ms"], s["equity"], s["n_positions"], s["n_open_orders"]), (20_000, 100.0, 2, 3))
        self.assertAlmostEqual(s["leverage"], 3.0)
        self.assertEqual(s["spot"][0]["coin"], "USDC")
        pos = {p["coin"]: p for p in app.q_positions(self.db, "0xa")}
        self.assertEqual((pos["BTC"]["szi"], pos["BTC"]["szi_prev"]), (-3.0, -2.0))
        self.assertEqual(list(pos)[0], "BTC")  # ordered by position value

    def test_series_rows_are_per_round(self):
        for i in range(3):
            self.round(1000 + i, -2 - i, 10_000 * (i + 1))
        s = app.q_series(self.db, "0xa", "BTC", 15_000)
        self.assertEqual([r[0] for r in s["rows"]], [20_000, 30_000])
        self.assertEqual([r[1] for r in s["rows"]], [-3.0, -4.0])
        a = app.q_account_series(self.db, "0xa", 0)
        self.assertEqual(len(a["rows"]), 3)
        self.assertEqual(a["rows"][0][1], 100.0)

    def test_empty_address(self):
        self.assertIsNone(app.q_summary(self.db, "0xnone"))
        self.assertEqual(app.q_positions(self.db, "0xnone"), [])

    # ---- position trends: 15 m / 2 h / 1 d reference rounds
    M = 60_000
    R = 1_000_000_000  # latest round

    def rounds_at(self, spec):
        """spec: [(minutes_before_latest, btc_size), ...]"""
        for mins, szi in spec:
            rnd = self.R - mins * self.M
            self.round(rnd, szi, rnd)

    def trends(self):
        return {p["coin"]: p["trend"] for p in app.q_positions(self.db, "0xa")}

    def test_trends_pick_the_reference_rounds(self):
        self.rounds_at([(130, -1), (20, -2), (16, -3), (1, -4), (0, -5)])
        t = self.trends()["BTC"]
        self.assertEqual((t["15m"]["szi"], t["15m"]["base_ms"]), (-3.0, self.R - 16 * self.M))
        self.assertEqual((t["2h"]["szi"], t["2h"]["base_ms"]), (-1.0, self.R - 130 * self.M))
        self.assertIsNone(t["1d"])  # no round that old
        eth = self.trends()["ETH"]["15m"]
        self.assertEqual((eth["szi"], eth["position_value"], eth["opened"]), (4.0, 100.0, False))

    def test_trends_need_enough_history(self):
        self.rounds_at([(20, -2), (0, -3)])
        t = self.trends()["BTC"]
        self.assertEqual(t["15m"]["szi"], -2.0)
        self.assertIsNone(t["2h"])
        self.assertIsNone(t["1d"])

    def test_trend_ignores_reference_older_than_one_and_a_half_windows(self):
        self.rounds_at([(60, -2), (0, -3)])  # collection gap: nothing between 60 and 0 minutes ago
        t = self.trends()["BTC"]
        self.assertIsNone(t["15m"])  # 60 min old > 22.5 min
        self.assertIsNone(t["2h"])   # no round at or before 120 min

    def test_position_opened_within_the_window(self):
        self.round(self.R - 20 * self.M, -2, self.R - 20 * self.M, drop_eth=True)
        self.round(self.R, -2, self.R)
        eth = self.trends()["ETH"]["15m"]
        self.assertTrue(eth["opened"])
        self.assertEqual((eth["szi"], eth["position_value"], eth["upnl"]), (0.0, 0.0, 0.0))

    def test_downsample_keeps_last_point(self):
        rows = [(i,) for i in range(10_000)]
        out = app.downsample(rows, 1000)
        self.assertLessEqual(len(out), 1001)
        self.assertEqual(out[-1], (9_999,))

    def test_config_defaults_and_labels(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps({"addresses": ["0xABCDEF0123456789"], "interval_seconds": 1}))
            c = app.load_config(p)
            self.assertEqual(c["interval_seconds"], 5.0)  # floor protects the API
            self.assertEqual(c["addresses"][0]["address"], "0xabcdef0123456789")
            self.assertFalse(c["addresses"][0]["fills"])
            self.assertEqual(Path(c["db"]).parent, Path(d).resolve())



class EventsTest(unittest.TestCase):
    def setUp(self):
        self.db = logger.connect(":memory:")
        tl.fake_post.calls, tl.fake_post.pages = [], []
        app.EVENTS.clear()
        self.cfg = {"addresses": [{"address": "0xa", "label": "Test", "fills": False}], "backfill_hours": 0}

    def post_with_btc(self, szi, ts):
        cs = json.loads(json.dumps(tl.CS))
        cs["time"] = ts
        cs["assetPositions"][0]["position"]["szi"] = str(szi)
        return lambda b: cs if b["type"] == "clearinghouseState" and not b.get("dex") else tl.fake_post(b)

    def test_rounds_emit_snapshot_and_position_change_events(self):
        app.collect_once(self.db, self.cfg, round_ms=10_000, post=self.post_with_btc(-2, 1000))
        app.collect_once(self.db, self.cfg, round_ms=70_000, post=self.post_with_btc(-2.5, 2000))
        kinds = [e["kind"] for e in app.EVENTS]
        self.assertEqual(kinds.count("snapshot"), 2)
        changes = [e for e in app.EVENTS if e["kind"] == "position"]
        self.assertEqual(len(changes), 1)  # first round has nothing to compare with
        self.assertIn("BTC size -2.0000 -> -2.5000", changes[0]["msg"])
        self.assertEqual(kinds.count("round"), 4)  # start + done for each of the two rounds

    def test_failed_wallet_emits_error_and_continues(self):
        def boom(b):
            raise OSError("network down")

        app.collect_once(self.db, self.cfg, round_ms=1, post=boom)
        errs = [e for e in app.EVENTS if e["level"] == "ERROR"]
        self.assertEqual(len(errs), 1)
        self.assertIn("network down", errs[0]["msg"])
        self.assertIn("0xa", app.STATE["errors"])

    def test_events_after_returns_only_newer(self):
        a = app.emit("INFO", "x", "one")
        app.emit("INFO", "x", "two")
        self.assertEqual([e["msg"] for e in app.events_after(a["id"])], ["two"])

    def test_http_hook_reports_calls_and_retries(self):
        import io
        import urllib.error
        from unittest import mock

        seen = []
        outcomes = [urllib.error.HTTPError("u", 429, "slow", {}, io.BytesIO(b"")), io.BytesIO(b'{"ok": 1}')]

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=0):
            o = outcomes.pop(0)
            if isinstance(o, Exception):
                raise o
            return Resp(o.getvalue())

        with mock.patch.object(logger.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(logger.time, "sleep"), mock.patch.object(logger, "HOOK", seen.append):
            self.assertEqual(logger.post({"type": "clearinghouseState", "dex": "xyz"}), {"ok": 1})
        self.assertEqual([e["kind"] for e in seen], ["http_error", "http"])
        self.assertEqual(seen[0]["error"], "HTTP 429")
        self.assertEqual((seen[1]["type"], seen[1]["dex"], seen[1]["attempt"]), ("clearinghouseState", "xyz", 2))


class ConfigHolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "c.json"
        self.write({"addresses": ["0xa"], "interval_seconds": 60})
        app.EVENTS.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data, raw=None):
        self.path.write_text(raw if raw is not None else json.dumps(data), encoding="utf-8")
        import os
        st = self.path.stat()  # make sure the mtime changes even on coarse filesystems
        os.utime(self.path, (st.st_atime, st.st_mtime + 1 + getattr(self, "_bump", 0)))
        self._bump = getattr(self, "_bump", 0) + 2

    def config_errors(self):
        return [e for e in app.EVENTS if e["kind"] == "config" and e["level"] == "ERROR"]

    def test_keeps_last_good_config_when_file_breaks_and_recovers(self):
        h = app.ConfigHolder(self.path)
        self.assertEqual(h.get()["interval_seconds"], 60)
        self.write(None, raw="{ not json")
        self.assertEqual(h.get()["interval_seconds"], 60)  # last good config
        self.write({"addresses": ["0xa"], "interval_seconds": 30})
        self.assertEqual(h.get()["interval_seconds"], 30)  # fixed again

    def test_error_reported_once_per_file_change(self):
        h = app.ConfigHolder(self.path)
        h.get()
        self.write(None, raw="{ not json")
        for _ in range(5):
            h.get()
        self.assertEqual(len(self.config_errors()), 1)
        self.write(None, raw="{ still bad")
        h.get()
        self.assertEqual(len(self.config_errors()), 2)

    def test_invalid_file_at_startup_raises(self):
        self.write(None, raw="{ not json")
        with self.assertRaises(ValueError):
            app.ConfigHolder(self.path).get()


if __name__ == "__main__":
    unittest.main()
