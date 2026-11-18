import http.client
import json
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import app
import logger

OWN = {"mypc", "192.168.1.20"}
PORT = 8765


def allowed(host, client="127.0.0.1", origin=None, ctype="application/json", write=False, cfg=None):
    return app.request_allowed(client, host, origin, ctype, PORT, cfg or {}, OWN, write)


class AllowedHostsTest(unittest.TestCase):
    def test_default_names_and_own_names_are_allowed(self):
        for h in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765", "mypc:8765", "MyPC:8765", "192.168.1.20:8765",
                  "mypc.local:8765"):
            self.assertTrue(allowed(h)[0], h)

    def test_other_hosts_are_refused_and_the_working_urls_are_named(self):
        ok, why = allowed("evil.example:8765")
        self.assertFalse(ok)
        self.assertIn("http://192.168.1.20:8765", why)
        self.assertIn("http://127.0.0.1:8765", why)
        self.assertFalse(allowed("mypc:9999")[0])  # right name, wrong port
        self.assertFalse(allowed(None)[0])

    def test_extra_hosts_from_the_config(self):
        cfg = {"allowed_hosts": ["Dash.Home:8765"]}
        self.assertTrue(allowed("dash.home:8765", cfg=cfg)[0])


class WriteRulesTest(unittest.TestCase):
    def test_this_computer_may_write(self):
        self.assertTrue(allowed("127.0.0.1:8765", write=True)[0])
        self.assertTrue(allowed("localhost:8765", client="::1", write=True)[0])

    def test_other_devices_cannot_write_by_default(self):
        ok, why = allowed("192.168.1.20:8765", client="192.168.1.55", write=True)
        self.assertFalse(ok)
        self.assertIn("allow_remote_edit", why)

    def test_other_devices_can_write_when_switched_on(self):
        cfg = {"allow_remote_edit": True}
        self.assertTrue(allowed("192.168.1.20:8765", client="192.168.1.55", write=True, cfg=cfg)[0])

    def test_remote_writes_still_need_a_same_origin_json_request(self):
        cfg = {"allow_remote_edit": True}
        host = "192.168.1.20:8765"
        self.assertFalse(allowed(host, "192.168.1.55", origin="https://example.com", write=True, cfg=cfg)[0])
        self.assertFalse(allowed(host, "192.168.1.55", ctype="text/plain", write=True, cfg=cfg)[0])
        self.assertTrue(allowed(host, "192.168.1.55", origin="http://192.168.1.20:8765", write=True, cfg=cfg)[0])

    def test_reading_is_allowed_for_other_devices(self):
        self.assertTrue(allowed("192.168.1.20:8765", client="192.168.1.55", write=False)[0])


class ConfigAndUrlsTest(unittest.TestCase):
    def test_config_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text("{}")
            c = app.load_config(p)
        self.assertEqual((c["host"], c["allow_remote_edit"], c["allowed_hosts"]), ("127.0.0.1", False, []))

    def test_config_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps({"host": "0.0.0.0", "allow_remote_edit": True, "allowed_hosts": ["x:1"]}))
            c = app.load_config(p)
        self.assertEqual((c["host"], c["allow_remote_edit"], c["allowed_hosts"]), ("0.0.0.0", True, ["x:1"]))

    def test_urls_local_only(self):
        self.assertEqual(app.dashboard_urls("127.0.0.1", 8765, ["192.168.1.20"]), ["http://127.0.0.1:8765"])
        self.assertIsNone(app.exposure_notice({"host": "127.0.0.1"}))

    def test_urls_when_exposed(self):
        urls = app.dashboard_urls("0.0.0.0", 8765, ["192.168.1.20", "10.0.0.5"])
        self.assertEqual(urls, ["http://127.0.0.1:8765", "http://192.168.1.20:8765", "http://10.0.0.5:8765"])
        self.assertEqual(app.dashboard_urls("192.168.1.20", 8765, ["192.168.1.20"]), ["http://192.168.1.20:8765"])

    def test_exposure_notice_mentions_password_editing_and_firewall(self):
        note = app.exposure_notice({"host": "0.0.0.0", "allow_remote_edit": False})
        self.assertIn("no password", note)
        self.assertIn("read-only", note)
        self.assertIn("Firewall", note)
        self.assertIn("can also change wallets", app.exposure_notice({"host": "0.0.0.0", "allow_remote_edit": True}))

    def test_local_host_names_include_this_computers_name(self):
        self.assertIn(socket.gethostname().lower(), app.local_host_names())


class BindTest(unittest.TestCase):
    def test_host_is_used_and_named_in_the_error(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        try:
            with self.assertRaises(app.StartupError) as cm:
                app.bind_server("127.0.0.1", busy.getsockname()[1], app.make_handler(None))
        finally:
            busy.close()
        self.assertIn("already in use", str(cm.exception))

    def test_binds_on_all_interfaces(self):
        srv = app.bind_server("0.0.0.0", 0, app.make_handler(None))
        try:
            self.assertEqual(srv.server_address[0], "0.0.0.0")
        finally:
            srv.server_close()


class HostCheckHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cfg = Path(cls.tmp.name) / "config.json"
        cls.cfg.write_text(json.dumps({"addresses": [], "db": "t.sqlite"}))
        logger.connect(str(Path(cls.tmp.name) / "t.sqlite")).close()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0),
                                      app.make_handler(app.ConfigHolder(cls.cfg), own_names={"mypc", "192.168.1.20"}))
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, path, host):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", path, headers={"Host": host})
        r = c.getresponse()
        out = (r.status, r.read().decode())
        c.close()
        return out

    def test_known_host_is_served_unknown_is_refused(self):
        self.assertEqual(self.get("/", f"mypc:{self.port}")[0], 200)
        self.assertEqual(self.get("/api/status", f"192.168.1.20:{self.port}")[0], 200)
        status, body = self.get("/api/status", f"evil.example:{self.port}")
        self.assertEqual(status, 403)
        self.assertIn(f"http://192.168.1.20:{self.port}", body)
        self.assertEqual(self.get("/", f"evil.example:{self.port}")[0], 403)


if __name__ == "__main__":
    unittest.main()
