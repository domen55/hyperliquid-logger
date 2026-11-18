## 1. Tests first

- [x] 1.1 `request_allowed`: Host allow-list, write rules, remote edit off by default, own names / `.local` / `allowed_hosts`
- [x] 1.2 Config defaults `host`, `allow_remote_edit`, `allowed_hosts`
- [x] 1.3 `dashboard_urls`: loopback only vs LAN addresses; exposure notice
- [x] 1.4 HTTP: foreign Host gets 403 with the working URLs on GET and POST
- [x] 1.5 `bind_server` honours `host`; port-in-use message names the host

## 2. Implementation

- [x] 2.1 `load_config` keys, `local_host_names`, `lan_ips`, `request_allowed`, handler wiring
- [x] 2.2 Banner and `check.py` URLs and notice

## 3. Config and docs

- [x] 3.1 `config.json` host 0.0.0.0; `start.cmd`; NAVODILA.md and README (firewall, find the address, trusted network only)

## 4. Verification

- [x] 4.1 Full test suite green
- [x] 4.2 Live: open via the LAN IP, foreign Host refused, edit from LAN IP refused
