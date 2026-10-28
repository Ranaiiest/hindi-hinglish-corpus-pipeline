import copy
import hashlib
import json

DEFAULTS = {
    "text_fields": ["text", "content", "raw_content", "body", "sentence",
                    "document", "article", "review", "message", "comment"],
    "txt_mode": "lines",
    "keep_langs": ["hi", "hi-Latn"],
    "langid": {
        "dev_min_frac": 0.40,
        "dev_mixed_frac": 0.15,
        "marker_min_hits": 2,
        "marker_min_rate": 0.02,
        "latn_hi_min_hits": 2,
        "latn_hi_min_rate": 0.06,
        "latn_hi_vs_en": 0.4,
        "latn_en_min_rate": 0.15,
    },
    "quality": {
        "min_letters": 6,
        "min_words": 2,
        "min_alpha_frac": 0.40,
        "boilerplate_doc_frac": 0.50,
        "boilerplate_line_maxlen": 100,
        "spam_distinct": 3,
        "spam_density": 0.03,
        "url_min": 3,
        "contact_phones_min": 3,
        "contact_maxlen": 1500,
        "symbol_frac": 0.35,
        "max_top_token_share": 0.25,
        "min_tokens_for_repeat_checks": 30,
        "min_unique_line_ratio": 0.30,
        "min_lines_for_line_check": 8,
        "max_char_run_frac": 0.30,
        "numeric_table_min_tokens": 6,
        "numeric_table_frac": 0.80,
        "max_latin1_frac": 0.10,
        "max_replacement_chars": 2,
        "max_markup_tags": 3,
        "max_markup_frac": 0.05,
    },
    "dedup": {
        "num_perm": 128, "bands": 32, "rows": 4,
        "shingle_words": 3,
        "threshold": 0.80,
        "log_floor": 0.60,
        "seed": 1,
        "max_bucket": 50,
        "max_candidates": 200,
    },
    "eval": {
        "purpose": "held-out Hindi / Hinglish passages for measuring Falcon's per-token loss (perplexity) and "
                   "next-token quality on Indian-language text",
        "quota": {"hi": 160, "hi-Latn": 40},
        "oversample": 6,
        "min_words": 8, "min_chars": 60, "max_chars": 600,
        "seed": "eval-v1",
    },
    "contamination": {
        "gram_words": 5,
        "containment": 0.50,
        "reject_floor": 0.25,
        "translit_gram": 4,
        "translit_containment": 0.50,
        "translit_min_words": 8,
    },
    "output": {"shard_docs": 50000},
}

STAGE_KEYS = {
    "s1": ["text_fields", "txt_mode", "keep_langs", "langid", "quality", "eval"],
    "s2": ["eval"],
    "s3": ["dedup"],
    "s4": ["contamination"],
    "final": ["output"],
}


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, encoding="utf-8") as f:
            _merge(cfg, json.load(f))
    d = cfg["dedup"]
    assert d["bands"] * d["rows"] == d["num_perm"], "bands*rows must equal num_perm"
    return cfg


def subset_hash(cfg, keys):
    blob = json.dumps({k: cfg[k] for k in keys}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()
