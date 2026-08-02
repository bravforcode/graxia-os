"""Benchmark turbovec (TurboQuantIndex / IdMapIndex) with real quant_os market data.

Usage:
    python scripts/bench_turbovec.py [--n 100000] [--bit-width 4] [--k 10] [--queries 1000]

Builds fixed-dim feature vectors from real OHLCV rows (data/canonical/XAUUSD_D1_clean.csv
plus any data/*.csv on disk), then measures:
  - add rate (vectors/s)
  - prepare time
  - search p50/p95 latency
  - recall@1 vs brute-force numpy (L2)
  - write/load round-trip correctness
  - IdMapIndex add_with_ids / contains / allowlist search / remove
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import time

import numpy as np
from turbovec import IdMapIndex, TurboQuantIndex

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIMARY = os.path.join(BASE, "data", "canonical", "XAUUSD_D1_clean.csv")
EXTRA_GLOBS = [os.path.join(BASE, "data", "*.csv"), os.path.join(BASE, "data", "canonical", "*.csv")]
OUT = os.path.join(BASE, "artifacts", "turbovec_bench.json")


def load_rows(limit: int) -> np.ndarray:
    """Load up to `limit` OHLCV rows from real files -> float matrix [N, 6]."""
    rows: list[list[float]] = []
    sources: list[str] = []
    paths = [PRIMARY]
    for g in EXTRA_GLOBS:
        for p in sorted(glob.glob(g)):
            if p not in paths:
                paths.append(p)
    for p in paths:
        if len(rows) >= limit:
            break
        try:
            with open(p, encoding="utf-8") as f:
                r = csv.reader(f)
                hdr = next(r)
                col_idx = {c: i for i, c in enumerate(hdr)}
                need = ["open", "high", "low", "close"]
                if not all(c in col_idx for c in need):
                    continue
                oi, hi, li, ci = (col_idx[c] for c in need)
                vi = col_idx.get("volume")
                for line in r:
                    if len(rows) >= limit:
                        break
                    try:
                        o = float(line[oi])
                        h = float(line[hi])
                        lo = float(line[li])
                        c = float(line[ci])
                        v = float(line[vi]) if vi is not None else 0.0
                        if h < lo or o <= 0 or c <= 0:
                            continue
                        rows.append([o, h, lo, c, v])
                    except (ValueError, IndexError):
                        continue
        except OSError:
            continue
        sources.append(os.path.basename(p))
    if not rows:
        raise SystemExit(f"no data found; looked at {paths}")
    return np.asarray(rows, dtype=np.float64), sources


def build_features(ohlcv: np.ndarray, mode: int = 8) -> np.ndarray:
    """Normalized features per bar.

    mode=8  -> per-bar 8-dim: o,h,l,c,v, body, range, pct return (z-scored, L2-normalized).
    mode=100 -> 20-bar sliding window of (return, body/close, range/close, volume) x20 = 80-dim
                + 20-bar momentum stats (z-scored, L2-normalized).
    """
    o = ohlcv[:, 0]
    h = ohlcv[:, 1]
    lo = ohlcv[:, 2]
    c = ohlcv[:, 3]
    v = ohlcv[:, 4]
    if mode == 8:
        body = c - o
        rng = h - lo
        ret = np.zeros_like(c)
        ret[1:] = np.diff(c) / c[:-1]
        feats = np.column_stack([o, h, lo, c, v, body, rng, ret])
    else:
        ret = np.zeros_like(c)
        ret[1:] = np.diff(c) / c[:-1]
        body_r = np.zeros_like(c)
        body_r[1:] = (c[1:] - o[1:]) / c[1:]
        rng_r = np.zeros_like(c)
        rng_r[1:] = (h[1:] - lo[1:]) / c[1:]
        vol_r = np.zeros_like(c)
        vol_r[1:] = v[1:] / np.maximum(v[:-1], 1e-9)
        cols = [ret, body_r, rng_r, vol_r]
        n_w = ohlcv.shape[0]
        n_feat = 20 * 4
        feats = np.zeros((n_w, n_feat), dtype=np.float64)
        for i in range(20):
            for j, col in enumerate(cols):
                if i == 0:
                    feats[:, j] = col
                else:
                    feats[i:, j + 4 * i] = col[:-i]
        feats = feats[19:]  # drop warm-up rows
    # per-feature z-score (drop constant cols -> keep 0)
    mu = feats.mean(axis=0)
    sd = feats.std(axis=0)
    sd[sd == 0] = 1.0
    feats = (feats - mu) / sd
    # L2-normalize: turbovec ranks by inner product -> unit vectors make dot == cosine
    # similarity and keep self-hit == exact nearest neighbor.
    norms = np.linalg.norm(feats, axis=1)
    norms[norms == 0] = 1.0
    feats = feats / norms[:, None]
    return np.ascontiguousarray(feats, dtype=np.float32)


def brute_top1(feats: np.ndarray, queries: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Exact L2 nearest-neighbor labels (global, ignoring idx mask) — used only for recall sanity."""
    # limit brute-force size for speed: if feats big, restrict to nearest 20k random + idx
    # For this benchmark the index contains ALL vectors, so exact global argmin is right.
    d = np.linalg.norm(feats[None, :, :] - queries[:, None, :], axis=2)  # [Q, N]
    return d.argmin(axis=1)


