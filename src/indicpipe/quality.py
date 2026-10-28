import re
from collections import Counter

from .textnorm import DIGIT_FOLD

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]{0,20}(?:\s[^<>]{0,300})?/?>")
ENTITY_RE = re.compile(r"&(?:nbsp|amp|lt|gt|quot|#\d{2,5}|#x[0-9a-f]{2,4});", re.I)
WIKI_RE = re.compile(r"\{\{|\}\}|\[\[|\]\]|^\s*\|-|^\s*\{\|", re.M)
MOJI_RE = re.compile(r"(?:à[¤¥]|Ã[\u0080-\u00bf]|â€)")
LATIN1_RE = re.compile(r"[\u00c0-\u00ff]")
DEV_BAD_START = re.compile(r"(?:^|\s)[\u0900-\u0903\u093A-\u094D\u0951-\u0957]")
PHONEISH = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
NUM_TOKEN = re.compile(r"^[()\[\]+\-−–₹$%.,:;/0-9]*[0-9][()\[\]+\-−–₹$%.,:;/0-9]*$")
CHAR_RUN = re.compile(r"(.)\1{9,}")
SYMBOLS = re.compile(r"[\w\s\u0900-\u097F]+")

SPAM_LAT = re.compile(
    r"\b(?:viagra|casino|betting|bet365|jackpot|satta|matka|lottery|vashikaran|love problem|black magic|baba ?ji|"
    r"astrologer|call girls?|escort|porn|xxx|sex video|earn money|work from home|click here|free download|"
    r"whatsapp (?:me|now|no)|buy now|best price|loan approval|dating|slot machine|rummy|teen patti)\b", re.I)
SPAM_DEV = ["वशीकरण", "सट्टा", "मटका", "कॉल गर्ल", "लॉटरी", "जैकपॉट", "घर बैठे कमाएं", "ऑनलाइन कमाई", "रमी", "तीन पत्ती",
            "फ्री डाउनलोड", "यहाँ क्लिक करें", "यहां क्लिक करें", "काला जादू", "लव प्रॉब्लम"]

BOILER_START = re.compile(
    r"^\s*(?:copyright|©|all rights reserved|privacy policy|terms (?:of|and) (?:use|service|conditions)|cookie|subscribe|"
    r"follow us|share (?:on|this|via)|read more|click here|sign in|log ?in|related (?:posts?|articles?|news)|advertisement|"
    r"skip to|home\s*[|»>]|tags?:|posted (?:by|on)|leave a (?:reply|comment)|"
    r"सर्वाधिकार सुरक्षित|अधिक पढ़ें|और पढ़ें|ये भी पढ़ें|यह भी पढ़ें|इसे भी पढ़ें|हमें फॉलो करें|विज्ञापन|शेयर करें|"
    r"गोपनीयता नीति|कुकी|सब्सक्राइब|लॉग ?इन|डाउनलोड करें|संपादित करें|टिप्पणी करें)", re.I)
BOILER_ANY = re.compile(r"all rights reserved|सर्वाधिकार सुरक्षित|privacy policy|गोपनीयता नीति", re.I)


def is_numeric_table(text, q):
    toks = text.split()
    if len(toks) < q["numeric_table_min_tokens"]:
        return False
    nums = sum(1 for t in toks if NUM_TOKEN.match(t.translate(DIGIT_FOLD)))
    return nums / len(toks) >= q["numeric_table_frac"]


def strip_boilerplate(text, q):

    lines = text.split("\n")
    keep, removed, nonempty = [], 0, 0
    for ln in lines:
        if not ln.strip():
            keep.append(ln); continue
        nonempty += 1
        if len(ln) <= q["boilerplate_line_maxlen"] and (BOILER_START.match(ln) or BOILER_ANY.search(ln)):
            removed += 1
        else:
            keep.append(ln)
    frac = removed / nonempty if nonempty else 0.0
    return "\n".join(keep).strip(), removed, frac


