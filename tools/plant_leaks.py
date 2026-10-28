import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(__file__))
raw, out, new = sys.argv[1:4]
shutil.copytree(raw, new, dirs_exist_ok=True)
ev = [json.loads(l) for l in open(os.path.join(out, "eval.jsonl"), encoding="utf-8")]
hi = [e for e in ev if e["lang"] == "hi"][:6]
os.makedirs(os.path.join(new, "leaks"), exist_ok=True)
rows = []
for i, e in enumerate(hi):
    t = e["text"]
    if i % 3 == 0:
        rows.append(t)
    elif i % 3 == 1:
        rows.append(t.replace("।", " ").upper() + " ")
    else:
        rows.append("भूमिका के रूप में यह बात कही गई है। " + t + " इसके बाद और भी कई बातें जोड़ी गई हैं।")
try:
    import make_synthetic
    rom = {d: l for d, l in make_synthetic.PAIRS}
    for e in hi[:2]:
        lat = " ".join(rom[s.strip() + "।"] for s in e["text"].split("।") if s.strip() + "।" in rom)
        if lat:
            rows.append(lat)
except Exception as ex:
    print("transliteration plant skipped:", ex)
with open(os.path.join(new, "leaks", "leaks.jsonl"), "w", encoding="utf-8") as f:
    for t in rows:
        f.write(json.dumps({"text": t}, ensure_ascii=False) + "\n")
print(f"planted {len(rows)} leak docs into {new}/leaks/leaks.jsonl")
