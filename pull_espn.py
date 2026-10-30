"""Pull ESPN NBA scoreboards (one call per day) and the full game summary (play-by-play +
box score) for every completed game in the date range. Raw JSON saved under data/espn/."""
import gzip, json, os, sys, time, datetime as dt, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "espn")
SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"
SUM = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={id}"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def main(start, end):
    d0 = dt.date.fromisoformat(start); d1 = dt.date.fromisoformat(end)
    games = []
    d = d0
    while d <= d1:
        ds = d.strftime("%Y%m%d")
        path = os.path.join(OUT, f"sb_{ds}.json")
        if os.path.exists(path):
            sb = json.load(open(path))
        else:
            sb = get(SB.format(d=ds)); json.dump(sb, open(path, "w")); time.sleep(0.5)
        for e in sb.get("events", []):
            comp = e["competitions"][0]
            games.append({"id": e["id"], "date_utc": e["date"], "name": e["name"],
                          "status": e["status"]["type"]["name"],
                          "season_type": (e.get("season") or {}).get("type"),
                          "teams": [{"abbr": t["team"]["abbreviation"], "name": t["team"]["displayName"],
                                     "location": t["team"].get("location"), "homeAway": t["homeAway"],
                                     "score": t.get("score")} for t in comp["competitors"]]})
        d += dt.timedelta(days=1)
    json.dump(games, open(os.path.join(OUT, "games_index.json"), "w"), indent=1)
    fin = [g for g in games if g["status"] == "STATUS_FINAL"]
    print(f"{len(games)} games listed, {len(fin)} final", flush=True)
    for g in fin:
        path = os.path.join(OUT, f"sum_{g['id']}.json.gz")
        if os.path.exists(path) or os.path.exists(path[:-3]): continue
        try:
            s = get(SUM.format(id=g["id"]))
        except Exception as ex:
            print("FAIL", g["id"], g["name"], ex, flush=True); continue
        with gzip.open(path, "wt") as fh: json.dump(s, fh)
        print("ok", g["id"], g["date_utc"][:10], g["name"], len(s.get("plays", [])), "plays", flush=True)
        time.sleep(0.7)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
