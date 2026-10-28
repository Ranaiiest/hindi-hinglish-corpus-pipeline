import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ORDER = ["lang", "filter", "eval_holdout", "exact_dedup", "near_dedup", "contamination"]


def load(out):
    out = Path(out)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(out / "ledger.csv", encoding="utf-8")))
    return out, m, rows


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if Path(p).exists() else []


def sources(out, m, rows):
    print("\n== 1. SOURCES (name | declared license | url | docs in | docs kept | raw bytes)")
    for s in m["sources"]:
        d = s["declared"]
        print(f"- {d.get('name', s['source_dir'])} | {d.get('license', 'FILL')} | {d.get('url', 'FILL')} | "
              f"in={s['docs_in']} kept={s['docs_kept']} | {s['raw_bytes']/1e6:.1f} MB raw | downloaded {d.get('download_date', 'FILL')}")


def funnel(out, m, rows):
    print("\n== 2. FUNNEL")
    total = len(rows)
    by = Counter((r["stage"], r["lang"] or "unknown") for r in rows if r["status"] == "dropped")
    drop_stage = Counter(r["stage"] for r in rows if r["status"] == "dropped")
    after_read = total - drop_stage["read"]
    after_norm = after_read - drop_stage["normalize"]
    print(f"input docs: {total}\nafter read (malformed skipped: {drop_stage['read']}): {after_read}\nafter normalize: {after_norm}")
    labelled = Counter(r["lang"] for r in rows if r["lang"])
    langs = sorted(labelled)
    print("\nper-language, after language labelling (labels: " + ", ".join(f"{l}={labelled[l]}" for l in langs) + ")")
    print("stage".ljust(16) + "".join(l.rjust(10) for l in langs) + "total".rjust(10))
    cur = dict(labelled)
    print("labelled".ljust(16) + "".join(str(cur[l]).rjust(10) for l in langs) + str(sum(cur.values())).rjust(10))
    for st in ORDER:
        for l in langs:
            cur[l] -= by.get((st, l), 0)
        print(("after " + st).ljust(16) + "".join(str(cur[l]).rjust(10) for l in langs) + str(sum(cur.values())).rjust(10))
    print("\ndrop reasons:")
    rs = Counter((r["stage"], r["reason"].split("(")[0]) for r in rows if r["status"] == "dropped")
    for (st, rsn), v in sorted(rs.items(), key=lambda x: -x[1]):
        print(f"  {st:14s} {rsn:28s} {v}")


def near(out, m, rows):
    d = m["config"]["dedup"]
    thr = d["threshold"]
    pairs = jl(out / "diagnostics" / "near_dup_pairs.jsonl")
    print(f"\n== 3. NEAR-DUPLICATES  method: word {d['shingle_words']}-shingle MinHash ({d['num_perm']} perms), "
          f"LSH {d['bands']}x{d['rows']}, est-Jaccard threshold {thr}; pairs logged from {d['log_floor']}")
    print(f"pairs logged: {len(pairs)}  (duplicate={sum(p['decision']=='duplicate' for p in pairs)}, distinct={sum(p['decision']=='distinct' for p in pairs)})")
    close = sorted(pairs, key=lambda p: abs(p["sim"] - thr))[:3]
    print("three pairs closest to the threshold (write your call on each):")
    for p in close:
        print(f"\n  sim={p['sim']}  decision={p['decision']}\n   A[{p['a']}]: {p['a_text']}\n   B[{p['b']}]: {p['b_text']}")


def filters(out, m, rows):
    print("\n== 4. FILTERS  (look for legit text that was dropped: write down 3, or argue there are none)")
    by = defaultdict(list)
    for s in jl(out / "diagnostics" / "filter_drop_samples.jsonl"):
        by[(s["stage"], s["reason"])].append(s)
    for k, v in sorted(by.items()):
        print(f"\n-- {k[0]}/{k[1]}: showing 6 of the sampled drops")
        for s in v[:6]:
            print(f"   [{s['id']}] ({s['lang']}) {s['text'][:160]!r}")


def contam(out, m, rows):
    print("\n== 5. CONTAMINATION")
    cr = jl(out / "contamination.jsonl")
    ev = jl(out / "eval.jsonl")
    print(f"eval items: {len(ev)}  affected: {len(cr)}  training docs removed: {sum(len(r['train_ids']) for r in cr)}")
    print("by method (strongest per eval item):", dict(Counter(r['method'] for r in cr)))
    rej = jl(out / "diagnostics" / "contamination_rejected.jsonl")
    print(f"rejected candidates logged: {len(rej)}  (pick one and explain why it is NOT a leak)")
    for r in sorted(rej, key=lambda r: -r["score"])[:3]:
        print(f"\n  score={r['score']} method={r['method']}\n   eval : {r['eval_text']}\n   train: {r['train_text']}")


def pii(out, m, rows):
    print("\n== PII / other counters")
    for k, v in sorted(m["counts"]["stage_stats"].get("s3", {}).items()):
        if k.startswith("redacted"):
            print(f"  {k}: {v}")
    print("  mojibake repaired:", m["counts"]["stage_stats"]["s1"].get("mojibake_repaired", 0),
          " boilerplate lines removed:", m["counts"]["stage_stats"]["s1"].get("boilerplate_lines_removed", 0))


SECTIONS = {"sources": sources, "funnel": funnel, "near": near, "filters": filters, "contam": contam, "pii": pii}

if __name__ == "__main__":
    out, m, rows = load(sys.argv[1])
    for name in (sys.argv[2:] or SECTIONS):
        SECTIONS[name](out, m, rows)
