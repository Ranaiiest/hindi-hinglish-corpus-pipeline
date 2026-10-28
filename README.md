# Indic corpus pipeline (Hindi + Hinglish)

```bash
./download.sh raw            # ONLINE: raw data + raw/SOURCES.json
./run.sh raw out             # OFFLINE: clean/, ledger.csv, eval.jsonl, contamination.jsonl, manifest.json
python tools/report.py out   # numbers used in DECISIONS.md
python -m pytest -q tests
```

Optional overrides: `CONFIG=my.json ./run.sh raw out` (deep-merged over `src/indicpipe/config.py`).

Smoke test (no download): `python tools/make_synthetic.py /tmp/raw && ./run.sh /tmp/raw /tmp/out`.

Submission artifacts in this repo: `DECISIONS.md`, `eval.jsonl`, `sample_clean_1000.jsonl` (full `raw/` / `out/` are gitignored — do not zip them).
