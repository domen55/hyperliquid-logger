## Why

The dashboard is reachable only from the computer running it (bound to `127.0.0.1`). The owner wants to open it from
other devices (phone, laptop) on the home network.

## What Changes

- New setting `host` (default `127.0.0.1`). `"0.0.0.0"` serves on all network interfaces, so
  `http://<this computer's IP>:8765` works from the local network. `config.json` ships with `"host": "0.0.0.0"`.
- The page has no password, so exposing it needs two safeguards:
  - **Allowed hosts:** every request must carry a `Host` header the server knows (loopback, this computer's name and
    IPs, or `allowed_hosts` in the config); otherwise 403 with the working URLs. This blocks DNS-rebinding, where a
    web page in the browser reads the dashboard through a hostile name.
  - **Editing stays local:** adding or removing wallets is accepted only from the computer running the app, unless
    `"allow_remote_edit": true`. Other devices get a read-only dashboard.
- The console banner and `--check` list the URLs and warn that the dashboard has no password when it is exposed.
- Docs: Windows Firewall prompt, how to find the address, that this is for a trusted home network only.

## Capabilities

### Modified Capabilities
- `dashboard`: server address, allowed hosts, remote editing.
- `configuration`: `host`, `allow_remote_edit`, `allowed_hosts`.
- `diagnostics`: URLs and exposure warning in the banner and `--check`.

## Impact

`app.py`, `check.py`, `config.json`, `start.cmd`, docs, tests. The Windows Firewall rule is a system setting and is
left to the user (Windows asks once when Python starts listening).
