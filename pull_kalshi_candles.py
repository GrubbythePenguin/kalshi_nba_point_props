"""Pull 1-min candlesticks for every settled KXNBAPTS (NBA player points ladder) market.

Reuses Tennis-Model's authenticated, fleet-paced Kalshi Feed. One GET per market covers
its whole life (open_time .. close_time, ~1440 candles). Output: one gzipped JSON per
market in data/kalshi_candles/<ticker>.json.gz; skips tickers already on disk.
"""
import gzip, json, os, sys, time, datetime as dt
sys.path.insert(0, "/Users/bradleyguan/Documents/Coding/Tennis-Model")
import kalshi_tennis as kt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "kalshi_candles")
RPS = float(os.environ.get("NBA_RPS", "3.0"))
PREFIX = os.environ.get("NBA_EVENT_PREFIX", "KXNBAPTS-26OCT")   # this season only

def iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

def main():
    f = kt.Feed(rps=RPS, verbose=True)
    # refresh the settled event list so late-settling games are included
    evs = []; cursor = None
    while True:
        p = {"series_ticker": "KXNBAPTS", "status": "settled", "limit": 200,
             "with_nested_markets": "true"}
        if cursor: p["cursor"] = cursor
        r = f.get("/events", p)
        if not r: print("events fetch failed", flush=True); break
        e = r.get("events", []); evs += e; cursor = r.get("cursor")
        if not cursor or not e: break
    json.dump(evs, open(os.path.join(HERE, "data", "kalshi_events",
                                     "kalshi_events_KXNBAPTS_settled.json"), "w"))
    mkts = [m for e in evs if e["event_ticker"].startswith(PREFIX) for m in e.get("markets", [])]
    print(f"{len(evs)} settled events, {len(mkts)} markets under {PREFIX}", flush=True)
    todo = [m for m in mkts if not os.path.exists(os.path.join(OUT, m["ticker"] + ".json.gz"))]
    print(f"{len(todo)} to fetch", flush=True)
    t0 = time.time(); n_ok = n_bad = 0
    for i, m in enumerate(todo):
        st = int(iso(m["open_time"]).timestamp()) - 60
        en = int(iso(m["close_time"]).timestamp()) + 300
        # Kalshi caps one request at 5000 candles; opening-night markets opened 4 days early.
        allc = []; ok = True; a = st
        while a < en:
            b = min(en, a + 4800 * 60)
            c = f.get(f"/series/KXNBAPTS/markets/{m['ticker']}/candlesticks",
                      {"start_ts": a, "end_ts": b, "period_interval": 1})
            if c is None: ok = False; break
            allc += c.get("candlesticks", []); a = b
        if not ok:
            n_bad += 1
            print(f"FAIL {m['ticker']}", flush=True)
            continue
        rec = {"market": m, "candlesticks": allc}
        with gzip.open(os.path.join(OUT, m["ticker"] + ".json.gz"), "wt") as fh:
            json.dump(rec, fh)
        n_ok += 1
        if i % 100 == 0:
            el = time.time() - t0
            print(f"[{i}/{len(todo)}] ok={n_ok} bad={n_bad} 429s={f.n_429} "
                  f"{el:.0f}s elapsed, eta {(len(todo)-i)/max(i,1)*el/60:.1f} min", flush=True)
    print(f"done ok={n_ok} bad={n_bad} gets={f.n_get} 429s={f.n_429}", flush=True)

if __name__ == "__main__":
    main()
