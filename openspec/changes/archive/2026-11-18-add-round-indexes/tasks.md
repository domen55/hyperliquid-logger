## 1. Tests first

- [x] 1.1 Test: query plans for positions and spot of one round use the `(address, round_ms)` indexes
- [x] 1.2 Test: opening an old database (without the indexes) creates them and keeps the rows

## 2. Implementation

- [x] 2.1 Add the two `CREATE INDEX IF NOT EXISTS` statements to the schema in `logger.py`

## 3. Verification

- [x] 3.1 Full test suite green
- [x] 3.2 Real database migrates on restart
