import argparse
import csv
import hashlib
import heapq
import json
import os
import shutil
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from . import CODE_VERSION
from .config import STAGE_KEYS, load_config, subset_hash
from .contam import grams, skeleton_words, snippet
from .dedup import LSH, MinHasher, est_jaccard, word_shingles
from .io_utils import (JsonlWriter, atomic_write_text, discover, iter_records, read_jsonl, rel,
                       sha256_file, source_of)
from .langid import detect
from .pii import redact
from .quality import check, is_numeric_table
from .textnorm import fix_mojibake, normalize_text, text_key

STAGES = ["read", "normalize", "lang", "filter", "eval_holdout", "exact_dedup", "near_dedup", "contamination"]
SAMPLE_K = 40


def log(*a):
    print("[pipeline]", *a, file=sys.stderr, flush=True)


def h64(s):
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def drop_row(doc_id, source, stage, reason, lang="", dup_of=""):
    return {"id": doc_id, "status": "dropped", "stage": stage, "reason": reason, "dup_of": dup_of,
            "source": source, "lang": lang}


def truncate_at_boundary(text, max_chars):
    if len(text) <= max_chars:
        return text, False
    cut = text[:max_chars]
    for sep in ("।", "\n", ". ", "? ", "! "):
        i = cut.rfind(sep)
        if i >= max_chars * 0.5:
            return cut[:i + len(sep)].strip(), True
    j = cut.rfind(" ")
    return (cut[:j] if j > 0 else cut).strip(), True


def stage1(files, raw_dir, cfg, work, diag):
    kept = JsonlWriter(work / "s1_kept.jsonl.gz", gz=True)
    dropped = JsonlWriter(work / "s1_dropped.jsonl")
    ec = cfg["eval"]
    quota = ec["quota"]
    heaps = {l: [] for l in quota}
    samples = defaultdict(list)
    c = Counter()
    keep_langs = set(cfg["keep_langs"])

    def sample(stage, reason, doc_id, source, lang, text):
        hp = samples[(stage, reason)]
        item = (-h64("sample:" + doc_id), doc_id,
                {"id": doc_id, "source": source, "lang": lang, "stage": stage, "reason": reason, "text": text[:800]})
        if len(hp) < SAMPLE_K:
            heapq.heappush(hp, item)
        elif item[0] > hp[0][0]:
            heapq.heapreplace(hp, item)

    n_in = 0
    for path in files:
        r = rel(path, raw_dir)
        pre = hashlib.sha1(r.encode()).hexdigest()[:8]
        src = source_of(path, raw_dir)
        for ordinal, raw, err in iter_records(path, cfg):
            doc_id = f"{pre}:{ordinal:09d}"
            n_in += 1
            if err:
                dropped.write(drop_row(doc_id, src, "read", err)); c["read:" + err] += 1
                continue
            t, fixed = fix_mojibake(raw)
            if fixed:
                c["mojibake_repaired"] += 1
            t = normalize_text(t)
            if not t:
                dropped.write(drop_row(doc_id, src, "normalize", "empty_after_normalize")); continue
            lang, st = detect(t, cfg["langid"])
            numeric = is_numeric_table(t, cfg["quality"])
            if lang not in keep_langs and not (lang == "other" and numeric):
                reason = f"lang_{lang}"
                dropped.write(drop_row(doc_id, src, "lang", reason, lang))
                sample("lang", reason, doc_id, src, lang, t)
                continue
            ok, reason, t2, notes = check(t, lang, st, cfg["quality"], numeric)
            c["boilerplate_lines_removed"] += notes.get("boilerplate_lines_removed", 0)
            if not ok:
                dropped.write(drop_row(doc_id, src, "filter", reason, lang))
                sample("filter", reason, doc_id, src, lang, t)
                continue
            raw_sha = hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()
            kept.write({"id": doc_id, "source": src, "lang": lang, "text": t2, "raw_sha": raw_sha,
                        "numeric": bool(notes.get("numeric_table"))})

            if lang in quota and not numeric:
                words = t2.split()
                if len(words) >= ec["min_words"] and len(t2) >= ec["min_chars"]:
                    rank = h64(ec["seed"] + text_key(t2))
                    hp = heaps[lang]
                    k = quota[lang] * ec["oversample"]
                    item = (-rank, doc_id, {"id": doc_id, "source": src, "lang": lang, "text": t2, "raw_sha": raw_sha})
                    if len(hp) < k:
                        heapq.heappush(hp, item)
                    elif item[0] > hp[0][0]:
                        heapq.heapreplace(hp, item)
    kept.close(); dropped.close()
    cands = {l: [it[2] | {"rank": -it[0]} for it in sorted(hp, key=lambda x: (-x[0], x[1]))] for l, hp in heaps.items()}
    atomic_write_text(work / "s1_eval_candidates.json", json.dumps(cands, ensure_ascii=False, sort_keys=True))
    w = JsonlWriter(diag / "filter_drop_samples.jsonl")
    for key in sorted(samples):
        for it in sorted(samples[key], key=lambda x: (-x[0], x[1])):
            w.write(it[2])
    w.close()
    stats = dict(c); stats["n_in"] = n_in; stats["kept"] = kept.n
    return stats


