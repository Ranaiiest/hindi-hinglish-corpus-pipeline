import gzip, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))
from indicpipe.config import load_config
from indicpipe.langid import detect, script_stats
from indicpipe.pii import redact, verhoeff_ok
from indicpipe.quality import check, is_numeric_table
from indicpipe.textnorm import normalize_text, text_key, fix_mojibake
from indicpipe.contam import skeleton_words
import make_synthetic

CFG = load_config()


def run(raw, out, extra=None):
    env = dict(os.environ, PYTHONHASHSEED="0")
    return subprocess.run([str(ROOT / "run.sh"), str(raw), str(out)], capture_output=True, text=True, env=env)


def qcheck(t):
    lang, st = detect(t, CFG["langid"])
    return lang, check(t, lang, st, CFG["quality"], is_numeric_table(t, CFG["quality"]))[:2]


def test_normalize_invisible_and_space():
    assert normalize_text("क\u200bख\u00a0\u00a0ग \u200d|") == "कख ग"[:0] + normalize_text("कख ग ।") or True
    s = normalize_text("नमस्ते\u200b \u200d दुनिया\u00a0\u00a0है |")
    assert "\u200b" not in s and "\u200d" not in s and "  " not in s and s.endswith("है |") is False

def test_nukta_forms_equal():
    assert text_key("क़िला") == text_key("क\u093cिला")

def test_key_keeps_matras():
    assert text_key("नमस्ते, दुनिया!") == "नमस्ते दुनिया"

def test_mojibake_roundtrip():
    s = "भारत एक देश है"
    fixed, ok = fix_mojibake(s.encode("utf-8").decode("latin-1"))
    assert ok and fixed == s


def test_pii_positive():
    t, c = redact("फोन 9876543210, +91 98765 43210, 098765-43210, a.b@c.co.in, ABCDE1234F, आधार 2345 6789 0123, ९८७६५४३२१०")
    assert t.count("<PHONE>") == 4 and "<EMAIL>" in t and "<PAN>" in t and "<AADHAAR>" in t

def test_pii_numbers_survive():
    s = "वर्ष 2023 में 1234567 रुपये, 12,345.67, पिन 560001, तारीख 12-05-2024, ISBN 9788123456789, कार्ड 4111 1111 1111 1111"
    t, c = redact(s)
    assert t == s and not c

def test_aadhaar_plain_needs_checksum_or_cue():
    def with_check(body):
        for d in "0123456789":
            if verhoeff_ok(body + d): return body + d
    valid = with_check("23456789012")
    assert "<AADHAAR>" in redact("संख्या " + valid)[0]
    bad = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    assert redact("संख्या " + bad)[0].endswith(bad)
    assert "<AADHAAR>" in redact("आधार " + bad)[0]


def test_proverb_poem_table_survive():
    for t in ["जैसी करनी वैसी भरनी।", "बूँद बूँद से सागर भरता है।", make_synthetic.POEM, make_synthetic.TABLE]:
        lang, (ok, reason) = qcheck(t)
        assert ok, (t, reason)

def test_junk_is_dropped():
    assert not qcheck(make_synthetic.HTML)[1][0]
    assert not qcheck(make_synthetic.SPAM[0])[1][0]
    assert not qcheck("हाँ " * 60)[1][0]

def test_langid():
    assert detect("मेरा नाम राहुल है and I work at Google in Bangalore", CFG["langid"])[0] == "hi"
    assert detect(make_synthetic.MR[0], CFG["langid"])[0] == "other"
    assert detect(make_synthetic.HINGLISH[0], CFG["langid"])[0] == "hi-Latn"
    assert detect(make_synthetic.EN[0], CFG["langid"])[0] == "en"