def pct(vals, p: float) -> float:
    s = sorted(float(x) for x in vals)
    if not s:
        return 0.0
    i = min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))
    return s[i]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100_000, help="max rows to index")
    ap.add_argument("--bit-width", type=int, default=4, choices=[2, 3, 4])
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--queries", type=int, default=1000)
    ap.add_argument(
        "--dim-feature",
        type=int,
        default=8,
        choices=[8, 80],
        help="8 = per-bar features; 80 = 20-bar sliding-window features (4 cols x 20)",
    )
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    t0 = time.perf_counter()
    ohlcv, sources = load_rows(args.n)
    feats = build_features(ohlcv, args.dim_feature)
    # dedupe: many real OHLCV bars share identical feature vectors -> distorts index-level recall
    feats = np.unique(feats, axis=0)
    n, dim = feats.shape
    q = min(args.queries, n)
    rng = np.random.default_rng(42)
    q_idx = rng.choice(n, size=q, replace=False)
    queries = feats[q_idx]

    res: dict = {
        "n": n,
        "dim": dim,
        "bit_width": args.bit_width,
        "k": args.k,
        "sources": sources,
        "load_sec": round(time.perf_counter() - t0, 3),
    }
    # ---- brute-force baselines (chunked to bound RAM; exact dot argmax + exact L2 argmin) ----
    tb = time.perf_counter()
    chunk = 100
    exact_dot = np.empty(q, dtype=np.int64)
    exact_l2 = np.empty(q, dtype=np.int64)
    for s in range(0, q, chunk):
        qs = queries[s : s + chunk]
        dots = feats @ qs.T  # [N, chunk]
        exact_dot[s : s + chunk] = dots.argmax(axis=0)
        del dots
        l2 = np.linalg.norm(feats[None] - qs[:, None], axis=2)  # [chunk, N]
        exact_l2[s : s + chunk] = l2.argmin(axis=1)
        del l2
    res["bruteforce_q1000_sec"] = round(time.perf_counter() - tb, 3)
    # self-hit sanity: exact_dot / exact_l2 must equal the query index for unique vectors
    res["exact_dot_selfhit"] = float(np.mean(exact_dot == q_idx))
    res["exact_l2_selfhit"] = float(np.mean(exact_l2 == q_idx))

    # ---- per-bit-width sweep: build/search/recall ----
    res["bit_widths"] = {}
    for bw in (2, 3, 4):
        idx = TurboQuantIndex(dim=dim, bit_width=bw)
        ta = time.perf_counter()
        idx.add(feats)
        add_sec = time.perf_counter() - ta
        tp = time.perf_counter()
        idx.prepare()
        prepare_sec = time.perf_counter() - tp
        ts = time.perf_counter()
        out = idx.search(queries, args.k)
        search_q_sec = time.perf_counter() - ts
        dists, ids = out
        dists = np.asarray(dists)
        ids = np.asarray(ids)
        lat = []
        for qq in queries[: min(200, q)]:
            t1 = time.perf_counter()
            idx.search(qq.reshape(1, -1), args.k)
            lat.append((time.perf_counter() - t1) * 1000)

        r1 = float(np.mean(ids[:, 0] == exact_dot))
        r5 = float(np.mean([exact_dot[i] in ids[i] for i in range(q)]))
        # non-self distance quality: top-1 dist vs exact 2nd-nearest (self excluded), chunked
        d2 = np.empty(q)
        for s in range(0, q, chunk):
            qs = queries[s : s + chunk]
            d_all = np.linalg.norm(feats[None] - qs[:, None], axis=2)
            d_all[np.arange(d_all.shape[0]), exact_dot[s : s + d_all.shape[0]]] = np.inf
            d2[s : s + chunk] = d_all.min(axis=1)
            del d_all
        d_top = np.linalg.norm(feats[ids[:, 0]] - queries, axis=1)
        ratio = d_top / np.maximum(d2, 1e-6)

        res["bit_widths"][str(bw)] = {
            "add_sec": round(add_sec, 3),
            "add_rate_vectors_per_s": int(n / max(add_sec, 1e-9)),
            "prepare_sec": round(prepare_sec, 3),
            "search_q_sec": round(search_q_sec, 3),
            "per_query_ms_p50": round(pct(lat, 50), 3),
            "per_query_ms_p95": round(pct(lat, 95), 3),
            "per_query_ms_max": round(max(lat), 3),
            "recall@1": round(r1, 4),
            "recall@5": round(r5, 4),
            "top1_2nd_dist_ratio_p50": round(pct(list(ratio), 50), 4),
        }

    # ---- write/load round-trip (bit_width=4, the sweet spot) ----
    idx = TurboQuantIndex(dim=dim, bit_width=4)
    idx.add(feats)
    idx.prepare()
    _, ids = idx.search(queries[: min(50, q)], args.k)
    tmp = os.path.join(BASE, "artifacts", "turbovec_tmp.bin")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    idx.write(tmp)
    res["index_bytes_bw4"] = os.path.getsize(tmp)
    idx2 = TurboQuantIndex(bit_width=4).load(tmp)
    out2 = idx2.search(queries[: min(50, q)], args.k)
    same = np.array_equal(np.asarray(out2[1]), np.asarray(ids))
    res["roundtrip_ids_equal"] = bool(same)
    os.remove(tmp)

    # ---- IdMapIndex: ids + allowlist + contains + remove ----
    im = IdMapIndex(dim=dim, bit_width=args.bit_width)
    ids_full = np.arange(n, dtype=np.uint64)
    im.add_with_ids(feats, ids_full)
    im.prepare()
    res["idmap_contains_existing"] = bool(im.contains(0))
    res["idmap_contains_missing"] = bool(im.contains(n + 999))
    allow = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.uint64)
    out3 = im.search(queries[: min(50, q)], args.k, allowlist=allow)
    res["idmap_allowlist_max_id"] = int(np.asarray(out3[1]).max()) if len(np.asarray(out3[1])) else None
    im.remove(int(ids_full[0]))
    res["idmap_removed_gone"] = bool(not im.contains(0))

    res["status"] = "ok"
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2, default=str))
    print("saved ->", args.out)


if __name__ == "__main__":
    main()
