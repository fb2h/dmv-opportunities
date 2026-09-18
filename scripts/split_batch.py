"""Split a collector batch into one file per program under data/programs/.

Each program file carries its own sources and evidence so a single file is
self-contained and a git diff on it shows exactly what changed for that program.
Batch-level metadata (coverage tasks, identity resolution) goes to data/meta/.
Never edits the import; re-running is idempotent.
"""
import json, os, sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "data/imports/DMV_collection_batch_2026-09-08.json")
out_dir = os.path.join(root, "data/programs")
meta_dir = os.path.join(root, "data/meta")
os.makedirs(out_dir, exist_ok=True); os.makedirs(meta_dir, exist_ok=True)

d = json.load(open(src, encoding="utf-8"))
# Two collection lanes sometimes submitted the same pid (same program, different
# offerings). Same pid is an explicit identity claim by the collector, so the two
# are merged: offerings, sources and evidence are unioned by id; header fields come
# from the first; the merge is logged so a person can glance at it.
by_pid, merge_log = {}, []
for c in d["candidates"]:
    pid = c["pid"]
    if pid not in by_pid:
        by_pid[pid] = json.loads(json.dumps(c)); continue
    base = by_pid[pid]
    have = {o["oid"] for o in base["offerings"]}
    base["offerings"] += [o for o in c["offerings"] if o["oid"] not in have]
    have = {x["sid"] for x in base["sources"]}
    base["sources"] += [x for x in c["sources"] if x["sid"] not in have]
    seen = {(e["sid"], e["oid"], e["quote"]) for e in base["evidence"]}
    base["evidence"] += [e for e in c["evidence"] if (e["sid"], e["oid"], e["quote"]) not in seen]
    merge_log.append({"pid": pid, "kept_name": base["name"], "merged_name": c["name"],
                      "lanes": [base["lane"], c["lane"]], "offerings_now": [o["oid"] for o in base["offerings"]],
                      "note": "Same pid submitted by two lanes; offerings unioned. Check whether two 'standing' offerings describe the same thing."})

n = 0
for c in by_pid.values():
    rec = {
        "schema_version": d["schema_version"],
        "taxonomy_version": d["taxonomy_version"],
        "imported_from": {"batch_id": d["batch_id"], "submitted_at": d["submitted_at"], "collector_id": d["collector_id"]},
        **c,
    }
    with open(os.path.join(out_dir, f"{c['pid']}.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1, ensure_ascii=False); f.write("\n")
    n += 1
with open(os.path.join(meta_dir, "merge_log.json"), "w", encoding="utf-8") as f:
    json.dump(merge_log, f, indent=1, ensure_ascii=False); f.write("\n")

for k in ("coverage_tasks", "identity_resolution", "conflicts", "discovered_links"):
    with open(os.path.join(meta_dir, f"{k}.json"), "w", encoding="utf-8") as f:
        json.dump(d.get(k), f, indent=1, ensure_ascii=False); f.write("\n")

print(f"merged {len(merge_log)} same-pid pairs; wrote {n} program files to data/programs/ and 4 meta files to data/meta/")
