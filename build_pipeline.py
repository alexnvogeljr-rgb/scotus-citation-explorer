#!/usr/bin/env python3
"""
build_pipeline.py  -  Rebuild every SCOTUS citation-network artifact from a node/edge list.

Inputs (in ./data/):
    nodes.csv   columns: cl_opinion_id [, case_name, year, issue_area | issue_area_code, true_cited]
    edges.csv   columns: citing_id, cited_id      (a directed edge = "citing case -> cited case")

If a `true_cited` column is present it is used as the node-size metric (a case's real,
full-corpus citation count); otherwise in-degree within the supplied graph is used.

Outputs (in this folder):
    data/nodes.csv                  (rewritten with metrics + layout columns)
    data/coords_web.csv             (single connected force layout)
    data/coords_clusters.csv        (community-anchored layout)
    citation_galaxy.png             (poster: the connected citation web)
    doctrinal_map.png               (poster: communities, labelled by area of law)
    scotus_citation_network.gexf    (open in Gephi)
    scotus_citation_explorer.html   (self-contained interactive map)

Requires:  pip install python-igraph matplotlib networkx numpy
Run:       python3 build_pipeline.py
"""
import csv, os, math, json, random, sys
from collections import defaultdict, Counter
import numpy as np
import igraph as ig
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

random.seed(7)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# node-size curve: small cases stay tiny, the canon gets large (big visual delta)
def size_radius_px(v): return 0.7 + (max(0, v) ** 0.72) * 0.52   # for reference / parity with the HTML
CLUSTER_SPREAD = 24      # higher = doctrinal-cluster islands sit farther apart

IANAMES = ["Criminal Procedure","Civil Rights","First Amendment","Due Process","Privacy",
           "Economic Activity","Judicial Power","Federalism","Federal Taxation","Unions",
           "Attorneys","Interstate Relations","Private Action","Miscellaneous","Other/Unknown"]
PAL = {"Criminal Procedure":"#e15759","Civil Rights":"#f28e2b","First Amendment":"#edc948",
       "Due Process":"#b07aa1","Privacy":"#ff9da7","Economic Activity":"#4e79a7",
       "Judicial Power":"#59a14f","Federalism":"#76b7b2","Federal Taxation":"#9c755f",
       "Unions":"#af7aa1","Attorneys":"#86bcb6","Interstate Relations":"#d37295",
       "Private Action":"#9aa0a6","Miscellaneous":"#79706e","Other/Unknown":"#555b66"}
ISSUE = {1:"Criminal Procedure",2:"Civil Rights",3:"First Amendment",4:"Due Process",5:"Privacy",
         6:"Attorneys",7:"Unions",8:"Economic Activity",9:"Judicial Power",10:"Federalism",
         11:"Interstate Relations",12:"Federal Taxation",13:"Miscellaneous",14:"Private Action"}

def issue_of(r):
    if r.get("issue_area"): return r["issue_area"]
    c = r.get("issue_area_code", "")
    if str(c).strip() not in ("", "None"):
        try: return ISSUE.get(int(float(c)), "Other/Unknown")
        except Exception: pass
    return "Other/Unknown"

def log(*a): print(*a, flush=True)

# ---------------------------------------------------------------- load
log("Loading node/edge lists ...")
node_rows = list(csv.DictReader(open(os.path.join(DATA, "nodes.csv"))))
ids  = [r["cl_opinion_id"] for r in node_rows]
idx  = {v: i for i, v in enumerate(ids)}
name = {r["cl_opinion_id"]: (r.get("case_name", "") or "") for r in node_rows}
year = {r["cl_opinion_id"]: (r.get("year", "") or "") for r in node_rows}
iarea= {r["cl_opinion_id"]: issue_of(r) for r in node_rows}
def _ti(r):
    try: return int(r.get("true_cited") or r.get("times_cited") or 0)
    except Exception: return 0
truecited = {r["cl_opinion_id"]: _ti(r) for r in node_rows}
use_true = bool(node_rows) and (("true_cited" in node_rows[0]) or ("times_cited" in node_rows[0]))

