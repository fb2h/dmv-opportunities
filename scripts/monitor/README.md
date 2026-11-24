# Known-source monitor (Round 2)

The monitor answers one question: for an opportunity we already know about, what changed on its official source since the last check, and does a person need to review that change?

It does **not** publish the directory, approve a revision, or remove a listing. An approved 2026–2027 revision stays as it is until someone approves an exact replacement through the Round 1 workbook. Contract 2.4.2 is unchanged. This file is the operating note for the monitor.

Production stays frozen. There is no schedule, no Pages deploy, and no live monitoring in CI.

## What it monitors

Sources already recorded for a known program or offering:

- the program's official page
- the organization's official application page
- a known official PDF or another recorded first-party URL

Each source has a stable id. Checking it again updates the snapshot. It does not create a second source just because the page changed.

Historical 2025–2026 programs stay in the backend and are not shown as 2026–2027 offerings. Their official pages are still worth checking, because that same page may later announce a new cycle. A new cycle is a new offering. The monitor never rewrites the old offering's year.

## What it does not monitor

- Google, Bing, social media, newsletters, or directories
- pages that are not already on the source list
- links discovered while reading a page
- an organization's whole website
- brand-new programs that are not already in the review store

Known-source checks and new-program discovery are separate. This round does not build discovery.

## Layers

1. **Inventory.** The operator names the source id, program, offering, and URL. `--source` or `--all-listed` limits the run to that list.
2. **Fetch.** Record the source id, requested URL, final URL, time, HTTP status, content type, raw hash, ETag, and Last-Modified when the server sends them. The client sends a clear User-Agent, uses a short timeout, and retries only transient failures. It does not send credentials, disable TLS checks, or follow a redirect onto a host outside the source allowlist. A timeout, 403, TLS error, or JavaScript shell is a fetch failure. A 404 or 410 is a missing page. Neither one means the opportunity was cancelled.
3. **Normalize.** Keep two fingerprints: the raw bytes, and the reviewable text after scripts, styles, navigation, and footers are removed. A hash change by itself is not a fact change.
4. **Interpret.** Read only explicit statements (a named cycle, a full deadline, a pay rate, a grade range, a cancellation sentence). If the page disagrees with itself, the result is an ambiguous observation and no proposed fact.
5. **Stage.** Call Round 1 `stage_observation`. That is the only way a candidate is created. The monitor does not call the approval function.

## How a check is classified

| Result | What you see | What is written |
| --- | --- | --- |
| Unchanged | The meaningful text matches the last good check, and explicit facts match the approved offering. | A successful check and a snapshot. No candidate. |
| Formatting / non-material | The raw page changed (whitespace, markup, footer, navigation, or an unrelated paragraph) but no structured fact did. | An observation. No factual candidate. |
| Fetch failure | Timeout, connection error, 403, TLS error, empty shell, or a PDF with no text. | An observation. The approved revision stays. |
| Missing page | HTTP 404 or 410. | An observation on the report. Not a cancellation and not a removal. |
| Pending / ambiguous | The page changed and the monitor cannot safely turn that into one supported fact, or the redirect left the official host. | An observation with the snapshot. No invented fact. A redirect to another host is not used as evidence. |
| Next cycle | The official page explicitly announces a different cycle (`2026-2027 school year`, `Summer 2027`). A copyright year or "we usually run this" is not enough. | A new offering candidate. Only facts stated on the new page are filled in. Last year's dates, pay, grades, fees, and location are left unknown. The old offering is not edited. |
| Material change | A stated fact (deadline, pay, grades, fee, dates, delivery, location) differs from the approved revision and the page quotes the new value. | A candidate that points at the old value, the proposed value, the URL, the snapshot, and the excerpt. The approved revision is untouched until a person approves that exact candidate. |
| First-party cancellation | The page itself says the offering has been cancelled, and the check has a first-party source, an official URL, and that sentence as an excerpt. | A Round 1.2 cancellation candidate. It is not approved automatically. Anything weaker (a rumor, a third party, a missing link, a missing sentence, a failed fetch, a 404) is an observation only. |

Repeating the same check does not create another candidate. If a newer fact arrives while an older candidate is still open, the older candidate is left intact and marked superseded so its workbook row cannot be approved as if it were the newest evidence. The new candidate is a separate revision.

The first check does not mean "nothing changed." The page is still compared with the known offering, so a first look that already announces 2026–2027 still opens a next-cycle candidate.

## Where state lives

Nothing is written into `data/programs/` or `site/data/catalog.json`.

- Review store: the isolated workspace's `data/review/store.json` (observations, candidates, approved revisions).
- Check history: `--state-root` (`checks.json`, `last_report.txt`).
- Snapshots: `--snapshot-root` (default `<state-root>/snapshots`). One snapshot id per source and content hash. The same bytes are not stored twice. Each check still records its own retrieval time.

The CLI refuses a workspace or output directory inside this repository, so a run cannot land on the production checkout. Tests pass temporary directories.

## Run the fixture tests

```bash
python3 tests/round2/run_acceptance.py
```

The suite does not use the network. Round 1 stays at:

```bash
python3 tests/round1/run_acceptance.py
```

## Optional manual dry run

Use a disposable workspace. This does not touch production records.

```bash
WS=/tmp/dmv-r2-workspace
STATE=/tmp/dmv-r2-state
python3 scripts/monitor_tool.py \
  --workspace "$WS" \
  --state-root "$STATE" \
  --inventory testdata/round2/inventory.json \
  --fixtures testdata/round2/fixtures/manifest.json \
  --source river-official \
  --seed-fixtures \
  --dry-run
```

Drop `--dry-run` to write the isolated review store, snapshots, and a text report. Add `--source harbor-official` or repeat `--source` for a small allowlist. `--all-listed` checks only the inventory file.

`--live` is a manual allowlist fetch. Every URL must be repeated with `--allow-url`. It is not wired to GitHub Actions and it is not a crawl. Do not point `--workspace` at a checkout that contains the live catalog.

A candidate created this way is reviewed with the existing Round 1 tool (`export`, edit Decision, `import`). Approving the workbook approves the stored revision and its fingerprint. An edited fingerprint or a superseded row is rejected. The monitor has no separate approve command.

## Why a changed page is not automatically a changed fact

Footers, navigation, analytics, whitespace, and unrelated paragraphs change the raw hash without changing a directory fact. The monitor records those as observations. It opens a factual candidate only when it can show the field, the previous approved value, the proposed value, the official URL, the snapshot, and the sentence that supports the new value.