def stage2(cfg, work, out_tmp):
    ec = cfg["eval"]
    cands = json.loads((work / "s1_eval_candidates.json").read_text(encoding="utf-8"))
    seen, ids, rows = set(), [], []
    stats = {}
    for lang in sorted(ec["quota"]):
        n = 0
        for it in cands.get(lang, []):
            if n >= ec["quota"][lang]:
                break
            text, truncated = truncate_at_boundary(it["text"], ec["max_chars"])
            text, _ = redact(text)
            key = text_key(text)
            if key in seen or len(text.split()) < ec["min_words"]:
                continue
            seen.add(key)
            rows.append({"eval_id": it["id"], "lang": lang, "source": it["source"], "text": text,
                         "raw_sha": None if truncated else it["raw_sha"]})
            ids.append(it["id"]); n += 1
        stats[f"eval_{lang}"] = n
    rows.sort(key=lambda r: (r["lang"], r["eval_id"]))
    w = JsonlWriter(out_tmp / "eval.jsonl")
    for r in rows:
        w.write({k: r[k] for k in ("eval_id", "text", "lang", "source")})
    w.close()
    w = JsonlWriter(work / "s2_eval_internal.jsonl")
    for r in rows:
        w.write(r)
    w.close()
    atomic_write_text(work / "s2_eval_ids.json", json.dumps(sorted(ids)))
    stats["eval_total"] = len(rows)
    return stats


def stage3(cfg, work, diag):
    dc = cfg["dedup"]
    eval_ids = set(json.loads((work / "s2_eval_ids.json").read_text()))
    kept = JsonlWriter(work / "s3_kept.jsonl.gz", gz=True)
    dropped = JsonlWriter(work / "s3_dropped.jsonl")
    pairs = JsonlWriter(diag / "near_dup_pairs.jsonl")
    mh = MinHasher(dc["num_perm"], dc["seed"])
    lsh = LSH(dc["bands"], dc["rows"], dc["max_bucket"])
    sigs, idx_ids, idx_snip = [], [], []
    exact = {}
    pii = Counter(); c = Counter()
    for row in read_jsonl(work / "s1_kept.jsonl.gz"):
        doc_id, src, lang = row["id"], row["source"], row["lang"]
        if doc_id in eval_ids:
            dropped.write(drop_row(doc_id, src, "eval_holdout", "held_out_for_eval", lang)); c["eval_holdout"] += 1
            continue
        text, counts = redact(row["text"])
        pii.update(counts)
        key = text_key(text)
        kh = hashlib.blake2b(key.encode("utf-8"), digest_size=16).digest()
        if kh in exact:
            dropped.write(drop_row(doc_id, src, "exact_dedup", "exact_duplicate", lang, exact[kh])); c["exact"] += 1
            continue
        sig = mh.signature(word_shingles(key, dc["shingle_words"]))
        dup_of, best = "", 0.0
        if sig is not None:
            cand = lsh.query(sig, dc["max_candidates"])
            for ci in cand:
                s = est_jaccard(sig, sigs[ci])
                if s >= dc["log_floor"]:
                    pairs.write({"a": idx_ids[ci], "b": doc_id, "sim": round(s, 4),
                                 "decision": "duplicate" if s >= dc["threshold"] else "distinct",
                                 "a_text": idx_snip[ci], "b_text": snippet(text)})
                if s > best:
                    best, dup_of = s, idx_ids[ci]
            if best >= dc["threshold"]:
                dropped.write(drop_row(doc_id, src, "near_dedup", f"near_duplicate(sim={best:.2f})", lang, dup_of)); c["near"] += 1
                continue
        exact[kh] = doc_id
        if sig is not None:
            lsh.add(len(sigs), sig)
            sigs.append(sig); idx_ids.append(doc_id); idx_snip.append(snippet(text))
        kept.write({"id": doc_id, "source": src, "lang": lang, "text": text, "raw_sha": row["raw_sha"]})
    kept.close(); dropped.close(); pairs.close()
    stats = dict(c); stats["kept"] = kept.n
    stats.update({f"redacted_{k}": v for k, v in sorted(pii.items())})
    return stats


