import csv
import gzip
import hashlib
import io
import json
import os
import sys
import zlib
from pathlib import Path

DATA_SUFFIXES = (".jsonl", ".ndjson", ".json", ".csv", ".tsv", ".parquet", ".txt")
csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))


def discover(raw_dir):
    root = Path(raw_dir)
    files = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        up = p.name.upper()
        if up.startswith("SOURCES") or up.startswith("README") or up.startswith("MANIFEST"):
            continue
        base = p.name[:-3] if p.name.lower().endswith(".gz") else p.name
        if base.lower().endswith(DATA_SUFFIXES):
            files.append(p)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def rel(path, root):
    return Path(path).relative_to(root).as_posix()


def source_of(path, root):
    parts = Path(path).relative_to(root).parts
    if len(parts) > 1:
        return parts[0]
    name = parts[0]
    for suf in (".gz",):
        if name.lower().endswith(suf):
            name = name[:-len(suf)]
    return name.rsplit(".", 1)[0]


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _open_bin(path):
    return gzip.open(path, "rb") if str(path).lower().endswith(".gz") else open(path, "rb")


def _pick_text(obj, fields):
    if isinstance(obj, str):
        return obj, None
    if isinstance(obj, dict):
        for k in fields:
            v = obj.get(k)
            if isinstance(v, str):
                return v, None
        strs = [v for v in obj.values() if isinstance(v, str)]
        if strs:
            return max(strs, key=len), None
        return None, "no_text_field"
    return None, "not_a_record"


def _iter_jsonl(path, cfg):
    i = -1
    try:
        with _open_bin(path) as f:
            for raw in f:
                i += 1
                if not raw.strip():
                    yield i, None, "blank_line"; continue
                try:
                    line = raw.decode("utf-8")
                except UnicodeDecodeError:
                    yield i, None, "bad_utf8"; continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    yield i, None, "bad_json"; continue
                t, err = _pick_text(obj, cfg["text_fields"])
                yield i, t, err
    except (EOFError, OSError, zlib.error):
        yield i + 1, None, "truncated_or_corrupt_file"


def _iter_json_whole(path, cfg):
    try:
        with _open_bin(path) as f:
            data = json.loads(f.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError, EOFError, OSError, zlib.error):
        yield 0, None, "bad_json_file"; return
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        yield 0, None, "not_a_record"; return
    for i, obj in enumerate(data):
        t, err = _pick_text(obj, cfg["text_fields"])
        yield i, t, err


def _iter_json(path, cfg):

    with _open_bin(path) as f:
        head = f.read(1)
        while head and head.isspace():
            head = f.read(1)
    if head in (b"[",):
        yield from _iter_json_whole(path, cfg)
    else:
        yield from _iter_jsonl(path, cfg)


def _iter_csv(path, cfg, delim):
    i = -1
    try:
        with _open_bin(path) as b:
            f = io.TextIOWrapper(b, encoding="utf-8", errors="replace", newline="")
            rdr = csv.reader(f, delimiter=delim)
            header = next(rdr, None)
            if header is None:
                return
            col = next((header.index(k) for k in cfg["text_fields"] if k in header), None)
            if col is None:
                col = 0
            for row in rdr:
                i += 1
                if col >= len(row):
                    yield i, None, "malformed_row"; continue
                yield i, row[col], None
    except (csv.Error, EOFError, OSError, zlib.error):
        yield i + 1, None, "truncated_or_corrupt_file"


def _iter_parquet(path, cfg):
    import pyarrow as pa
    import pyarrow.parquet as pq
    i = -1
    try:
        pf = pq.ParquetFile(path)
        names = pf.schema_arrow.names
        col = next((k for k in cfg["text_fields"] if k in names), None)
        if col is None:
            col = next((f.name for f in pf.schema_arrow if pa.types.is_string(f.type) or pa.types.is_large_string(f.type)), None)
        if col is None:
            yield 0, None, "no_text_field"; return
        for batch in pf.iter_batches(batch_size=1000, columns=[col]):
            for v in batch.column(0).to_pylist():
                i += 1
                if isinstance(v, str):
                    yield i, v, None
                else:
                    yield i, None, "no_text_field"
    except (pa.ArrowException, OSError, EOFError):
        yield i + 1, None, "truncated_or_corrupt_file"


def _iter_txt(path, cfg):
    i = -1
    try:
        with _open_bin(path) as f:
            if cfg["txt_mode"] == "file":
                try:
                    yield 0, f.read().decode("utf-8"), None
                except UnicodeDecodeError:
                    yield 0, None, "bad_utf8"
                return
            for raw in f:
                if not raw.strip():
                    continue
                i += 1
                try:
                    yield i, raw.decode("utf-8"), None
                except UnicodeDecodeError:
                    yield i, None, "bad_utf8"
    except (EOFError, OSError, zlib.error):
        yield i + 1, None, "truncated_or_corrupt_file"


def iter_records(path, cfg):
    name = Path(path).name.lower()
    if name.endswith(".gz"):
        name = name[:-3]
    if name.endswith((".jsonl", ".ndjson")):
        return _iter_jsonl(path, cfg)
    if name.endswith(".json"):
        return _iter_json(path, cfg)
    if name.endswith(".csv"):
        return _iter_csv(path, cfg, ",")
    if name.endswith(".tsv"):
        return _iter_csv(path, cfg, "\t")
    if name.endswith(".parquet"):
        return _iter_parquet(path, cfg)
    return _iter_txt(path, cfg)


class JsonlWriter:


    def __init__(self, path, gz=False):
        self.path, self.tmp = str(path), str(path) + ".tmp"
        raw = open(self.tmp, "wb")
        self._raw = raw
        if gz:
            self._gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
            self.f = io.TextIOWrapper(self._gz, encoding="utf-8", newline="\n")
        else:
            self._gz = None
            self.f = io.TextIOWrapper(raw, encoding="utf-8", newline="\n")
        self.n = 0

    def write(self, row):
        self.f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self.n += 1

    def close(self):
        self.f.flush()
        if self._gz is not None:
            self._gz.close()
        self._raw.flush(); os.fsync(self._raw.fileno()); self._raw.close()
        os.replace(self.tmp, self.path)


def read_jsonl(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def atomic_write_text(path, text):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
