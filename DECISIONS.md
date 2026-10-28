# DECISIONS

Numbers below are from my local run: `./download.sh raw` then `./run.sh raw out` on this machine (`.venv`, Python 3.14). Download took ~4 min. Full pipeline ~7.8 min wall clock on ~40k docs. I also smoke-tested on synthetic data + `plant_leaks.py` before the real download.

---

## 1. Sources

- Hindi Wikipedia (wikimedia/wikipedia, 20231101.hi) | CC BY-SA 3.0 (+GFDL) — checked against HF dataset card on download day | [https://huggingface.co/datasets/wikimedia/wikipedia](https://huggingface.co/datasets/wikimedia/wikipedia) | docs in=12000 kept=9530 | 27.9 MB raw | downloaded 2026-10-27 (UTC)
- FineWeb-2 hin_Deva | ODC-By 1.0 (+ Common Crawl terms) | [https://huggingface.co/datasets/HuggingFaceFW/fineweb-2](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2) | in=20000 kept=19793 | 50.8 MB | same date
- FineWeb-2 hin_Latn (Hinglish / Latin-script Hindi candidates) | ODC-By 1.0 (+ CC terms) | same FineWeb-2 URL | in=8000 kept=7845 | 33.3 MB | same date

Raw is kept as downloaded: first N rows of each original parquet shard, record values not edited. Full original shard sha256 is in `raw/SOURCES.json` (and mirrored into `manifest.json`).

Hinglish: FineWeb-2 `hin_Latn` is what I used. Source language labels are NOT trusted — after our own LID we got **hi-Latn = 7875** labelled docs (way above the 1k bar). A bunch of that shard is still English-ish / spam and gets dropped later, but the labelled count at LID time is what matters for the collect requirement. I didnt chase a second Hinglish crawl because this one already cleared 1k under our rule.

---



## 2. Funnel (docs in → out)

input docs: **40000**  
after read (malformed skipped: 0): 40000  
after normalize: 40000

per-language after our labelling (en=11, hi=32111, hi-Latn=7875, other=3):


| stage               | en  | hi    | hi-Latn | other | total     |
| ------------------- | --- | ----- | ------- | ----- | --------- |
| labelled            | 11  | 32111 | 7875    | 3     | 40000     |
| after lang          | 0   | 32111 | 7875    | 0     | 39986     |
| after filter        | 0   | 31875 | 7782    | 0     | 39657     |
| after eval_holdout  | 0   | 31715 | 7742    | 0     | 39457     |
| after exact_dedup   | 0   | 31212 | 7742    | 0     | 38954     |
| after near_dedup    | 0   | 29914 | 7738    | 0     | 37652     |
| after contamination | 0   | 29434 | 7734    | 0     | **37168** |


Biggest drops: near_dedup 1302, exact 503, contamination 484, eval holdout 200. Filters were relatively light (garbled 133, markup 98, spam_keywords 65, …). Lang gate only killed 11 en + 3 other.

PII on the train path (s3): phone 557, email 1271, aadhaar 9. Also stripped ~1195 boilerplate *lines* inside otherwise-kept docs.

---



## 3. Near-duplicates

- Method: word 3-shingle MinHash, 128 perms, LSH 32 bands × 4 rows, candidates checked with estimated Jaccard. Pairs with sim ≥ 0.60 logged to `diagnostics/near_dup_pairs.jsonl` (55794 pairs: 10310 called duplicate, 45484 distinct under thr=0.80).
- **Threshold = 0.80** (default I started with; kept it after reading buckets).

How I chose it: looked at `tools/probe_threshold.py out` buckets on the logged pairs.

- **0.60–0.70**: mostly different articles that share a site footer / translated supplier boilerplate / same news topic. Clearly keep both.
- **0.70–0.80**: still a lot of template overlap (same wiki “district stub” chrome, same health-site disclaimer, same opening “hi dosto…” with different story body). Below ~0.80 I kept seeing *different* place names or different plot with shared scaffolding.
- **0.80–0.90**: more often same spam page with small edits, or wiki stubs that are basically the same page with one token swapped. Dropping at ≥0.80 felt right.
- **0.90+**: almost always same doc / same stub template. Rare (115 + 3 in the top buckets).

Three pairs near the threshold (sim≈0.797, pipeline marked distinct — my call):

1. **sim=0.7969 — KEEP both (agree with distinct).** Hinglish “shyam / anuradha” stories. Same greeting + family setup, but one is “dusari kahani” and the other continues into siblings/ages. Shared opener, different body → not a near-dup for training.
2. **sim=0.7969 — KEEP both.** Wiki: “रायगढा … उड़ीसा … जिला” vs “फूलबनी … उड़ीसा … जिला”. Same district-page template, **different towns**. Dropping these would wipe a lot of geo pages that only differ in the headword.
3. **sim=0.7969 — KEEP both.** Manipur district stubs (तमेंगलोंग vs चन्देल) — same “इन्हें भी देखें / बाहरी कड़ियाँ” tail, different district. Same call as (2).

Known weakness: word-shingle Jaccard misses paraphrases; short docs are noisy; first-seen wins (not best-quality wins). Also wiki stub templates sit awkwardly right under 0.80 — if I had more time I’d try a second pass that strips the shared “बाहरी कड़ियाँ…” footer before shingling.

---



## 4. Filters

Deliberate exemptions (still in config): short proverbs (≥6 letters / 2 words, no harsh length floor), poems (line-repeat needs ≥8 lines and >70% repeats), number tables (≥80% numeric tokens skip letter-ratio).

I spot-checked the sampled drops in `diagnostics/filter_drop_samples.jsonl` / `report.py filters`. Three drops that look **too aggressive** (legit-ish text caught):

1. **id** `f8c0514a:000000198` **— rule** `markup`**.** Tripura state intro in clean Hindi; only reason seems leftover `[[...]]`-ish wiki residue. I’d soften markup detection when tag count is low vs long Devanagari body, or strip wiki links before the markup count.
2. **id** `f8c0514a:000010331` **— rule** `markup`**.** Normal Bollywood film blurb (“परदेस 1997…”) — again looks like a content page, not HTML spam. Same fix as above.
3. **id** `82c0b451:000001271` **— rule** `garbled_encoding`**.** Mostly readable news (“कुंवर्स ग्लोबल स्कूल…”) with one mojibake-ish char (`राष्टï्रों`). Punishing the whole doc for a single glitch is harsh; I’d allow ≤N replacement/odd latin1 chars instead of hard fail (we already have knobs, maybe my thresholds are still a bit tight).

Spam_keywords / too_short / contact_spam samples looked fair when I skimmed them (vashikaran, empty stubs like “मुखपृष्ठ”, etc.).

---



## 5. Contamination

- Eval set: **200** items (160 hi + 40 hi-Latn) held out **before** dedup. Purpose (from manifest): held-out Hindi / Hinglish passages for measuring Falcon’s per-token loss (perplexity) and next-token quality on Indian-language text.
- Method: exact (raw_sha / raw text), normalised `text_key`, containment (≥50% of eval word 5-grams in a train doc), transliteration (Devanagari↔Latin consonant skeleton, 4-grams, ≥50%, cross-script only).
- Result on real run: **15** eval items affected; **484** training docs removed (`ledger` stage=contamination). Strongest method per eval item: mostly `contained` (14), plus **1** `exact`. No translit hits on this particular eval/train mix (detector still exercised on synthetic + plant_leaks).
- Rejected candidate (logged, score below keep thr): hotel boilerplate.  
  - score≈0.37 `contained`  
  - eval: Swissotel Tallinn blurb (“यहाँ से, अतिथि शहर के उन सभी स्थानों पर आसानी से जा सकते हैं…”)  
  - train: San Francisco Hotel / Soechi International Hotel with the **same stock Hindi hotel-template sentence** but different property.  
  - Why not a leak: shared booking-site template, different hotels/cities — not the eval passage leaking into train.
- Detector sanity: on synthetic data, `tools/plant_leaks.py` + rerun showed exact / normalized / contained / translit paths firing (contam.jsonl non-empty; report listed all four methods). I didnt re-plant into the 40k raw (would contaminate the real corpus); synthetic proof is enough for “the checker works”.

---



## 6. Reproducibility

Immutable raw (sha256 in `manifest.json` / `SOURCES.json`), same commit + `requirements.lock`, `./run.sh raw out`, compare `manifest.output_sha256`. Pipeline is deterministic: `PYTHONHASHSEED=0`, seeded MinHash, sorted file/doc iteration, atomic tmp+rename writers, stage `.done` fingerprints over inputs+config+code. Kill/resume covered by `tests/test_pipeline.py`. Download is separate (`download.sh`); `run.sh` stays offline.

Note: I ran unauthenticated HF downloads (got the “set HF_TOKEN” warning) — fine for this size, but for a rebuild I’d pin a token if rate limits bite.

---



## 7. Scale (if this were 2 TB on object storage)

First thing to break: the **in-memory** exact-hash map + MinHash signatures / LSH buckets in stage 3 (~order of 1 KB per doc). Single process, full sha256 pass over inputs, one giant `ledger.csv`, and `io_utils` assuming local paths. Fix sketch: hash-partition the stream, per-shard dedup then merge on sorted keys (Spark/Ray), treat MinHash bands as a distributed join, ranged reads from object storage, ledger as partitioned parquet.

---



## 8. Wrap-up

Not done / would do next (priority order):

1. Soften markup / single-char garbled filters (see §4) and re-measure false drops.
2. Optional footer-stripping before near-dedup for wiki stubs.
3. Maybe lower near-thr slightly and re-read 0.78–0.82 band with more pairs (I stuck with 0.80 for time).
4. Commit history + zip packaging polish; more live-coding practice on PII extras (UPI/IFSC) in case follow-up asks.

Time spent: ~**3.5–4 h** honest (setup/venv/macOS `realpath` fix, synthetic smoke, download, first full run ~7.8 min, reading ledger/clean samples, probe buckets, writing this). 