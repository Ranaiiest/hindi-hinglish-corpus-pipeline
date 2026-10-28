import json, sys
from collections import defaultdict
pairs = [json.loads(l) for l in open(sys.argv[1] + "/diagnostics/near_dup_pairs.jsonl", encoding="utf-8")]
b = defaultdict(list)
for p in pairs:
    b[int(p["sim"] * 20) / 20].append(p)
for k in sorted(b):
    print(f"\n=== sim {k:.2f}-{k+0.05:.2f}: {len(b[k])} pairs")
    for p in b[k][:3]:
        print(f"  {p['sim']}\n    A: {p['a_text'][:150]}\n    B: {p['b_text'][:150]}")