def stage4(cfg, work, out_tmp, diag):
    cc = cfg["contamination"]
    n = cc["gram_words"]; tn = cc["translit_gram"]
    ev = list(read_jsonl(work / "s2_eval_internal.jsonl"))
    exact_raw, exact_text, exact_key = {}, {}, {}
    gram_idx, tgram_idx = defaultdict(list), defaultdict(list)
    ev_info = []
    for i, e in enumerate(ev):
        text = e["text"]; key = text_key(text)
        if e.get("raw_sha"):
            exact_raw.setdefault(e["raw_sha"], []).append(i)
        exact_text.setdefault(text, []).append(i)
        exact_key.setdefault(key, []).append(i)
        g = grams(key.split(), n)
        tw = skeleton_words(text)
        tg = grams(tw, tn) if len(tw) >= cc["translit_min_words"] else set()
        ev_info.append((g, tg))
        for x in g:
            gram_idx[x].append(i)
        for x in tg:
            tgram_idx[x].append(i)
    kept = JsonlWriter(work / "s4_kept.jsonl.gz", gz=True)
    dropped = JsonlWriter(work / "s4_dropped.jsonl")
    rej = JsonlWriter(diag / "contamination_rejected.jsonl")
    leaks = defaultdict(dict)
    rank = {"exact": 0, "normalized": 1, "contained": 2, "translit": 3}
    c = Counter(); n_rej = 0
    for row in read_jsonl(work / "s3_kept.jsonl.gz"):
        text = row["text"]; key = text_key(text)
        hits = {}
        for i in exact_raw.get(row["raw_sha"], []):
            hits[i] = "exact"
        for i in exact_text.get(text, []):
            hits.setdefault(i, "normalized")
        for i in exact_key.get(key, []):
            hits.setdefault(i, "normalized")

        tg_doc = set(); counts = Counter()
        for x in grams(key.split(), n):
            for i in gram_idx.get(x, ()):
                counts[i] += 1
        for i, k in sorted(counts.items()):
            tot = len(ev_info[i][0]) or 1
            frac = k / tot
            if frac >= cc["containment"]:
                hits.setdefault(i, "contained")
            elif frac >= cc["reject_floor"] and n_rej < 300:
                rej.write({"eval_id": ev[i]["eval_id"], "train_id": row["id"], "method": "contained",
                           "score": round(frac, 3), "eval_text": snippet(ev[i]["text"], 300), "train_text": snippet(text, 300)})
                n_rej += 1
        tw = skeleton_words(text)
        tcounts = Counter()
        for x in grams(tw, tn):
            for i in tgram_idx.get(x, ()):
                if ev[i]["lang"] != row["lang"]:
                    tcounts[i] += 1
        for i, k in sorted(tcounts.items()):
            frac = k / (len(ev_info[i][1]) or 1)
            if frac >= cc["translit_containment"]:
                hits.setdefault(i, "translit")
            elif frac >= cc["reject_floor"] + 0.15 and n_rej < 300:
                rej.write({"eval_id": ev[i]["eval_id"], "train_id": row["id"], "method": "translit",
                           "score": round(frac, 3), "eval_text": snippet(ev[i]["text"], 300), "train_text": snippet(text, 300)})
                n_rej += 1
        if hits:
            first = min(sorted(hits), key=lambda i: (rank[hits[i]], i))
            m = hits[first]
            dropped.write(drop_row(row["id"], row["source"], "contamination", f"leaks_eval({m})", row["lang"], ev[first]["eval_id"]))
            c["leaking_train_docs"] += 1; c["by_" + m] += 1
            for i, mm in hits.items():
                leaks[i][row["id"]] = mm
        else:
            kept.write(row)
    kept.close(); dropped.close(); rej.close()
    w = JsonlWriter(work / "s4_contamination.jsonl")
    for i in sorted(leaks, key=lambda i: ev[i]["eval_id"]):
        methods = leaks[i]
        best = min(methods.values(), key=lambda m: rank[m])
        w.write({"eval_id": ev[i]["eval_id"], "train_ids": sorted(methods), "method": best,
                 "methods": {k: methods[k] for k in sorted(methods)}})
    w.close()
    stats = dict(c); stats["eval_items_affected"] = len(leaks); stats["kept"] = kept.n
    return stats


