"""Join Kalshi KXNBAPTS ladder price history with ESPN per-quarter player scoring.

Outputs (out/):
  ladder_by_quarter.csv   one row per market (player x strike): pregame and end-of-Q1/Q2/Q3/
                          Q4 yes bid/ask/mid, player's points by quarter, result.
  player_games.csv        one row per player-game: quarter points, minutes, pregame ladder
                          mids and a crude ladder-implied projection.
  unmatched.txt           Kalshi markets that could not be joined, with the reason.

Timestamps: ESPN play-by-play wallclocks (UTC). "end of Qn" = wallclock of the last play
of period n. Candles are 1-min bars keyed by end_period_ts; the bar used for a timestamp
is the last bar whose end <= t (the state as of t), and the +2min column is the bar whose
end <= t+120s (the quarter break, after the market has repriced the new score).
"""
import csv, glob, gzip, json, os, re, unicodedata, datetime as dt, collections, math
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data"); O = os.path.join(HERE, "out")
ET = ZoneInfo("America/New_York")
K2E = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"}
MON = {m: i for i, m in enumerate(["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"], 1)}

def iso(s): return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
def norm(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'\-]", "", n)
    toks = [t for t in n.split() if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(toks)
def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

# ---------------------------------------------------------------- ESPN
def load_espn():
    games = {}
    for p in glob.glob(os.path.join(D, "espn", "sum_*.json")) + glob.glob(os.path.join(D, "espn", "sum_*.json.gz")):
        s = json.load(gzip.open(p, "rt")) if p.endswith(".gz") else json.load(open(p))
        comp = s["header"]["competitions"][0]
        if comp["status"]["type"]["name"] != "STATUS_FINAL": continue
        gid = s["header"]["id"]
        date_et = iso(comp["date"]).astimezone(ET).date()
        teams = {}
        for c in comp["competitors"]:
            teams[c["team"]["abbreviation"]] = {"name": c["team"]["displayName"], "homeAway": c["homeAway"],
                                                 "score": f(c.get("score"))}
        plays = s.get("plays", [])
        if not plays: continue
        tip = iso(plays[0]["wallclock"]) if plays[0].get("wallclock") else iso(comp["date"])
        pend = {}
        for pl in plays:
            if pl.get("wallclock"): pend[pl["period"]["number"]] = iso(pl["wallclock"])
        pts = collections.defaultdict(collections.Counter)
        for pl in plays:
            if pl.get("scoringPlay") and pl.get("participants"):
                pts[pl["participants"][0]["athlete"]["id"]][pl["period"]["number"]] += pl.get("scoreValue", 0)
        roster = {}
        for t in s["boxscore"]["players"]:
            st = t["statistics"][0]; names = st["names"]
            for a in st["athletes"]:
                aid = a["athlete"]["id"]
                stats = a.get("stats") or []
                g = lambda k: stats[names.index(k)] if k in names and len(stats) > names.index(k) else None
                roster[aid] = {"name": a["athlete"]["displayName"], "norm": norm(a["athlete"]["displayName"]),
                               "team": t["team"]["abbreviation"], "min": g("MIN"), "box_pts": f(g("PTS")),
                               "starter": a.get("starter"), "dnp": a.get("didNotPlay"),
                               "q": dict(pts.get(aid, {}))}
        nper = max(pend)
        games[gid] = {"id": gid, "date_et": date_et, "teams": teams, "tip": tip, "pend": pend, "nper": nper,
                      "roster": roster, "name": s["header"]["competitions"][0].get("notes", [{}])[0].get("headline", ""),
                      "season_type": (s["header"].get("season") or {}).get("type")}
    return games

def espn_lookup(games):
    idx = {}
    for g in games.values():
        idx[(g["date_et"], frozenset(g["teams"]))] = g
    return idx

# ---------------------------------------------------------------- Kalshi
def bar_at(cands, t):
    """Last 1-min bar with end_period_ts <= t (unix). Returns dict or None."""
    ts = int(t.timestamp()) if isinstance(t, dt.datetime) else int(t)
    best = None
    for c in cands:
        if c["end_period_ts"] <= ts: best = c
        else: break
    return best

def quote(c):
    if not c: return (None, None, None, None, None)
    bid = f(c["yes_bid"].get("close_dollars")); ask = f(c["yes_ask"].get("close_dollars"))
    last = c.get("_last")
    if bid is None or ask is None or ask >= 1.0 and bid <= 0.0:
        mid = None
    else:
        mid = (bid + ask) / 2
    return (bid, ask, mid, last, f(c.get("volume_fp")))

def main():
    games = load_espn(); idx = espn_lookup(games)
    print(f"{len(games)} ESPN final games")
    evs = json.load(open(os.path.join(D, "kalshi_events", "kalshi_events_KXNBAPTS_settled.json")))
    evs = [e for e in evs if e["event_ticker"].startswith("KXNBAPTS-26OCT")]
    rows = []; unmatched = []; pg = {}
    for e in evs:
        tag = e["event_ticker"].split("-")[1]
        d = dt.date(2000 + int(tag[:2]), MON[tag[2:5]], int(tag[5:7]))
        ka, kb = tag[7:10], tag[10:13]
        ea, eb = K2E.get(ka, ka), K2E.get(kb, kb)
        g = idx.get((d, frozenset({ea, eb})))
        if not g:
            unmatched.append(f"{e['event_ticker']}: no ESPN game on {d} for {ea}/{eb}"); continue
        for m in e["markets"]:
            path = os.path.join(D, "kalshi_candles", m["ticker"] + ".json.gz")
            if not os.path.exists(path):
                unmatched.append(f"{m['ticker']}: candles not downloaded"); continue
            cands = json.load(gzip.open(path, "rt"))["candlesticks"]
            cands.sort(key=lambda c: c["end_period_ts"])
            lastpx = None
            for c in cands:
                px = f((c.get("price") or {}).get("close_dollars"))
                if px is not None: lastpx = px
                c["_last"] = lastpx
            pname = m["yes_sub_title"].split(":")[0].strip()
            kteam = m["ticker"].split("-")[2][:3]
            eteam = K2E.get(kteam, kteam)
            cand = [r for r in g["roster"].values() if r["norm"] == norm(pname)]
            if not cand:
                cand = [r for r in g["roster"].values() if r["norm"].split()[-1] == norm(pname).split()[-1]
                        and r["norm"][0] == norm(pname)[0]]
            if len(cand) > 1:
                unmatched.append(f"{m['ticker']}: player '{pname}' ambiguous -> {[r['name'] for r in cand]}"); continue
            if cand:
                r = cand[0]; aid = [k for k, v in g["roster"].items() if v is r][0]; inbox = True
                q = r["q"]; q1, q2, q3, q4 = (q.get(i, 0) for i in (1, 2, 3, 4))
                ot = sum(v for k, v in q.items() if k > 4)
            else:   # listed by Kalshi, absent from the ESPN box score: inactive / scratched
                r = {"team": eteam, "name": pname, "min": None, "box_pts": None, "starter": None, "dnp": True}
                aid = "kalshi:" + m["ticker"].split("-")[2]; inbox = False
                q1 = q2 = q3 = q4 = ot = None
            row = {"date_et": g["date_et"], "event": e["event_ticker"], "espn_game_id": g["id"],
                   "away": next(a for a, t in g["teams"].items() if t["homeAway"] == "away"),
                   "home": next(a for a, t in g["teams"].items() if t["homeAway"] == "home"),
                   "team": r["team"], "player": r["name"], "espn_athlete_id": aid, "in_boxscore": inbox,
                   "ticker": m["ticker"], "strike": m["floor_strike"], "result": m["result"],
                   "minutes": r["min"], "starter": r["starter"], "dnp": r["dnp"],
                   "q1_pts": q1, "q2_pts": q2, "q3_pts": q3, "q4_pts": q4, "ot_pts": ot,
                   "thru_q1": q1, "thru_q2": (q1 + q2) if inbox else None,
                   "thru_q3": (q1 + q2 + q3) if inbox else None, "final_pts": r["box_pts"],
                   "n_periods": g["nper"], "tip_utc": g["tip"].isoformat(),
                   "market_open_utc": m["open_time"], "market_close_utc": m["close_time"]}
            # pregame: bar ending at or before tip-60s
            b, a, mid, last, vol = quote(bar_at(cands, g["tip"] - dt.timedelta(seconds=60)))
            row.update(pre_bid=b, pre_ask=a, pre_mid=mid, pre_last=last)
            for n in (1, 2, 3, 4):
                t = g["pend"].get(n)
                row[f"q{n}_end_utc"] = t.isoformat() if t else None
                for lab, off in (("", 0), ("_p2", 120)):
                    b, a, mid, last, vol = quote(bar_at(cands, t + dt.timedelta(seconds=off))) if t else (None,)*5
                    row[f"q{n}{lab}_bid"] = b; row[f"q{n}{lab}_ask"] = a; row[f"q{n}{lab}_mid"] = mid; row[f"q{n}{lab}_last"] = last
            # last two-sided quote before the market closed at the final buzzer
            live = [c for c in cands if f(c["yes_bid"].get("close_dollars")) > 0 or f(c["yes_ask"].get("close_dollars")) < 1]
            if live:
                b, a, mid, last, vol = quote(live[-1])
                row.update(final_live_utc=dt.datetime.fromtimestamp(live[-1]["end_period_ts"], dt.timezone.utc).isoformat(),
                           final_live_bid=b, final_live_ask=a, final_live_mid=mid, final_live_last=last)
            else:
                row.update(final_live_utc=None, final_live_bid=None, final_live_ask=None, final_live_mid=None, final_live_last=None)
            # total volume over market life
            row["volume_total"] = sum(f(c.get("volume_fp")) or 0 for c in cands)
            rows.append(row)
            key = (g["id"], row["espn_athlete_id"])
            pg.setdefault(key, {k: row[k] for k in ("date_et", "event", "espn_game_id", "away", "home", "team", "player",
                                                     "espn_athlete_id", "in_boxscore", "minutes", "starter", "dnp", "q1_pts", "q2_pts",
                                                     "q3_pts", "q4_pts", "ot_pts", "final_pts", "n_periods")})
            pg[key].setdefault("ladder", {})[m["floor_strike"]] = {"pre": row["pre_mid"], "q1": row["q1_p2_mid"],
                                                                     "q2": row["q2_p2_mid"], "q3": row["q3_p2_mid"],
                                                                     "q4": row["q4_p2_mid"]}
    rows.sort(key=lambda r: (r["date_et"], r["event"], r["team"], r["player"], r["strike"]))
    cols = list(rows[0].keys())
    with open(os.path.join(O, "ladder_by_quarter.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({k: ("" if v is None else (round(v, 4) if isinstance(v, float) else v)) for k, v in r.items()})

    # per player-game with ladder-implied projection
    def implied(lad):
        """Crude E[pts] from survival mids: S(0)=1, linear between strikes, S(top+5)=0."""
        pts = sorted((k + 0.5, v) for k, v in lad.items() if v is not None)
        if len(pts) < 2: return None, None
        xs = [0.0] + [x for x, _ in pts] + [pts[-1][0] + 5]
        ys = [1.0] + [min(1, max(0, y)) for _, y in pts] + [0.0]
        ys = [max(ys[i:]) if False else ys[i] for i in range(len(ys))]
        ev = sum((xs[i + 1] - xs[i]) * (ys[i] + ys[i + 1]) / 2 for i in range(len(xs) - 1))
        med = None
        for i in range(len(xs) - 1):
            if ys[i] >= 0.5 >= ys[i + 1] and ys[i] != ys[i + 1]:
                med = xs[i] + (ys[i] - 0.5) / (ys[i] - ys[i + 1]) * (xs[i + 1] - xs[i]); break
        return round(ev, 2), (round(med, 2) if med is not None else None)
    prow = []
    strikes = sorted({s for p in pg.values() for s in p["ladder"]})
    for p in pg.values():
        lad = p.pop("ladder")
        p["pre_implied_mean"], p["pre_implied_median"] = implied({k: v["pre"] for k, v in lad.items()})
        for s in strikes:
            for ph in ("pre", "q1", "q2", "q3", "q4"):
                v = lad.get(s, {}).get(ph)
                p[f"{ph}_ge{int(s + 0.5)}"] = "" if v is None else round(v, 3)
        prow.append(p)
    prow.sort(key=lambda r: (r["date_et"], r["event"], r["team"], r["player"]))
    with open(os.path.join(O, "player_games.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(prow[0].keys())); w.writeheader()
        for r in prow: w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    open(os.path.join(O, "unmatched.txt"), "w").write("\n".join(unmatched))
    print(f"{len(rows)} market rows, {len(prow)} player-games, {len(unmatched)} unmatched")
    print(collections.Counter(u.split(':', 1)[1].split('->')[0].split(' for ')[0].strip()[:30] for u in unmatched).most_common(8))

if __name__ == "__main__":
    main()
