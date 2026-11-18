## Why

`config.json` is meant to be edited while the app runs (interval, wallets). The collector already keeps the
previous configuration when the saved file is invalid, but every dashboard API request reloads the file
outside its error handling. While the file is half-edited or invalid, `/api/*` requests fail with a dropped
connection and the page shows nothing, although data is still being collected.

## What Changes

- The web server uses the last valid configuration when `config.json` cannot be read or parsed.
- The problem is reported once per file change as an ERROR `config` event (visible in the Debug panel and
  the log file), not on every request.
- The application still refuses to start when the file is invalid at startup (there is no previous
  configuration to fall back to).

## Capabilities

### Modified Capabilities
- `configuration`: the "Live reload" requirement also covers the dashboard API.

## Impact

`app.py` only (`load_config` call in the HTTP handler, new small config holder); `test_app.py`.
No API, schema or UI changes.
