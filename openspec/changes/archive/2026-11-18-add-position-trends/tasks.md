## 1. Tests first

- [x] 1.1 Test: trends pick the right reference rounds (16 min -> 15m, 130 min -> 2h, none for 1d)
- [x] 1.2 Test: too little history gives null; a gap older than 1.5 x window gives null
- [x] 1.3 Test: a coin missing in the reference round is `opened` with earlier size 0

## 2. Backend

- [x] 2.1 `q_positions` adds `trend` per position

## 3. Frontend

- [x] 3.1 Three trend columns and the metric selector in the positions table
- [x] 3.2 Cells: change, percentage, colour, "new", dash, tooltip

## 4. Verification

- [x] 4.1 Full test suite green
- [x] 4.2 Real data in the browser (15 min column filled, 2 h / 1 day dashes until history exists)
