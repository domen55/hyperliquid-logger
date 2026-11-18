## Why

Wallets can only be added or removed by editing `config.json` by hand. The owner wants to do it on the page.
While at it, two things came up: the time-range selector at the top ("1 h ... all") is not obviously a chart
range, and a wallet with no activity (typo in the address, spot-only wallet) currently breaks the snapshot event
or shows nothing at all.

## What Changes

- A **Wallets** panel on the dashboard lists the tracked wallets with a Remove button (two-step) and a form to add
  one (address, label, collect fills). Changes are written to `config.json`; the running collector picks them up
  at once (it already restarts the round when the file changes).
- New API: `POST /api/wallets` (add) and `POST /api/wallets/remove`. Because the server writes a file, requests are
  accepted only from the page itself (Host/Origin check, JSON content type).
- Removing a wallet keeps its stored history (re-adding shows it again).
- The range selector is labelled "Range" with a tooltip saying it applies to the charts, not to the trend columns.
- The main perp dex is always stored, so a spot-only or empty wallet shows its (zero) summary and spot balances;
  a wallet with no activity at all raises a WARNING so a wrong address is noticed.

## Capabilities

### Modified Capabilities
- `dashboard`: wallet management, local write protection, range selector scope.
- `data-collection`: main dex always stored; empty-wallet warning.

## Impact

`app.py`, `logger.py` (one condition), `static/index.html`, tests. `config.json` is rewritten (pretty-printed
JSON, same keys) when wallets are added or removed.
