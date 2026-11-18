## Decisions

- **Computed on read, no new tables.** Each window needs one lookup of the reference round
  (`MAX(round_ms) <= target` on `account_snapshot`) and one read of that whole round from `position_snapshot`
  via the `(address, round_ms)` index: three extra indexed queries per request.
- **The API returns earlier values, the page computes deltas and percentages.** This lets the metric selector
  switch without another request.
- **Reference = nearest round at or before the target**, so the real age is `>= window`; `base_ms` is returned and
  shown in the tooltip. The 1.5 x window limit keeps a collection gap from presenting a stale number as a trend.
- **Colour by sign of the change**, not by good/bad: for a short, a negative size change means it grew.