edges = []
for e in csv.DictReader(open(os.path.join(DATA, "edges.csv"))):
    a, b = idx.get(e["citing_id"]), idx.get(e["cited_id"])
    if a is not None and b is not None and a != b:
        edges.append((a, b))
g = ig.Graph(n=len(ids), edges=edges, directed=True)
g.vs["name"] = ids
indeg, outdeg = g.indegree(), g.outdegree()
# size metric: true full-corpus citation count when available, else within-set in-degree
SZ = [ (truecited[ids[i]] if use_true else indeg[i]) for i in range(len(ids)) ]
log(f"  {g.vcount():,} nodes  {g.ecount():,} edges  (size metric: {'true_cited' if use_true else 'in-degree'})")

# ---------------------------------------------------------------- metrics / communities
giant = g.connected_components(mode="weak").giant()
ug = giant.copy(); ug.to_undirected(combine_edges="ignore")
comm = ug.community_multilevel()
giant.vs["comm"] = comm.membership
gcomm = {giant.vs[i]["name"]: comm.membership[i] for i in range(giant.vcount())}
log(f"  giant component {giant.vcount():,} nodes  -  {len(comm)} communities (modularity {ug.modularity(comm.membership):.3f})")

# ---------------------------------------------------------------- layout 1: connected web
log("Computing force layout (web) ...")
Lw = giant.layout_fruchterman_reingold(niter=800)
web = {giant.vs[i]["name"]: (Lw[i][0], Lw[i][1]) for i in range(giant.vcount())}

# ---------------------------------------------------------------- layout 2: community-anchored clusters
log("Computing community-anchored layout (clusters) ...")
members = defaultdict(list)
for i in range(giant.vcount()):
    members[giant.vs[i]["comm"]].append(i)
loc = {}
for c, mem in members.items():
    sub = giant.subgraph(mem)
    L = sub.layout_fruchterman_reingold(niter=300) if sub.vcount() >= 3 else [(random.uniform(-1,1), random.uniform(-1,1)) for _ in mem]
    A = np.array(L.coords if hasattr(L, "coords") else L, dtype=float)
    A -= A.mean(0); s = (np.sqrt((A**2).sum(1)).max() or 1.0); A /= s
    loc[c] = (mem, A * math.sqrt(len(mem)))
meta = giant.copy(); meta.contract_vertices(giant.vs["comm"], combine_attrs=None); meta.simplify(multiple=True, loops=True)
Cm = np.array(meta.layout_fruchterman_reingold(niter=3000).coords, dtype=float); Cm -= Cm.mean(0)
sc = (np.sqrt((Cm**2).sum(1)).max() or 1.0)
K = (max(math.sqrt(len(mem)) for mem in members.values()) * CLUSTER_SPREAD) / sc
clu = {}
for c, (mem, A) in loc.items():
    center = Cm[c] * K
    for k, n in enumerate(mem):
        clu[giant.vs[n]["name"]] = (center[0] + A[k][0], center[1] + A[k][1])

# ---------------------------------------------------------------- normalise + park non-giant nodes
def normalise(d):
    xs=[v[0] for v in d.values()]; ys=[v[1] for v in d.values()]
    mnx,mny=min(xs),min(ys); s=max(max(xs)-mnx, max(ys)-mny) or 1
    return {k:(((v[0]-mnx)/s)*1000, ((v[1]-mny)/s)*1000) for k,v in d.items()}
