import unittest

import logger

CS = {
    "time": 1000,
    "marginSummary": {"accountValue": "100", "totalNtlPos": "300", "totalRawUsd": "0", "totalMarginUsed": "30"},
    "withdrawable": "50",
    "assetPositions": [
        {"position": {"coin": "BTC", "szi": "-2", "entryPx": "100", "positionValue": "200",
                      "unrealizedPnl": "5", "returnOnEquity": "0.1", "liquidationPx": "150",
                      "marginUsed": "20", "leverage": {"type": "cross", "value": 10},
                      "cumFunding": {"allTime": "1", "sinceOpen": "2", "sinceChange": "0"}}},
        {"position": {"coin": "ETH", "szi": "4", "entryPx": "25", "positionValue": "100",
                      "unrealizedPnl": "-1", "returnOnEquity": "-0.1", "liquidationPx": None,
                      "marginUsed": "10", "leverage": {"type": "cross", "value": 10},
                      "cumFunding": {"allTime": "0", "sinceOpen": "0", "sinceChange": "0"}}},
    ],
}


EMPTY = {"time": 1000, "marginSummary": {"accountValue": "0", "totalNtlPos": "0", "totalMarginUsed": "0"},
         "withdrawable": "0", "assetPositions": []}


def fake_post(body):
    t = body["type"]
    if t == "perpDexs":
        return [None, {"name": "xyz"}]
    if t == "clearinghouseState":
        return CS if body.get("dex", "") == "" else EMPTY
    if t == "openOrders":
        return [{}, {}, {}] if body.get("dex", "") == "" else []
    if t == "spotClearinghouseState":
        return {"balances": [{"coin": "USDC", "total": "10", "hold": "1", "entryNtl": "0"}]}
    if t == "userFillsByTime":
        fake_post.calls.append(body["startTime"])
        return fake_post.pages.pop(0) if fake_post.pages else []
    raise AssertionError(t)


def fill(tid, time_ms):
    return {"coin": "BTC", "px": "1", "sz": "2", "side": "B", "time": time_ms, "startPosition": "0",
            "dir": "Close Short", "closedPnl": "3", "hash": "0x", "oid": 1, "crossed": True,
            "fee": "0.1", "feeToken": "USDC", "tid": tid}


class LoggerTest(unittest.TestCase):
    def setUp(self):
        self.db = logger.connect(":memory:")
        fake_post.calls, fake_post.pages = [], []

    def test_snapshot_values(self):
        ts, n = logger.snapshot(self.db, "0xa", post=fake_post)
        self.assertEqual((ts, n), (1000, 2))
        acc = self.db.execute("SELECT account_value,total_ntl_pos,leverage,n_open_orders,long_value,"
                              "short_value,upnl FROM account_snapshot WHERE dex=''").fetchone()
        self.assertEqual(acc, (100.0, 300.0, 3.0, 3, 100.0, 200.0, 4.0))
        btc = self.db.execute("SELECT side,mark_px,position_value FROM position_snapshot "
                              "WHERE coin='BTC'").fetchone()
        self.assertEqual(btc, ("short", 100.0, 200.0))
        self.assertIsNone(self.db.execute("SELECT liq_px FROM position_snapshot WHERE coin='ETH'").fetchone()[0])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM spot_snapshot").fetchone()[0], 1)

    def test_hip3_dex_positions_are_stored(self):
        xyz = dict(CS, assetPositions=[dict(CS["assetPositions"][0])])
        xyz["assetPositions"][0] = {"position": dict(CS["assetPositions"][0]["position"], coin="xyz:TSLA")}
        base = fake_post

        def post(body):
            return xyz if body.get("dex") == "xyz" and body["type"] == "clearinghouseState" else base(body)

        ts, n = logger.snapshot(self.db, "0xa", post=post)
        self.assertEqual(n, 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM account_snapshot").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM position_snapshot WHERE coin='xyz:TSLA'").fetchone()[0], 1)

    def test_failed_dex_writes_nothing(self):
        def post(body):
            if body.get("dex") == "xyz" and body["type"] == "clearinghouseState":
                raise OSError("boom")
            return fake_post(body)

        with self.assertRaises(OSError):
            logger.snapshot(self.db, "0xa", post=post)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM account_snapshot").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM position_snapshot").fetchone()[0], 0)

    def plan(self, sql):
        return " ".join(r[3] for r in self.db.execute("EXPLAIN QUERY PLAN " + sql, ("0xa", 1)))

    def test_whole_round_lookups_use_round_indexes(self):
        self.assertIn("(address=? AND round_ms=?)",
                      self.plan("SELECT coin,szi FROM position_snapshot WHERE address=? AND round_ms=?"))
        self.assertIn("(address=? AND round_ms=?)",
                      self.plan("SELECT coin,total FROM spot_snapshot WHERE address=? AND round_ms=?"))

    def test_old_database_gets_the_indexes(self):
        import os
        import sqlite3
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "old.sqlite")
            logger.connect(path).close()
            old = sqlite3.connect(path)
            old.execute("DROP INDEX pos_round_ms")
            old.execute("DROP INDEX spot_round_ms")
            old.execute("INSERT INTO spot_snapshot VALUES (1,'0xa','USDC',1,0,0,1)")
            old.commit()
            old.close()
            db = logger.connect(path)
            names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            self.assertTrue({"pos_round_ms", "spot_round_ms"} <= names)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM spot_snapshot").fetchone()[0], 1)
            db.close()

    def test_snapshot_idempotent_for_same_ts(self):
        logger.snapshot(self.db, "0xa", post=fake_post)
        logger.snapshot(self.db, "0xa", post=fake_post)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM position_snapshot").fetchone()[0], 2)

    def test_fills_dedupe_and_resume(self):
        fake_post.pages = [[fill(1, 10), fill(2, 20)]]
        self.assertEqual(logger.pull_fills(self.db, "0xa", backfill_ms=5, post=fake_post), 2)
        fake_post.pages = [[fill(2, 20), fill(3, 30)]]  # overlap must not duplicate
        logger.pull_fills(self.db, "0xa", post=fake_post)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fill").fetchone()[0], 3)
        self.assertEqual(fake_post.calls[1], 21)  # resumes after newest stored fill

    def test_fills_paginate(self):
        fake_post.pages = [[fill(i, 100 + i) for i in range(2000)], [fill(5000, 9000)]]
        self.assertEqual(logger.pull_fills(self.db, "0xa", backfill_ms=1, post=fake_post), 2001)
        self.assertEqual(fake_post.calls[1], 100 + 1999 + 1)


if __name__ == "__main__":
    unittest.main()
