#!/usr/bin/env python3
"""
refresh_from_courtlistener.py
=============================
Rebuild the SCOTUS citation graph from CourtListener's LIVE data so you get
(a) authoritative case NAMES and (b) coverage all the way to the present day.

WHY THIS RUNS ON *YOUR* MACHINE
    The assistant that generated this project is sandboxed and cannot reach
    courtlistener.com. Your computer can. So this fetch step is yours to run.

WHAT IT DOES
    1. Pages through every U.S. Supreme Court opinion cluster (court = "scotus")
       to collect case name, decision year, and the SCDB id.
    2. Pages through every SCOTUS opinion to read its `opinions_cited` list and
       builds the case-to-case citation edges (kept only when *both* ends are SCOTUS).
    3. Optionally maps each case's SCDB id -> issue area using data/SCDB.csv.
    4. Writes data/nodes.csv and data/edges.csv (overwriting the bundled ~2016 set).
    5. Tells you to run:  python3 build_pipeline.py   to regenerate all visuals.

SETUP
    1. Make a free account at https://www.courtlistener.com/  then copy your API
       token from https://www.courtlistener.com/profile/api/  (or "Profile -> API").
    2. export COURTLISTENER_TOKEN=xxxxxxxxxxxxxxxxxxxx
    3. pip install python-igraph matplotlib networkx numpy      (for build_pipeline.py)
    4. python3 refresh_from_courtlistener.py        # add --resume to continue a stopped run

NOTES
    * This is a big crawl (tens of thousands of records). It can take a while and
      is restartable: it checkpoints to data/_raw_clusters.jsonl and
      data/_raw_citations.jsonl. Re-run with --resume to pick up where it left off.
    * The CourtListener v4 schema occasionally changes. If a filter name errors,
      read the message - the relevant knobs are CLUSTER_URL / OPINION_URL below.
"""
import os, sys, json, time, urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data"); os.makedirs(DATA, exist_ok=True)
TOKEN = os.environ.get("COURTLISTENER_TOKEN", "").strip()
RESUME = "--resume" in sys.argv

BASE = "https://www.courtlistener.com/api/rest/v4"
# All SCOTUS opinion clusters (cases), with just the fields we need:
CLUSTER_URL = BASE + "/clusters/?docket__court=scotus&page_size=100&fields=id,case_name,date_filed,scdb_id,sub_opinions"
# All SCOTUS opinions, with the list of opinions each one cites:
OPINION_URL = BASE + "/opinions/?cluster__docket__court=scotus&page_size=100&fields=id,cluster,opinions_cited"

def die(msg): print("ERROR:", msg); sys.exit(1)
if not TOKEN:
    die("Set COURTLISTENER_TOKEN first (see SETUP at top of this file).")

def tail_id(url):
    """ '.../opinions/12345/' -> '12345' """
    if not url: return None
    return urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]

def get(url):
    """GET with auth + retry/backoff on rate limits and transient errors."""
    for attempt in range(8):
        req = urllib.request.Request(url, headers={"Authorization": "Token " + TOKEN,
                                                   "User-Agent": "scotus-citation-refresh/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                wait = int(e.headers.get("Retry-After", 0)) or min(60, 2 ** attempt + 3)
                print(f"  HTTP {e.code} - backing off {wait}s ..."); time.sleep(wait); continue
            if e.code in (401, 403): die(f"HTTP {e.code}: check your API token / permissions.")
            die(f"HTTP {e.code} on {url}\n{e.read().decode()[:400]}")
        except (urllib.error.URLError, TimeoutError) as e:
            wait = min(60, 2 ** attempt + 3); print(f"  network error ({e}); retry in {wait}s"); time.sleep(wait)
    die("Too many retries.")

def crawl(url, checkpoint, extract):
    """Follow cursor pagination, append extracted rows to a jsonl checkpoint."""
    done = 0
    if RESUME and os.path.exists(checkpoint):
        done = sum(1 for _ in open(checkpoint)); print(f"  resume: {done:,} rows already in {os.path.basename(checkpoint)}")
    out = open(checkpoint, "a")
    page = 0
    while url:
        data = get(url); page += 1
        rows = data.get("results", [])
        # crude resume: skip pages we already have
        if done and page * 100 <= done:
            url = data.get("next"); continue
        for row in rows:
            out.write(json.dumps(extract(row)) + "\n")
        out.flush()
        if page % 10 == 0: print(f"  page {page} ... (+{len(rows)})")
        url = data.get("next")
        time.sleep(0.2)
    out.close()

# ---- 1. clusters (cases) -----------------------------------------------------
print("Fetching SCOTUS cases (clusters) ...")
cl_ckpt = os.path.join(DATA, "_raw_clusters.jsonl")
crawl(CLUSTER_URL, cl_ckpt, lambda c: {
    "id": str(c["id"]),
    "case_name": c.get("case_name", ""),
    "year": (c.get("date_filed") or "")[:4],
    "scdb_id": c.get("scdb_id", "") or "",
    "ops": [tail_id(u) for u in (c.get("sub_opinions") or [])],
})

clusters, op2cluster = {}, {}
for line in open(cl_ckpt):
    c = json.loads(line); clusters[c["id"]] = c
    for op in c["ops"]:
        if op: op2cluster[op] = c["id"]
print(f"  {len(clusters):,} cases, {len(op2cluster):,} opinions mapped")

# ---- 2. citation edges -------------------------------------------------------
print("Fetching SCOTUS opinions + citations ...")
ci_ckpt = os.path.join(DATA, "_raw_citations.jsonl")
crawl(OPINION_URL, ci_ckpt, lambda o: {
    "cluster": tail_id(o.get("cluster")),
    "cited": [tail_id(u) for u in (o.get("opinions_cited") or [])],
})

edges = set()
for line in open(ci_ckpt):
    o = json.loads(line); src = o["cluster"]
    if src not in clusters: continue
    for cop in o["cited"]:
        dstc = op2cluster.get(cop)
        if dstc and dstc != src: edges.add((src, dstc))
print(f"  {len(edges):,} SCOTUS->SCOTUS citation edges")

# ---- 3. issue area from SCDB (optional) --------------------------------------
scdb_issue = {}
scdb_path = os.path.join(DATA, "SCDB.csv")
if os.path.exists(scdb_path):
    import csv
    for r in csv.DictReader(open(scdb_path, encoding="latin-1")):
        if r.get("caseId") and r.get("issueArea"):
            scdb_issue[r["caseId"]] = r["issueArea"]
    print(f"  SCDB issue areas available for {len(scdb_issue):,} cases")

# ---- 4. write nodes.csv + edges.csv -----------------------------------------
import csv
with open(os.path.join(DATA, "nodes.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["cl_opinion_id", "case_name", "year", "issue_area_code"])
    for cid, c in clusters.items():
        w.writerow([cid, c["case_name"], c["year"], scdb_issue.get(c["scdb_id"], "")])
with open(os.path.join(DATA, "edges.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["citing_id", "cited_id"])
    for a, b in edges: w.writerow([a, b])

print(f"\nWrote data/nodes.csv ({len(clusters):,} cases) and data/edges.csv ({len(edges):,} edges).")
print("Now run:  python3 build_pipeline.py   to regenerate the named, current visualizations.")
