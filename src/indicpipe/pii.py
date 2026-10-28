import re
from collections import Counter

DIGIT_FOLD = str.maketrans("०१२३४५६७८९", "0123456789")

EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")

PAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])")

AADHAAR_GROUPED_RE = re.compile(r"(?<!\d)(?<!\d[ \-])\d{4}[ \-]\d{4}[ \-]\d{4}(?!\d)(?![ \-]\d{4})")

AADHAAR_PLAIN_RE = re.compile(r"(?<![\d.])[2-9]\d{11}(?!\d)(?![.,]\d)")
PHONE_RE = re.compile(
    r"(?<!\d)(?<!\d[.,])(?:(?:\+\s?91|0091|91|0)[\s\-.]?)?"
    r"(?:[6-9]\d{9}|[6-9]\d{4}[\s\-.]\d{5}|[6-9]\d{2}[\s\-.]\d{3}[\s\-.]\d{4}|[6-9]\d{3}[\s\-.]\d{3}[\s\-.]\d{3})(?!\d)")
_CUE = re.compile(r"aadh?aa?r|adhar|uidai|\buid\b|आधार", re.I)

_D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],
      [4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],
      [8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
      [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]


def verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def _not_isbn(folded, s, e):
    return "isbn" not in folded[max(0, s - 12):s].lower()


def _aadhaar_plain_ok(folded, s, e):
    return verhoeff_ok(folded[s:e]) or bool(_CUE.search(folded[max(0, s - 30):s]))


def _sub(regex, text, token, counts, key, validator=None):
    folded = text.translate(DIGIT_FOLD)
    out, last, n = [], 0, 0
    for m in regex.finditer(folded):
        s, e = m.span()
        if validator and not validator(folded, s, e):
            continue
        out.append(text[last:s]); out.append(token); last = e; n += 1
    if n:
        out.append(text[last:])
        counts[key] += n
        return "".join(out)
    return text


def redact(text: str):
    counts = Counter()
    text = _sub(EMAIL_RE, text, "<EMAIL>", counts, "email")
    text = _sub(PAN_RE, text, "<PAN>", counts, "pan")
    text = _sub(AADHAAR_GROUPED_RE, text, "<AADHAAR>", counts, "aadhaar")
    text = _sub(PHONE_RE, text, "<PHONE>", counts, "phone", _not_isbn)
    text = _sub(AADHAAR_PLAIN_RE, text, "<AADHAAR>", counts, "aadhaar", _aadhaar_plain_ok)
    return text, counts