def check(text, lang, st, q, numeric):

    notes = {}
    n = len(text)
    folded = text.translate(DIGIT_FOLD)


    tags = len(TAG_RE.findall(text))
    tag_chars = sum(len(m) for m in TAG_RE.findall(text))
    junk = len(ENTITY_RE.findall(text)) + len(WIKI_RE.findall(text))
    if tags >= q["max_markup_tags"] or (n and tag_chars / n > q["max_markup_frac"]) or junk >= 5:
        return False, "markup", text, notes
    braces = sum(text.count(c) for c in "{}<>;=")
    if n > 40 and braces / n > 0.05 and st["lat"] > 0 and st["dev"] == 0:
        return False, "markup", text, notes


    if len(MOJI_RE.findall(text)) >= 2:
        return False, "garbled_encoding", text, notes
    if text.count("\ufffd") >= q["max_replacement_chars"]:
        return False, "garbled_encoding", text, notes
    if st["lat"] and len(LATIN1_RE.findall(text)) / max(1, st["lat"]) > q["max_latin1_frac"]:
        return False, "garbled_encoding", text, notes
    toks = text.split()
    if st["dev"] and toks and len(DEV_BAD_START.findall(text)) / len(toks) > 0.10:
        return False, "garbled_encoding", text, notes
    if n > 30 and text.count("?") / n > 0.30:
        return False, "garbled_encoding", text, notes


    text2, removed, frac = strip_boilerplate(text, q)
    if removed:
        notes["boilerplate_lines_removed"] = removed
        if frac >= q["boilerplate_doc_frac"] or not text2:
            return False, "boilerplate", text, notes
        text = text2
        toks = text.split()
        folded = text.translate(DIGIT_FOLD)
        n = len(text)


    letters = st["dev_base"] + st["lat"] + st["other"]
    if numeric:
        notes["numeric_table"] = True
    else:
        if letters < q["min_letters"] or len(toks) < q["min_words"]:
            return False, "too_short", text, notes
        alpha_like = st["dev"] + st["lat"] + st["other"]
        if st["nonspace"] and alpha_like / st["nonspace"] < q["min_alpha_frac"]:
            return False, "low_letter_ratio", text, notes


    low = text.lower()
    hits = SPAM_LAT.findall(low) + [w for w in SPAM_DEV if w in text]
    if hits:
        distinct = len(set(hits))
        if distinct >= q["spam_distinct"] or (len(hits) >= 2 and len(hits) / max(1, len(toks)) >= q["spam_density"]):
            return False, "spam_keywords", text, notes
    urls = URL_RE.findall(text)
    if len(urls) >= q["url_min"] and (len(urls) / max(1, len(toks)) > 0.10 or sum(map(len, urls)) / max(1, n) > 0.25):
        return False, "url_spam", text, notes
    if n <= q["contact_maxlen"] and len(PHONEISH.findall(folded)) >= q["contact_phones_min"]:
        return False, "contact_spam", text, notes
    if not numeric and st["nonspace"] >= 20:
        sym = len(SYMBOLS.sub("", text))
        if sym / st["nonspace"] > q["symbol_frac"]:
            return False, "symbol_heavy", text, notes


    if len(toks) >= q["min_tokens_for_repeat_checks"] and not numeric:
        cnt = Counter(t.casefold() for t in toks)
        if cnt.most_common(1)[0][1] / len(toks) > q["max_top_token_share"]:
            return False, "repetitive", text, notes
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) >= q["min_lines_for_line_check"] and not numeric:
        if len(set(lines)) / len(lines) < q["min_unique_line_ratio"]:
            return False, "repeated_lines", text, notes
    run_chars = sum(len(m.group(0)) for m in CHAR_RUN.finditer(text))
    if n > 30 and run_chars / n > q["max_char_run_frac"]:
        return False, "repetitive", text, notes
    return True, "", text, notes
