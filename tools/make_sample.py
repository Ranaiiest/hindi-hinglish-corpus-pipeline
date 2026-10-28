import glob, gzip, hashlib, json, sys
out, dest = sys.argv[1], sys.argv[2]
K = 1000
res = []
for p in sorted(glob.glob(out + "/clean/*.jsonl.gz")):
    for line in gzip.open(p, "rt", encoding="utf-8"):
        r = json.loads(line)
        k = hashlib.blake2b(("sample" + r["id"]).encode(), digest_size=8).hexdigest()
        res.append((k, line))
        if len(res) > 2 * K:
            res.sort(); res = res[:K]
res.sort(); res = res[:K]
with open(dest, "w", encoding="utf-8") as f:
    for _, line in sorted(res, key=lambda x: json.loads(x[1])["id"]):
        f.write(line)
print("wrote", len(res), "rows to", dest)
