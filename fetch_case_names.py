#!/usr/bin/env python3
"""
Fetch case-name metadata for the existing explorer IDs and write case_names.json.

Set COURTLISTENER_TOKEN first. The generated JSON is static and safe to deploy;
the token is used only while building the cache and is never shipped to visitors.
"""
import csv
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser(description="Build a static CourtListener case-name cache for the explorer.")
parser.add_argument("--top", type=int, default=0, help="Fetch only the top N cases by times_cited. Default: all cases.")
parser.add_argument("--out", default="case_names.json", help="Output JSON path. Default: case_names.json")
parser.add_argument("--max-wait", type=int, default=180, help="Exit and save progress if CourtListener asks us to wait longer than this many seconds. Default: 180.")
args = parser.parse_args()

HERE = os.path.dirname(os.path.abspath(__file__))
NODES = os.path.join(HERE, "data", "nodes.csv")
OUT = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
BASE = "https://www.courtlistener.com/api/rest/v4/search/?type=o&q="

def cited_count(row):
    try:
        return int(row.get("times_cited") or 0)
    except ValueError:
        return 0

rows = list(csv.DictReader(open(NODES, newline="")))
rows.sort(key=cited_count, reverse=True)
if args.top:
    rows = rows[:args.top]
ids = [r["cl_opinion_id"] for r in rows]

TOKEN = os.environ.get("COURTLISTENER_TOKEN", "").strip()
if not TOKEN:
    print("ERROR: Set COURTLISTENER_TOKEN first.", file=sys.stderr)
    print(f"Ready to fetch {len(ids):,} IDs. Example: COURTLISTENER_TOKEN=... python3 fetch_case_names.py --top {args.top or len(ids)}", file=sys.stderr)
    sys.exit(1)

cache = {}
if os.path.exists(OUT):
    cache = json.load(open(OUT))

class LongRateLimit(Exception):
    def __init__(self, wait):
        super().__init__(f"rate-limited for {wait}s")
        self.wait = wait

def get_json(url):
    for attempt in range(8):
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Authorization": "Token " + TOKEN,
            "User-Agent": "scotus-citation-explorer-name-cache/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                wait = int(e.headers.get("Retry-After", 0)) or min(90, 2 ** attempt + 3)
                if e.code == 429 and wait > args.max_wait:
                    raise LongRateLimit(wait)
                print(f"HTTP {e.code}; waiting {wait}s")
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            time.sleep(min(90, 2 ** attempt + 3))
    raise RuntimeError("too many retries")

def complete_record(rec):
    return isinstance(rec, dict) and bool(rec.get("name")) and bool(rec.get("url"))

pending = [i for i in ids if not complete_record(cache.get(i))]
scope = f"top {args.top:,}" if args.top else "all"
print(f"{len(ids):,} target IDs ({scope}); {len(cache):,} cached total; {len(pending):,} pending")

for n, opinion_id in enumerate(pending, 1):
    q = urllib.parse.quote("id:" + opinion_id)
    try:
        data = get_json(BASE + q)
    except LongRateLimit as e:
        json.dump(cache, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
        print(f"Rate-limited for {e.wait:,}s. Saved {len(cache):,} names to {OUT}.")
        print("Run the same command later to resume from this point.")
        sys.exit(75)
    res = (data.get("results") or [None])[0]
    if res:
        citations = res.get("citation") or res.get("citations") or []
        us_cite = next((c for c in citations if "U.S." in c), "")
        url = res.get("absolute_url") or ""
        if url.startswith("/"):
            url = "https://www.courtlistener.com" + url
        cache[opinion_id] = {
            "name": res.get("caseName") or res.get("case_name") or "",
            "citation": us_cite,
            "url": url,
        }
    else:
        cache[opinion_id] = {"name": "", "citation": "", "url": ""}

    if n % 25 == 0 or n == len(pending):
        json.dump(cache, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
        print(f"wrote {len(cache):,}/{len(ids):,}")
    time.sleep(0.1)

json.dump(cache, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
print(f"Done: {OUT}")