def finalize(cfg, work, out, out_tmp, diag, n_in, inputs, raw_dir, stage_stats, fps):

    shard = cfg["output"]["shard_docs"]
    cdir = out / "clean.tmp"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir()
    w, n_shard, n_part = None, 0, 0
    kept_ids = 0
    for row in read_jsonl(work / "s4_kept.jsonl.gz"):
        if w is None or n_shard >= shard:
            if w:
                w.close()
            w = JsonlWriter(cdir / f"part-{n_part:05d}.jsonl.gz", gz=True); n_part += 1; n_shard = 0
        w.write({"id": row["id"], "text": row["text"], "lang": row["lang"], "source": row["source"]})
        n_shard += 1; kept_ids += 1
    if w:
        w.close()
    if (out / "clean").exists():
        shutil.rmtree(out / "clean")
    os.replace(cdir, out / "clean")


    funnel = Counter(); by_src = defaultdict(Counter); lang_label = Counter()
    tmp = out / "ledger.csv.tmp"
    n_rows = 0
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["id", "status", "stage", "reason", "dup_of", "source", "lang"])
        for name in ("s1_dropped", "s3_dropped", "s4_dropped"):
            for r in read_jsonl(work / f"{name}.jsonl"):
                wr.writerow([r["id"], "dropped", r["stage"], r["reason"], r["dup_of"], r["source"], r["lang"]])
                funnel[(r["stage"], r["lang"] or "unknown")] += 1
                by_src[r["source"]]["input"] += 1
                if r["lang"]:
                    lang_label[r["lang"]] += 1
                n_rows += 1
        for r in read_jsonl(work / "s4_kept.jsonl.gz"):
            wr.writerow([r["id"], "kept", "final", "", "", r["source"], r["lang"]])
            funnel[("kept", r["lang"])] += 1
            by_src[r["source"]]["input"] += 1; by_src[r["source"]]["kept"] += 1
            lang_label[r["lang"]] += 1
            n_rows += 1
        f.flush(); os.fsync(f.fileno())
    if n_rows != n_in:
        raise RuntimeError(f"ledger has {n_rows} rows but {n_in} input docs were read")
    os.replace(tmp, out / "ledger.csv")

    shutil.copyfile(out_tmp / "eval.jsonl", out / "eval.jsonl")
    shutil.copyfile(work / "s4_contamination.jsonl", out / "contamination.jsonl")
    ddir = out / "diagnostics"
    ddir.mkdir(exist_ok=True)
    for p in diag.glob("*.jsonl"):
        shutil.copyfile(p, ddir / p.name)


    declared = {}
    sp = Path(raw_dir) / "SOURCES.json"
    if sp.exists():
        try:
            for s in json.loads(sp.read_text(encoding="utf-8")):
                declared[s.get("dir") or s.get("name")] = s
        except ValueError:
            pass
    src_bytes = Counter()
    for i in inputs:
        top = i["path"].split("/")[0] if "/" in i["path"] else i["path"].rsplit(".", 1)[0]
        src_bytes[top] += i["bytes"]
    sources = []
    for s in sorted(by_src):
        d = declared.get(s, {})
        sources.append({"source_dir": s, "declared": d, "raw_bytes": src_bytes.get(s, 0),
                        "docs_in": by_src[s]["input"], "docs_kept": by_src[s]["kept"]})
    funnel_out = {}
    for (stage, lang), v in sorted(funnel.items()):
        funnel_out.setdefault(stage, {})[lang] = v

    def sha_of(p):
        return sha256_file(p)
    outputs = {}
    for p in sorted((out / "clean").glob("*.jsonl.gz")):
        outputs[f"clean/{p.name}"] = sha_of(p)
    for name in ("ledger.csv", "eval.jsonl", "contamination.jsonl"):
        outputs[name] = sha_of(out / name)
    manifest = {
        "code_version": CODE_VERSION,
        "inputs": inputs,
        "sources": sources,
        "config": cfg,
        "stage_fingerprints": fps,
        "counts": {"input_docs": n_in, "kept_docs": kept_ids, "language_labels_after_langid": dict(sorted(lang_label.items())),
                   "dropped_by_stage_and_lang": funnel_out, "stage_stats": stage_stats},
        "eval_purpose": cfg["eval"]["purpose"],
        "output_sha256": outputs,
    }
    atomic_write_text(out / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return {"kept": kept_ids, "ledger_rows": n_rows}


def run(raw_dir, out_dir, cfg, fresh=False):
    raw_dir, out = Path(raw_dir), Path(out_dir)
    files = discover(raw_dir)
    if not files:
        log(f"no data files found under {raw_dir}"); return 1
    out.mkdir(parents=True, exist_ok=True)
    work = out / ".work"
    if fresh and work.exists():
        shutil.rmtree(work)
    work.mkdir(exist_ok=True)
    diag = work / "diag"; diag.mkdir(exist_ok=True)
    out_tmp = work / "out"; out_tmp.mkdir(exist_ok=True)


    cache_p = work / "input_hashes.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    inputs = []
    for p in files:
        st = p.stat(); r = rel(p, raw_dir)
        ck = f"{r}|{st.st_size}|{st.st_mtime_ns}"
        if ck not in cache:
            cache[ck] = sha256_file(p)
        inputs.append({"path": r, "bytes": st.st_size, "sha256": cache[ck]})
    atomic_write_text(cache_p, json.dumps(cache))
    base = hashlib.sha256((json.dumps([i["sha256"] + i["path"] for i in inputs]) + CODE_VERSION).encode()).hexdigest()
    fps, prev = {}, base
    for st in ("s1", "s2", "s3", "s4", "final"):
        prev = hashlib.sha256((prev + subset_hash(cfg, STAGE_KEYS[st])).encode()).hexdigest()
        fps[st] = prev

    stats_all = {}

    def run_stage(name, fn):
        done, sp = work / f"{name}.done", work / f"{name}.stats.json"
        if done.exists() and done.read_text() == fps[name] and sp.exists():
            log(f"{name}: up to date, skipping")
            stats_all[name] = json.loads(sp.read_text()); return stats_all[name]
        if done.exists():
            done.unlink()
        log(f"{name}: running")
        s = fn()
        atomic_write_text(sp, json.dumps(s, sort_keys=True))
        atomic_write_text(done, fps[name])
        stats_all[name] = s
        log(f"{name}: done {s}")
        return s

    s1 = run_stage("s1", lambda: stage1(files, raw_dir, cfg, work, diag))
    run_stage("s2", lambda: stage2(cfg, work, out_tmp))
    run_stage("s3", lambda: stage3(cfg, work, diag))
    run_stage("s4", lambda: stage4(cfg, work, out_tmp, diag))
    run_stage("final", lambda: finalize(cfg, work, out, out_tmp, diag, s1["n_in"], inputs, raw_dir,
                                        {k: v for k, v in stats_all.items() if k != "final"}, fps))
    log("finished")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hindi/Hinglish corpus pipeline")
    ap.add_argument("raw_dir"); ap.add_argument("out_dir")
    ap.add_argument("--config", default=os.environ.get("CONFIG") or None)
    ap.add_argument("--fresh", action="store_true", help="discard cached stage outputs")
    a = ap.parse_args(argv)
    return run(a.raw_dir, a.out_dir, load_config(a.config), a.fresh)


if __name__ == "__main__":
    sys.exit(main())
