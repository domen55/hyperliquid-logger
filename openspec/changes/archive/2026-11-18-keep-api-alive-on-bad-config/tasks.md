## 1. Tests first

- [x] 1.1 Test: `ConfigHolder.get()` returns the last valid config when the file becomes invalid, and a new one once it is fixed
- [x] 1.2 Test: repeated `get()` on the same broken file emits exactly one ERROR `config` event; a new bad save emits another
- [x] 1.3 Test: an invalid file at the first `get()` raises

## 2. Implementation

- [x] 2.1 Add `ConfigHolder` to `app.py` and use it in the HTTP handler and `main()`
- [x] 2.2 Keep collector behaviour unchanged

## 3. Verification

- [x] 3.1 Full test suite green
- [x] 3.2 Live: break `config.json`, `/api/status` still answers, Debug shows one `config` error; restore the file
