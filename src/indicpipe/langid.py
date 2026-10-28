import re

_NOT_DEV = re.compile(r"[^\u0900-\u0963\u0971-\u097F]+")
_NOT_DEV_BASE = re.compile(r"[^\u0904-\u0939\u0958-\u0961\u0972-\u097F]+")
_NOT_LAT = re.compile(r"[^A-Za-z\u00c0-\u024f]+")
_NON_LETTER = re.compile(r"[\W\d_]+")
_WS = re.compile(r"\s+")
_NOT_DIGIT = re.compile(r"[^0-9\u0966-\u096F]+")
DEV_TOKEN = re.compile(r"[\u0900-\u0963\u0971-\u097F]+")
LAT_TOKEN = re.compile(r"[a-z]+")

HI_DEV = set("है हैं का की के में और से को पर यह वह था थी थे नहीं कि एक भी लिए हो रहा रही रहे गया गई गए किया करने इस उस तो जो कर "
             "अपने हम आप मैं वे सकता होता जाता द्वारा साथ बाद वर्ष लेकिन क्योंकि तक कुछ सभी जाते जाती होती करते करता".split())
MR_DEV = set("आहे आहेत आणि नाही नाहीत मध्ये च्या ची चे झाले झाली झाला केले केली केला करून त्यांनी असून म्हणून येथे आपल्या".split())
NE_DEV = set("छ छन् हुन्छ गर्न गरेको भएको थियो भयो छैन भन्ने लाई बाट सँग हुने गर्ने लागि".split())

HI_LAT = set(("hai hain nahi nahin nhi kya kyu kyun kyon mera meri mere tera teri tere aap aapka aapki tum tumhara hum humara "
              "mujhe tujhe tumhe unka uski uska iska iski yeh woh wo aur lekin magar bhi toh hoga hogi honge thi raha rahi rahe "
              "kar karo karna karte karta karti kiya kuch koi sab abhi jaise kaise kaisa kaun kahan kab kitna bahut accha acha "
              "achha bohot bahot yaar bhai dost jao aao chalo dekho suno bolo batao sirf hoon hun jab tab wala wali wale zindagi "
              "pyaar pyar dil log lagta lagti chahiye sakta sakti sakte milta mila gaya gayi gaye liye isliye kyunki phir fir "
              "agar bas thoda zyada jyada bilkul shayad haan nahi sath saath baad pehle pehla yahan wahan wahi yahi aisa aise "
              "waise jaisa mein mujhko ka ki ke ko se ne").split())

EN = set(("the is are was were and of to in that it for with as on this be by at from or an have has had not you your we "
          "they he she his her their will would can could which what who all been more about if but so there one when these than").split())


def _count(pat, s):
    return len(pat.sub("", s))


def script_stats(s):
    dev = _count(_NOT_DEV, s)
    dev_base = _count(_NOT_DEV_BASE, s)
    lat = _count(_NOT_LAT, s)
    alpha = len(_NON_LETTER.sub("", s))
    return {"dev": dev, "dev_base": dev_base, "lat": lat,
            "other": max(0, alpha - dev_base - lat),
            "digits": _count(_NOT_DIGIT, s), "nonspace": len(_WS.sub("", s))}


def detect(text, cfg):
    st = script_stats(text)
    total = st["dev"] + st["lat"] + st["other"]
    if total < 3:
        return "other", st
    if st["dev"] / total >= cfg["dev_min_frac"]:
        toks = DEV_TOKEN.findall(text)
        n = max(1, len(toks))
        h = sum(t in HI_DEV for t in toks)
        m = sum(t in MR_DEV for t in toks)
        ne = sum(t in NE_DEV for t in toks)
        o = max(m, ne)
        if o >= cfg["marker_min_hits"] and o > h and o / n >= cfg["marker_min_rate"]:
            return "other", st
        return "hi", st
    if st["other"] / total >= 0.5:
        return "other", st
    if st["dev"] / total >= cfg["dev_mixed_frac"]:

        if sum(t in HI_DEV for t in DEV_TOKEN.findall(text)) >= 1:
            return "hi", st
    toks = LAT_TOKEN.findall(text.lower())
    n = len(toks)
    if n == 0:
        return "other", st
    hl = sum(t in HI_LAT for t in toks)
    en = sum(t in EN for t in toks)
    if n < 3:
        return ("hi-Latn" if hl >= 1 else "other"), st
    if hl >= cfg["latn_hi_min_hits"] and hl / n >= cfg["latn_hi_min_rate"] and hl >= cfg["latn_hi_vs_en"] * en:
        return "hi-Latn", st
    if en / n >= cfg["latn_en_min_rate"]:
        return "en", st
    return "other", st
