import zlib

import numpy as np

_P = 4294967311


class MinHasher:
    def __init__(self, num_perm=128, seed=1):
        rs = np.random.RandomState(seed)
        self.a = rs.randint(1, 2 ** 31 - 1, size=num_perm).astype(np.uint64)
        self.b = rs.randint(0, 2 ** 31 - 1, size=num_perm).astype(np.uint64)

    def signature(self, shingles):
        if not shingles:
            return None
        arr = np.unique(np.fromiter((zlib.crc32(s.encode("utf-8")) for s in shingles),
                                    dtype=np.uint64, count=len(shingles)))
        sig = None
        for i in range(0, len(arr), 4096):
            h = (arr[i:i + 4096, None] * self.a[None, :] + self.b[None, :]) % np.uint64(_P)
            m = h.min(axis=0)
            sig = m if sig is None else np.minimum(sig, m)
        return sig


def word_shingles(key, n):
    w = key.split()
    if not w:
        return []
    if len(w) < n:
        return [" ".join(w)]
    return list({" ".join(w[i:i + n]) for i in range(len(w) - n + 1)})


def est_jaccard(a, b):
    return float(np.mean(a == b))


class LSH:
    def __init__(self, bands, rows, max_bucket=50):
        self.bands, self.rows, self.max_bucket = bands, rows, max_bucket
        self.tables = [dict() for _ in range(bands)]

    def _keys(self, sig):
        r = self.rows
        return [sig[i * r:(i + 1) * r].tobytes() for i in range(self.bands)]

    def query(self, sig, limit=200):
        cand = set()
        for t, k in zip(self.tables, self._keys(sig)):
            b = t.get(k)
            if b:
                cand.update(b[: self.max_bucket])
        return sorted(cand)[:limit]

    def add(self, idx, sig):
        for t, k in zip(self.tables, self._keys(sig)):
            t.setdefault(k, []).append(idx)
