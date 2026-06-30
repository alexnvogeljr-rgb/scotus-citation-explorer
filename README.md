# The Supreme Court Citation Network

A large-scale visualization of how U.S. Supreme Court opinions cite one another:
**4,133 cases** connected by **55,136 citations**, laid out, clustered, and made
explorable. (Filtered down to the most-cited core from the full ~27,900-case set — see "About the data".)

---

## Open these first

| File | What it is |
|---|---|
| **index.html** | Public website entrypoint. This is the file static hosts serve at the project root. |
| **scotus_citation_explorer.html** | Self-contained interactive map, kept as a named copy of the same explorer. **Hover a case to see its real name and U.S. citation** (fetched live from CourtListener), click to open it there, trace its citations, cycle through citation web / doctrinal clusters / area groups layouts, filter by area of law, zoom, and search by CourtListener ID or case name. Needs internet for live case-name lookup and remote name search; everything else works offline. |
| **citation_galaxy.png** | Poster: the whole corpus as one connected web. The glowing core is the small set of canonical, heavily-cited precedents; the lone orange island is a single tightly-knit area of law. |
| **doctrinal_map.png** | Poster: the same cases split into their natural citation communities, each labeled by its dominant area of law. |
| **scotus_citation_network.gexf** | The full graph for [Gephi](https://gephi.org) (free). Positions, colors, sizes, and per-case metadata are baked in - open it and start exploring, or run your own ForceAtlas2. |
| **data/nodes.csv**, **data/edges.csv** | The raw graph. `nodes.csv` = one row per case (ID, year, area of law, times-cited, cites-made, community, x/y, CourtListener link). `edges.csv` = one row per citation (`citing_id -> cited_id`). |

---

## Preview and publish

This is a static website. No build step is required for the already-generated site.

```bash
python3 -m http.server 4173
```

Then open `http://localhost:4173/`.

To publish it publicly, deploy the project root as a static site:

- **Netlify:** drag the folder into Netlify Drop, or connect the repository. `netlify.toml` is already configured to publish the root folder.
- **Vercel:** import the repository as a static project. `vercel.json` is included for headers and clean URLs.
- **GitHub Pages:** push the folder to a repository, enable Pages from the main branch root, and keep `.nojekyll` in place.

The public URL should point at `index.html`; the explorer does not need a backend server.

### Bake in case names

The bundled graph IDs are CourtListener opinion IDs, but the included node table does
not contain case names. The website can load an optional static `case_names.json` file
before falling back to live CourtListener lookup.

```bash
export COURTLISTENER_TOKEN=your_token_here
python3 fetch_case_names.py --top 1000
```

After this, deploy `case_names.json` with the site. The command above starts with the
1,000 most-cited cases; omit `--top 1000` later to fill in the rest. Visitors will see
names from that static cache without spending CourtListener API requests on hover.

---

## Read this about the data (it matters)

**Provenance.** The citation graph comes from the [Free Law Project / CourtListener](https://www.courtlistener.com)
corpus, originally assembled (and joined to the [Supreme Court Database](http://scdb.wustl.edu/))
by the UNC **law-net** project. The underlying opinions are public domain.

**Coverage stops around 2016.** This snapshot runs roughly **1792-2016**. It is *not*
current. The last ~10 years of opinions are missing. The structure is complete enough
to be representative, but do not treat it as up-to-date.

**Names are fetched live, not baked in.** The underlying graph keys cases by their
CourtListener opinion ID. When you hover a node, the explorer queries CourtListener's
public search API and shows the real case name and U.S. citation (e.g. *Miranda v.
Arizona · 384 U.S. 436*), caching each result. This needs an internet connection; with
no connection it falls back to the CourtListener ID, and clicking still opens the case.
Names are looked up rather than embedded because no reliable offline ID-to-name
crosswalk exists for this graph's vintage — guessing would have mislabeled landmarks.

**Filtered to the most-cited core.** The explorer, posters, and Gephi file show the
**4,133** cases that survive a usability filter: everything from 2000 on, 1975–1999 cited
at least 5 times, and pre-1975 cited at least 50 times. This drops the ~23,750 rarely-cited
cases that turned the full map into an unreadable hairball. Node size scales with a case's
real citation count, so the canon (Miranda, Chevron, Erie, …) dwarfs the rest. The full,
unfiltered source is kept in `data/nodes_full.csv` and `data/edges_full.csv`.

**To get current (post-2016) data with names baked in**, run the refresh below — it
rebuilds straight from CourtListener on your machine.

---

## Refresh to named, present-day data

```bash
# 1. Free CourtListener account, then copy your token from
#    https://www.courtlistener.com/profile/api/
export COURTLISTENER_TOKEN=your_token_here

# 2. Dependencies for the rebuild
pip install python-igraph matplotlib networkx numpy

# 3. Pull current SCOTUS cases + citations (restartable; add --resume to continue)
python3 refresh_from_courtlistener.py

# 4. Regenerate every visual from the fresh, named data
python3 build_pipeline.py
```

After this, `nodes.csv` carries `case_name`, the posters label the top hubs by name,
and the explorer's search box finds cases by name.

You can also run `python3 build_pipeline.py` on its own at any time to regenerate all
outputs from whatever is in `data/nodes.csv` + `data/edges.csv`.

---

## How to read the visualizations

- **Node size = times cited** by later Supreme Court opinions. Big nodes are the
  precedents the Court leans on most - its working canon.
- **Color = area of law** (Supreme Court Database issue areas: Criminal Procedure,
  Civil Rights, First Amendment, Economic Activity, Judicial Power, etc.).
- **Communities** are found with Louvain modularity on the citation graph. They line up
  strikingly well with doctrine - cases cite within their field far more than across it.
- **Three layouts.** "Citation web" is a single force-directed layout (Fruchterman-Reingold)
  showing the real, fully-connected web. "Doctrinal clusters" lays out each community
  separately. "Area groups" compresses cases within each area of law and spreads the
  areas apart for easier scanning.

---

## Files

```
index.html                        public website entrypoint
scotus_citation_explorer.html     interactive map (named copy of the website)
citation_galaxy.png               poster - the connected citation web
doctrinal_map.png                 poster - communities by area of law
scotus_citation_network.gexf      graph for Gephi
build_pipeline.py                 rebuild all visuals and the website from data/{nodes,edges}.csv
refresh_from_courtlistener.py     pull current, named data from CourtListener's API
fetch_case_names.py               build static case_names.json for hover labels
app_template.html                 HTML/JS template used by build_pipeline.py
data/nodes.csv, data/edges.csv    the (filtered) raw graph
data/nodes_full.csv, edges_full.csv  the full unfiltered graph (~27,900 cases)
data/coords_web.csv, coords_clusters.csv   precomputed layouts
data/SCDB.csv                     Supreme Court Database (used to label issue areas on refresh)
```

## Credits

Citation data: Free Law Project (CourtListener), public domain. Case metadata:
[Supreme Court Database](http://scdb.wustl.edu/), Washington University. Graph assembly:
the UNC **law-net** project. Visualizations and pipeline generated for this project.
