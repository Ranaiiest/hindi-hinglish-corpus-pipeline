import re
import zlib

_CONS = {}
for grp, ch in [("कखक़ख़", "k"), ("गघग़", "g"), ("चछ", "c"), ("जझज़", "j"), ("टठतथ", "t"), ("डढदधड़ढ़", "d"),
                ("ङञणन", "n"), ("पफफ़", "p"), ("बभ", "b"), ("म", "m"), ("य", "y"), ("र", "r"), ("लळ", "l"),
                ("व", "v"), ("शषस", "s"), ("ह", "h")]:
    for c in grp:
        _CONS[ord(c)] = ch
_DEV_TABLE = dict(_CONS)
for c in range(0x0900, 0x0980):
    _DEV_TABLE.setdefault(c, None)
_DEV_TABLE[0x0901] = "n"
_DEV_TABLE[0x0902] = "n"
_DEV_WORD = re.compile(r"[\u0900-\u0963\u0971-\u097F]+")
_LAT_WORD = re.compile(r"[a-z]+")
_DIGRAPH = [("chh", "c"), ("ch", "c"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"),
            ("ph", "p"), ("bh", "b"), ("sh", "s"), ("jh", "j")]
_LAT_TABLE = {ord(a): None for a in "aeiou"}
_LAT_TABLE.update({ord("f"): "p", ord("w"): "v", ord("z"): "j", ord("q"): "k", ord("x"): "k"})
_RUN = re.compile(r"(.)\1+")


def skeleton_words(text):
    out = []
    for m in re.finditer(r"[\u0900-\u0963\u0971-\u097F]+|[A-Za-z]+", text):
        w = m.group(0)
        if "\u0900" <= w[0] <= "\u097f":
            s = w.translate(_DEV_TABLE)
        else:
            s = w.lower()
            for a, b in _DIGRAPH:
                s = s.replace(a, b)
            s = s.translate(_LAT_TABLE)
        s = _RUN.sub(r"\1", s)
        if s:
            out.append(s)
    return out


def grams(words, n):
    if len(words) < n:
        return set()
    return {zlib.crc32(" ".join(words[i:i + n]).encode("utf-8")) for i in range(len(words) - n + 1)}


def snippet(s, n=200):
    s = s.replace("\n", " ")
    return s[:n]