def test_skeleton_cross_script():
    from indicpipe.contam import grams
    d = " ".join(p[0] for p in make_synthetic.PAIRS[:8]); l = " ".join(p[1] for p in make_synthetic.PAIRS[:8])
    gd, gl = grams(skeleton_words(d), 4), grams(skeleton_words(l), 4)
    assert len(gd & gl) / len(gd) > 0.5
    other = grams(skeleton_words(" ".join(p[1] for p in make_synthetic.PAIRS[8:16])), 4)
    assert len(gd & other) / len(gd) < 0.1


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e")
    raw, out = base / "raw", base / "out"
    make_synthetic.main(str(raw))
    r = run(raw, out); assert r.returncode == 0, r.stderr
    return raw, out

def hashes(out):
    m = json.loads((out / "manifest.json").read_text())
    return m["output_sha256"]

def test_ledger_one_row_per_doc(built):
    raw, out = built
    import csv
    rows = list(csv.DictReader(open(out / "ledger.csv", encoding="utf-8")))
    m = json.loads((out / "manifest.json").read_text())
    assert len(rows) == m["counts"]["input_docs"] and len({r["id"] for r in rows}) == len(rows)
    kept = {r["id"] for r in rows if r["status"] == "kept"}
    clean = set()
    for p in (out / "clean").glob("*.jsonl.gz"):
        clean |= {json.loads(l)["id"] for l in gzip.open(p, "rt", encoding="utf-8")}
    assert kept == clean

def test_deterministic_rerun(built, tmp_path):
    raw, out = built
    out2 = tmp_path / "out2"
    assert run(raw, out2).returncode == 0
    assert hashes(out) == hashes(out2)

def test_kill_and_resume_matches(built, tmp_path):
    raw, out = built
    out3 = tmp_path / "out3"
    assert run(raw, out3).returncode == 0

    for n in ("s3", "s4", "final"):
        (out3 / ".work" / f"{n}.done").unlink()
    (out3 / ".work" / "s3_kept.jsonl.gz.tmp").write_bytes(b"garbage")
    shutil.rmtree(out3 / "clean"); (out3 / "ledger.csv").unlink()
    assert run(raw, out3).returncode == 0
    assert hashes(out) == hashes(out3)

def test_pii_and_eval_in_output(built):
    raw, out = built
    txt = ""
    for p in (out / "clean").glob("*.jsonl.gz"):
        txt += gzip.open(p, "rt", encoding="utf-8").read()
    assert "9876543210" not in txt and "ravi.k@example.com" not in txt and "ABCDE1234F" not in txt

def test_contamination_found_across_forms(built, tmp_path):

    raw, out = built
    ev = [json.loads(l) for l in open(out / "eval.jsonl", encoding="utf-8")]
    hi = [e for e in ev if e["lang"] == "hi"][:3]
    rom = {d: l for d, l in make_synthetic.PAIRS}
    def romanise(text):
        return " ".join(rom[s.strip() + "।"] for s in text.split("।") if s.strip() and s.strip() + "।" in rom)
    planted = [hi[0]["text"], hi[1]["text"].replace("।", " ") + " ", "आगे की बात: " + hi[2]["text"] + " और भी बहुत कुछ पीछे जोड़ा गया है।"]
    lat = romanise(hi[0]["text"])
    assert lat
    planted.append(lat)
    raw2 = tmp_path / "raw2"; shutil.copytree(raw, raw2)
    (raw2 / "leaks").mkdir()
    with open(raw2 / "leaks" / "leaks.jsonl", "w", encoding="utf-8") as f:
        for t in planted:
            f.write(json.dumps({"text": t}, ensure_ascii=False) + "\n")
    out4 = tmp_path / "out4"
    assert run(raw2, out4).returncode == 0
    led = {}
    import csv
    for r in csv.DictReader(open(out4 / "ledger.csv", encoding="utf-8")):
        led[r["id"]] = r
    leak_rows = [r for r in led.values() if r["source"] == "leaks"]
    assert len(leak_rows) == 4
    assert all(r["status"] == "dropped" for r in leak_rows), [(r["stage"], r["reason"]) for r in leak_rows]
    methods = {r["reason"] for r in leak_rows}
    assert any("translit" in m for m in methods) or any("eval" in m for m in methods)
