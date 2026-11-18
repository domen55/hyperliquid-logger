## 1. Tests first

- [x] 1.1 Pure functions: add/remove wallet on the config dict (validation, duplicate, unknown, label default, string entries)
- [x] 1.2 `edit_config` writes atomically, keeps other keys, refuses an unparseable file
- [x] 1.3 HTTP: add/remove work; bad address 400; duplicate 409; unknown 404; foreign Origin / Host / content type 403
- [x] 1.4 Collector: empty wallet gives a WARNING and does not fail; main dex row stored when empty

## 2. Backend

- [x] 2.1 `add_wallet`, `remove_wallet`, `edit_config`, request guard, `do_POST` routes
- [x] 2.2 `logger._fetch_dex` always stores the main dex; `collect_once` empty-wallet warning and note

## 3. Frontend

- [x] 3.1 Wallets button, panel, add form, two-step Remove, errors
- [x] 3.2 Wallet selector rebuilds when the list changes; select new / first wallet
- [x] 3.3 Range label and tooltip; show a wallet's note when it has no data yet

## 4. Verification

- [x] 4.1 Full test suite green
- [x] 4.2 In the browser: add a wallet, see data, remove it; config.json valid afterwards
