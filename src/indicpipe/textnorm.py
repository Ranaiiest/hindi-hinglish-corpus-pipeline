import re
import unicodedata

_DROP = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064,
         0xFEFF, 0x00AD, 0x180E, 0x034F, 0x061C, 0x2066, 0x2067, 0x2068, 0x2069, 0xFFFE, 0xFFFF}
_DROP.update(range(0x202A, 0x202F))
_DROP.update(range(0xFE00, 0xFE10))
_DROP.update(c for c in range(0, 32) if c not in (9, 10, 11, 12, 13))
_DROP.update(range(0x7F, 0xA0))
_TABLE = {c: None for c in _DROP}
_TABLE.update({0x09: " ", 0x0B: " ", 0x0C: " ", 0x2028: " ", 0x2029: " ",
               0x1680: " ", 0x202F: " ", 0x205F: " ", 0x3000: " ", 0x00A0: " "})
_TABLE.update({c: " " for c in range(0x2000, 0x200B)})
_TABLE[0x85] = "\n"

_PIPE_DANDA = re.compile(r"([\u0900-\u097F])( ?)\|(?=[ \n]|$)")
_SP = re.compile(r" {2,}")
_NL_SP = re.compile(r" *\n *")
_NL = re.compile(r"\n{3,}")

DIGIT_FOLD = str.maketrans("०१२३४५६७८९", "0123456789")
_KEY_STRIP = re.compile(r"[^\w\u0900-\u0963\u0966-\u097F]+")


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.translate(_TABLE)
    s = _PIPE_DANDA.sub(r"\1\2।", s)
    s = _SP.sub(" ", s)
    s = _NL_SP.sub("\n", s)
    s = _NL.sub("\n\n", s)
    return s.strip()


def text_key(s: str) -> str:
    s = normalize_text(s).casefold().translate(DIGIT_FOLD)
    return _KEY_STRIP.sub(" ", s).strip()


_MOJI = re.compile(r"(?:à[¤¥]|Ã[\u0080-\u00bf]|â€)")


def _to_bytes(s):
    out = bytearray()
    for ch in s:
        o = ord(ch)
        if o < 256:
            out.append(o)
        else:
            out += ch.encode("cp1252")
    return bytes(out)


def fix_mojibake(s: str):
    if len(_MOJI.findall(s)) < 2:
        return s, False
    try:
        fixed = _to_bytes(s).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s, False
    if len(_MOJI.findall(fixed)) < len(_MOJI.findall(s)):
        return fixed, True
    return s, False
