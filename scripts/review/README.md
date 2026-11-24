# Round 1 reviewer (development only)

This is the isolated candidate / approval / workbook path. It does **not**
bulk-approve `data/programs/`, rewrite `site/data/catalog.json`, enable
nightly monitoring, or deploy GitHub Pages.

## Tooling choice

The reviewer is a **Python 3 standard-library loopback utility**:

- `http.server.ThreadingHTTPServer` bound to `127.0.0.1` only
- Excel import/export via `zipfile` + `xml.etree` (no openpyxl, no Node)
- CSRF token required on every state-changing POST
- Writes restricted to `data/review/` and `catalogs/` inside the isolated workspace
- Private review notes stay in `data/review/.review-notes.local.json` and are gitignored
- The process never copies `GITHUB_TOKEN` / `GH_TOKEN` into HTML, JSON, or workbooks

No extra web framework is used so the attack surface stays small and local.

## Commands

All commands require an isolated workspace. Do not point `--workspace` at the
production repository root if you might publish; tests use a disposable clone.

```bash
# Isolated workspace with a disposable local git remote
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 init --remote /tmp/dmv-r1.git

# Later monitor calls this deterministic staging API (fixtures only in Round 1)
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 stage material
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 stage fetch_failed
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 stage cancellation
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 stage first_party_cancellation

# Reviewer loopback
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 serve --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765/

# Same operations without the browser
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 export --out /tmp/review.xlsx
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 import --in /tmp/review.xlsx
python3 scripts/review_tool.py --workspace /tmp/dmv-r1 publish --today 2026-02-01 --out /tmp/dmv-r1/catalogs/catalog.json
```

Decision-saved (import) is not site-published (publish).

`fetch_failed`, `missing_page`, and `cancellation_report` are observations only. A first-party cancellation candidate requires `outcome=first_party_cancellation`, `source_authority=first_party`, at least one non-empty official link, and at least one non-empty excerpt. `source_authority=first_party` alone is not enough. Approval still sets `lifecycle_status=cancelled` and does not drop 2026-2027 membership.

Round 2 calls `stage_observation` in `scripts/review/stage.py` for every check. Unchanged pages and fetch failures stay observations. A supported fact change or an evidenced first-party cancellation becomes a normal candidate and then uses this same workbook. The monitor does not approve or publish. See `scripts/monitor/README.md`.

## Acceptance tests

```bash
python3 tests/round1/run_acceptance.py
```
