import datetime, hashlib, json, os, sys
from pathlib import Path
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download, list_repo_files

raw = Path(sys.argv[1]); raw.mkdir(parents=True, exist_ok=True)
today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

SOURCES = [
    dict(dir="wikipedia_hi", name="Hindi Wikipedia (wikimedia/wikipedia, 20231101.hi)", repo="wikimedia/wikipedia",
         prefixes=["20231101.hi/"], rows=int(os.environ.get("WIKI_ROWS", 12000)),
         url="https://huggingface.co/datasets/wikimedia/wikipedia", license="CC BY-SA 3.0 (+GFDL) - attribution + share-alike",
         notes="Devanagari Hindi; encyclopedic"),
    dict(dir="fineweb2_hin_deva", name="FineWeb-2 hin_Deva (Hindi web text)", repo="HuggingFaceFW/fineweb-2",
         prefixes=["data/hin_Deva/train/"], rows=int(os.environ.get("FW_HI_ROWS", 20000)),
         url="https://huggingface.co/datasets/HuggingFaceFW/fineweb-2", license="ODC-By 1.0 (plus Common Crawl terms of use)",
         notes="web text; source label NOT trusted"),
    dict(dir="fineweb2_hin_latn", name="FineWeb-2 hin_Latn (Hindi in Latin script / Hinglish candidates)", repo="HuggingFaceFW/fineweb-2",
         prefixes=["data/hin_Latn/train/"], rows=int(os.environ.get("FW_LATN_ROWS", 8000)),
         url="https://huggingface.co/datasets/HuggingFaceFW/fineweb-2", license="ODC-By 1.0 (plus Common Crawl terms of use)",
         notes="Hinglish source; many docs will be English/spam and get dropped by OUR language id"),
]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


manifest = []
for s in SOURCES:
    print("==", s["name"])
    files = sorted(list_repo_files(s["repo"], repo_type="dataset"))
    cand = [f for f in files if any(f.startswith(p) for p in s["prefixes"]) and f.endswith(".parquet")]
    if not cand:
        print("  !! no parquet files under", s["prefixes"], "- first files in repo:", files[:15]); continue
    got, rows_left, parts = [], s["rows"], []
    d = raw / s["dir"]; d.mkdir(exist_ok=True)
    for i, f in enumerate(cand):
        if rows_left <= 0:
            break
        local = hf_hub_download(s["repo"], f, repo_type="dataset")
        shard_hash = sha256(local)
        pf = pq.ParquetFile(local)
        out_path = d / f"part-{i:03d}.parquet"
        writer, taken = None, 0
        for batch in pf.iter_batches(batch_size=2000):
            if taken >= rows_left:
                break
            if taken + batch.num_rows > rows_left:
                batch = batch.slice(0, rows_left - taken)
            if writer is None:
                writer = pq.ParquetWriter(out_path, batch.schema)
            writer.write_batch(batch); taken += batch.num_rows
        if writer:
            writer.close()
        rows_left -= taken
        parts.append({"original_file": f, "original_sha256": shard_hash, "rows_kept": taken})
        print(f"  {f}: kept first {taken} rows (original sha256 {shard_hash[:12]}...)")
    manifest.append({"dir": s["dir"], "name": s["name"], "url": s["url"], "license": s["license"],
                     "download_date": today, "notes": s["notes"], "parts": parts,
                     "rows_requested": s["rows"]})
(raw / "SOURCES.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", raw / "SOURCES.json")
