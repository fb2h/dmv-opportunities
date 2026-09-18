# dmv-opportunities

A directory of work opportunities — paid or unpaid — for high school students in DC, Maryland and Virginia: internships, volunteer positions, paid jobs, apprenticeships, research, job shadowing and counselor roles. Every published fact is quoted from the hosting organization's own page. Nothing is guessed.

**Live site:** https://fb2h.github.io/dmv-opportunities/ (GitHub Pages, published by the workflow below).

## How it is organized

```
CONTRACT.md                 The Data Schema and Contract — the governing specification. It wins over everything else here.
data/programs/<pid>.json    The master database: one file per program, with its offerings, sources and verbatim evidence.
data/imports/               Collector batches exactly as received. Never edited.
data/meta/                  Generated reports: gate_report.json, autocheck_report.json, merge_log.json, coverage_tasks.json
scripts/split_batch.py      Import a collector batch into data/programs/ (merges same-pid submissions, logs the merge).
scripts/autocheck.py        Invariant checks: dates must appear in a quoted source, no pattern-derived years, evidence present, enums valid, links alive.
scripts/build.py            The publication gate (Section 7.1) and the transformation to the public catalog (Section 8.1).
site/                       The website: static HTML + JS, no build tools. Reads site/data/catalog.json and site/data/zips.json.
.github/workflows/site.yml  On every push and nightly: check → build → publish to GitHub Pages; open an issue when checks fail.
```

## Working locally

```bash
pip install -r requirements.txt
python scripts/split_batch.py data/imports/<batch>.json   # only when a new collector batch arrives
python scripts/autocheck.py                                 # add --links to check every source URL (needs open internet)
python scripts/build.py                                     # writes site/data/catalog.json
cd site && python -m http.server 8000                       # open http://localhost:8000
```

`build.py` publishes an offering only when the contract's gate passes: in scope, current cycle announced with evidence, cycle not ended, first-party source present. Its decisions and reasons are in `data/meta/gate_report.json`; the `disagreements_with_collector_flag` list is where a person should look first.

## Rules in one paragraph

Facts come only from the hosting organization's own page, PDF or notice, quoted verbatim. A recurring pattern ("applications usually open November 1") is recorded as a pattern, never as this year's date. Unknown is `null` with an issue recorded. Past cycles are never deleted — they predict the next cycle and drive the refresh schedule — but they are never displayed as if current. Splitting into offerings follows the contract; the frontend shows one card per program. Where the contract is silent, prefer showing more results; where it is explicit, the rule governs.

## Reporting a problem

Use *Report a problem* on any listing, or open an issue here. Please include the official link that shows the correct information.