web, clu = normalise(web), normalise(clu)
park = [i for i in ids if i not in web]
for k, nid in enumerate(park):
    p = ((k % 100)/100*1000, 1060 + (k//100)*9)
    web[nid] = p; clu[nid] = p

# ---------------------------------------------------------------- rewrite nodes.csv + coord files
with open(os.path.join(DATA, "nodes.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["cl_opinion_id","case_name","year","issue_area","times_cited","cites_made",
                "community","in_giant","x","y","courtlistener_url"])
    for i, nid in enumerate(ids):
        w.writerow([nid, name[nid], year[nid], iarea[nid], SZ[i], outdeg[i],
                    gcomm.get(nid, ""), 1 if nid in gcomm else 0,
                    round(web[nid][0],2), round(web[nid][1],2),
                    f"https://www.courtlistener.com/opinion/{nid}/x/"])
for fn, d in [("coords_web.csv", web), ("coords_clusters.csv", clu)]:
    with open(os.path.join(DATA, fn), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["cl_opinion_id","x","y"])
        for nid in ids: w.writerow([nid, round(d[nid][0],2), round(d[nid][1],2)])
log("Wrote data/nodes.csv, coords_web.csv, coords_clusters.csv")

# ---------------------------------------------------------------- posters
order = [c for c,_ in Counter(iarea.values()).most_common() if c in PAL]
legend = lambda: [Line2D([0],[0],marker="o",color="none",markerfacecolor=PAL[c],markersize=9,label=c) for c in order]
# matplotlib scatter `s` is area; SZ**1.44 keeps radius ~ SZ**0.72 (matches the HTML curve)
def poster_s(k, base): return base + (SZ[k] ** 1.3) * 0.05

def galaxy():
    P = web
    X = np.array([P[i][0] for i in ids]); Y = np.array([P[i][1] for i in ids])
    C = [PAL.get(iarea[i],"#888") for i in ids]; S = [poster_s(k, 0.5) for k in range(len(ids))]
    segs = [(P[a],P[b]) for a,b in [(ids[u],ids[v]) for u,v in edges] if a in P and b in P]
    fig = plt.figure(figsize=(14,15), facecolor="#07070d"); ax = fig.add_axes([0,0.04,1,0.88]); ax.set_facecolor("#07070d")
    ax.add_collection(LineCollection(segs, colors=[(0.42,0.58,1,0.05)], linewidths=0.10))
    ax.scatter(X,Y,s=S,c=C,linewidths=0,alpha=0.92)
    top = sorted(range(len(ids)), key=lambda k: SZ[k], reverse=True)[:12]
    for rank,k in enumerate(top,1):
        nid=ids[k]; x,y=P[nid]
        ax.scatter([x],[y],s=SZ[k]*0.9+30,facecolors="none",edgecolors="white",linewidths=0.8,alpha=0.9)
        lbl = name[nid] if name[nid] else f"{year[nid]} · {iarea[nid]}"
        ax.annotate(f"#{rank}  {lbl} · {SZ[k]} cites",(x,y),textcoords="offset points",xytext=(6,6),fontsize=6.5,color="white",alpha=0.85)
    ax.set_axis_off(); ax.set_aspect("equal")
    fig.text(0.5,0.965,"The Supreme Court Citation Galaxy",ha="center",color="white",fontsize=23,weight="bold")
    fig.text(0.5,0.935,f"{len(ids):,} opinions linked by {len(edges):,} citations - the bright core is the most-cited canon",ha="center",color="#9aa7c7",fontsize=11)
    ax.legend(handles=legend(),loc="lower center",bbox_to_anchor=(0.5,-0.055),ncol=5,frameon=False,fontsize=8,labelcolor="white",handletextpad=0.3,columnspacing=1.1)
    plt.savefig(os.path.join(HERE,"citation_galaxy.png"),dpi=200,facecolor="#07070d"); plt.close()

def doctrinal():
    P = clu
    byc = defaultdict(list)
    for nid in ids:
        if gcomm.get(nid,"")!="" : byc[gcomm[nid]].append(nid)
    X = np.array([P[i][0] for i in ids]); Y = np.array([P[i][1] for i in ids])
    C = [PAL.get(iarea[i],"#888") for i in ids]; S = [poster_s(k, 0.5) for k in range(len(ids))]
    fig = plt.figure(figsize=(14,15), facecolor="#0b0d12"); ax = fig.add_axes([0,0.04,1,0.88]); ax.set_facecolor("#0b0d12")
    ax.scatter(X,Y,s=S,c=C,linewidths=0,alpha=0.85)
    for c, mem in byc.items():
        if len(mem) < 60: continue
        cx = np.mean([P[i][0] for i in mem]); cy = np.max([P[i][1] for i in mem])
        dom = Counter([iarea[i] for i in mem]).most_common(1)[0][0]
        ax.annotate(f"{dom} · {len(mem):,}",(cx,cy),ha="center",va="bottom",fontsize=8.5,color="white",weight="bold",
                    textcoords="offset points",xytext=(0,7),
                    bbox=dict(boxstyle="round,pad=0.25",fc="#0b0d12",ec=PAL.get(dom,"#888"),lw=0.8,alpha=0.85))
    ax.set_axis_off(); ax.set_aspect("equal")
    fig.text(0.5,0.965,"The Supreme Court, Mapped by Doctrine",ha="center",color="white",fontsize=23,weight="bold")
    fig.text(0.5,0.935,f"The same {len(ids):,} opinions, split into {len(byc)} natural citation communities",ha="center",color="#9aa7c7",fontsize=11)
    ax.legend(handles=legend(),loc="lower center",bbox_to_anchor=(0.5,-0.055),ncol=5,frameon=False,fontsize=8,labelcolor="white",handletextpad=0.3,columnspacing=1.1)
    plt.savefig(os.path.join(HERE,"doctrinal_map.png"),dpi=200,facecolor="#0b0d12"); plt.close()

log("Rendering posters ...")
galaxy(); doctrinal()

# ---------------------------------------------------------------- GEXF for Gephi
try:
    import networkx as nx
    hx = lambda h:(int(h[1:3],16),int(h[3:5],16),int(h[5:7],16))
    G = nx.DiGraph()
    for k, nid in enumerate(ids):
        x,y = web[nid]; r,gg,b = hx(PAL.get(iarea[nid],"#888"))
        G.add_node(nid, label=name[nid], year=str(year[nid]), issue_area=iarea[nid],
                   times_cited=SZ[k], cites_made=outdeg[k], community=str(gcomm.get(nid,"")),
                   courtlistener_url=f"https://www.courtlistener.com/opinion/{nid}/x/",
                   viz={"position":{"x":x*10,"y":y*10,"z":0.0},"size":1.0+SZ[k]**0.72,"color":{"r":r,"g":gg,"b":b,"a":1.0}})
    for u,v in edges: G.add_edge(ids[u], ids[v])
    nx.write_gexf(G, os.path.join(HERE,"scotus_citation_network.gexf"))
    log("Wrote scotus_citation_network.gexf")
except Exception as e:
    log("GEXF skipped:", e)

# ---------------------------------------------------------------- interactive HTML
tpl_path = os.path.join(HERE, "app_template.html")
if os.path.exists(tpl_path):
    iaidx = {n:i for i,n in enumerate(IANAMES)}
    d = dict(IDS=ids, NAME=[name[i] for i in ids],
             WX=[round(web[i][0],1) for i in ids], WY=[round(web[i][1],1) for i in ids],
             CX=[round(clu[i][0],1) for i in ids], CY=[round(clu[i][1],1) for i in ids],
             COM=[gcomm.get(i, -1) for i in ids],
             IA=[iaidx.get(iarea[i],14) for i in ids],
             YR=[int(year[i]) if str(year[i]).strip().isdigit() else 0 for i in ids],
             DEG=[SZ[k] for k in range(len(ids))],
             EU=[u for u,v in edges], EV=[v for u,v in edges],
             IANAMES=IANAMES, IACOLORS=[PAL[n] for n in IANAMES])
    html = open(tpl_path).read().replace("/*__DATA__*/", "window.DATA="+json.dumps(d,separators=(",",":"))+";")
    for out_name in ("scotus_citation_explorer.html", "index.html"):
        open(os.path.join(HERE, out_name), "w").write(html)
    log("Wrote scotus_citation_explorer.html and index.html")
else:
    log("app_template.html not found - HTML skipped")

log("\nDONE. Open index.html in a browser, or the .gexf in Gephi.")
