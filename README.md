# kalshi_nba_props

NBA player-points ladder (Kalshi series `KXNBAPTS`) joined to ESPN per-quarter scoring,
for the 2026-27 season. Question under study: are the ladders mispriced at the end of
Q1/Q2/Q3 for high-usage scorers (minute projections off)?

## Data (`out/`)
- `ladder_by_quarter.csv` - one row per Kalshi market (player x strike). Columns:
  game/date/teams, `strike` (floor, e.g. 19.5 = "20+"), `result`, player's points per
  quarter (`q1_pts..q4_pts`, `ot_pts`, `thru_q1..thru_q3`, `final_pts`, `minutes`),
  and Kalshi yes bid/ask/mid/last-trade at: pregame (`pre_*`, bar ending 1 min before
  tip), end of each quarter (`qN_*` = bar covering the final-play wallclock;
  `qN_p2_*` = 2 min later, during the break, after repricing), and the last
  two-sided quote before the market closed (`final_live_*`). Prices in dollars (0-1).
- `player_games.csv` - one row per player-game: quarter points, minutes, pregame
  `pre_implied_mean`/`pre_implied_median` (linear-interpolated survival curve from the
  ladder mids, crude), and the ladder P(>=K) at pre / Q1 / Q2 / Q3 / Q4 for each strike.
- `unmatched.txt` - markets that could not be joined (and why).
- `in_boxscore=False` rows are players Kalshi listed pregame who were inactive (no ESPN
  box-score line); Kalshi settles those at a fair price.

## Raw (`data/`)
- `kalshi_candles/<ticker>.json.gz` - 1-min candlesticks for each market's whole life
  (yes bid/ask OHLC, trade OHLC, volume, OI). `kalshi_events/` - settled event list.
- `espn/sum_<gameid>.json.gz` - ESPN game summary (play-by-play + box score);
  `sb_<date>.json.gz` - daily scoreboards; `games_index.json`.

## Scripts
- `pull_espn.py START END` - scoreboards + summaries for a date range (no auth).
- `pull_kalshi_candles.py` - all settled `KXNBAPTS-26OCT*` markets; needs the
  Tennis-Model Kalshi client on this box (authenticated, fleet-paced). Set
  `NBA_EVENT_PREFIX` to extend (e.g. `KXNBAPTS-26NOV`).
- `build_dataset.py` - joins the two into `out/`.  `summarize.py` - coverage + calibration.

Times are UTC; `date_et` is the US/Eastern game date, which matches the Kalshi ticker date.
Quarter-end times come from ESPN play wallclocks, which lag the live feed by seconds.
