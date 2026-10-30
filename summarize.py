"""Coverage + quick calibration of end-of-quarter ladder mids vs settlement."""
import csv, collections, statistics as st
rows = list(csv.DictReader(open("out/ladder_by_quarter.csv")))
pg = list(csv.DictReader(open("out/player_games.csv")))
F = lambda x: float(x) if x not in ("", None) else None
print(f"markets {len(rows)}  player-games {len(pg)}  games {len({r['espn_game_id'] for r in rows})}  "
      f"dates {min(r['date_et'] for r in rows)}..{max(r['date_et'] for r in rows)}")
print("not in boxscore:", sum(r["in_boxscore"] == "False" for r in rows),
      " | pregame two-sided quote:", sum(F(r["pre_mid"]) is not None for r in rows),
      " | q1_p2 quote:", sum(F(r["q1_p2_mid"]) is not None for r in rows),
      " | q3_p2 quote:", sum(F(r["q3_p2_mid"]) is not None for r in rows))
print("result counts:", collections.Counter(r["result"] for r in rows))
proj = {(p["espn_game_id"], p["espn_athlete_id"]): F(p["pre_implied_mean"]) for p in pg}
def calib(col, label, filt=lambda r: True):
    b = collections.defaultdict(list)
    for r in rows:
        m = F(r[col])
        if m is None or r["result"] not in ("yes", "no") or r["in_boxscore"] != "True" or not filt(r): continue
        b[min(int(m * 10), 9)].append((m, 1.0 if r["result"] == "yes" else 0.0))
    print(f"\n{label}: bucket  n   mid   hit   hit-mid")
    for k in sorted(b):
        xs = b[k]; mm = st.mean(x for x, _ in xs); hh = st.mean(y for _, y in xs)
        print(f"  {k/10:.1f}-{(k+1)/10:.1f}  {len(xs):4d}  {mm:.3f}  {hh:.3f}  {hh-mm:+.3f}")
    allx = [x for xs in b.values() for x in xs]
    if allx: print(f"  all n={len(allx)} mean mid {st.mean(x for x,_ in allx):.3f} hit {st.mean(y for _,y in allx):.3f}")
for q in ("pre", "q1_p2", "q2_p2", "q3_p2"):
    calib(f"{q}_mid", f"{q} mid (all players)")
hi = lambda r: (proj.get((r["espn_game_id"], r["espn_athlete_id"])) or 0) >= 22
for q in ("pre", "q1_p2", "q2_p2", "q3_p2"):
    calib(f"{q}_mid", f"{q} mid (pregame implied mean >= 22)", hi)
