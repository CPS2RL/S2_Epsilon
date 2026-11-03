"""Pessimism of the GP relaxation versus searches that use the exact multi-job RTA.

For every taskset that is feasible under the deterministic scheduler, compare
noise bounds delta (all certified with the exact RTA and the stability check):

  gp          : geometric program (s2eps.solve_gp); delta = 0 if infeasible
  gp_refine   : start from the GP solution (or 0), then raise each delta_i by
                bisection while the exact check still passes (one pass,
                lowest priority first)
  greedy      : the same per-task bisection, starting from delta = 0
  uniform     : bisection on delta_i = rho * delta_max_i (as in check_conservatism.py)
  grid        : n = 5 only; exhaustive search over K values per task
                (depth-first, pruned by monotonicity), then the refine pass

Monotonicity: shortening any minimum inter-arrival time never decreases a
response time, so the feasible set is closed downward. This makes per-task
bisection and pruning valid. All searches also require a total utilization of
at most 1 - U_MARGIN; without it, a search can stop within 1e-8 of full
utilization, where the busy window becomes impractically long.

Input : data/tasksets.csv, results/per_taskset.csv (deterministic acceptance)
Output: results/pessimism/per_taskset.csv, results/pessimism/summary.csv

Usage : python pessimism.py [--workers N]
"""
import argparse
import csv
import os
import time
from collections import defaultdict
from multiprocessing import Pool

import numpy as np

from check_conservatism import exact_ok, unpack
from run_experiments import load_tasksets
from s2eps import certify, solve_gp

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results", "pessimism")
TOL = 1e-3              # bisection stops when the bracket is below TOL * delta_max_i
K = 6                   # grid values per task for the exhaustive search (n = 5)
GRID_N = 5
NONZERO = 1e-6          # same threshold as run_experiments.py
U_MARGIN = 1e-4        # searches keep sum C_i / (T_i - delta_i) <= 1 - U_MARGIN
METHODS = ("gp", "gp_refine", "greedy", "uniform", "grid")


def ok(C, T, D, ctrl, delta):
    """Exact schedulability and stability check with the utilization margin."""
    return float(np.sum(C / (T - delta))) <= 1.0 - U_MARGIN and exact_ok(C, T, D, ctrl, delta)


def uniform_search(C, T, D, ctrl, dmax):
    """Largest rho (up to TOL) such that delta = rho * delta_max passes the check."""
    if ok(C, T, D, ctrl, dmax):
        return 1.0
    lo, hi = 0.0, 1.0
    while hi - lo > TOL:
        mid = 0.5 * (lo + hi)
        if ok(C, T, D, ctrl, mid * dmax):
            lo = mid
        else:
            hi = mid
    return lo


def refine(C, T, D, ctrl, dmax, delta):
    """One pass, lowest priority first: raise delta_i as far as the exact check allows."""
    delta = np.array(delta, float)
    for i in reversed(range(len(C))):
        lo, hi = delta[i], dmax[i]
        trial = delta.copy(); trial[i] = hi
        if ok(C, T, D, ctrl, trial):
            delta[i] = hi
            continue
        while hi - lo > TOL * dmax[i]:
            mid = 0.5 * (lo + hi)
            trial[i] = mid
            if ok(C, T, D, ctrl, trial):
                lo = mid
            else:
                hi = mid
        delta[i] = lo
    return delta


def grid_search(C, T, D, ctrl, dmax):
    """Best weighted noise over the grid {0, 1/(K-1), ..., 1} * delta_max_i."""
    n = len(C)
    levels = np.linspace(0.0, 1.0, K)
    best = [np.zeros(n), 0.0]

    def dfs(i, delta):
        if i == n:
            val = float(np.sum(delta / T))
            if val > best[1]:
                best[0], best[1] = delta.copy(), val
            return
        for lv in levels:
            delta[i] = lv * dmax[i]
            # remaining tasks at zero noise: if this fails, every extension fails
            if lv > 0 and not ok(C, T, D, ctrl, delta):
                break
            dfs(i + 1, delta)
        delta[i] = 0.0

    dfs(0, np.zeros(n))
    return refine(C, T, D, ctrl, dmax, best[0])


def evaluate(item):
    key, rows = item
    C, T, D, ctrl, dmax = unpack(rows)
    res, tim = {}, {}

    t0 = time.perf_counter()
    d = solve_gp(C, T, D, ctrl, dmax)
    tim["gp"] = time.perf_counter() - t0
    gp_ok = d is not None
    res["gp"] = d if gp_ok else np.zeros(len(C))

    t0 = time.perf_counter()
    res["gp_refine"] = refine(C, T, D, ctrl, dmax, res["gp"])
    tim["gp_refine"] = tim["gp"] + time.perf_counter() - t0

    t0 = time.perf_counter()
    res["greedy"] = refine(C, T, D, ctrl, dmax, np.zeros(len(C)))
    tim["greedy"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    rho = uniform_search(C, T, D, ctrl, dmax)
    res["uniform"] = rho * dmax
    tim["uniform"] = time.perf_counter() - t0

    if len(C) == GRID_N:
        t0 = time.perf_counter()
        res["grid"] = grid_search(C, T, D, ctrl, dmax)
        tim["grid"] = time.perf_counter() - t0

    row = {"n_tasks": key[0], "utilization": key[1], "taskset_id": key[2], "gp_feasible": gp_ok}
    for m in METHODS:
        if m not in res:
            row.update({f"{m}_noise_pct": "", f"{m}_nonzero": "", f"{m}_time_s": ""})
            continue
        # independent check with the reference implementation of the exact RTA
        dl, st, _ = certify(C, D, T - res[m], ctrl)
        if not (dl and st):
            raise AssertionError(f"{key}: {m} solution fails the reference check")
        row[f"{m}_noise_pct"] = 100.0 * float(np.mean(res[m] / T))
        row[f"{m}_nonzero"] = bool(np.any(res[m] / T > NONZERO))
        row[f"{m}_time_s"] = tim[m]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--limit", type=int, default=0, help="tasksets per (n, U), for quick tests")
    args = ap.parse_args()

    sets = load_tasksets(os.path.join(HERE, "data", "tasksets.csv"))
    det = {(int(r["n_tasks"]), float(r["utilization"]), int(r["taskset_id"]))
           for r in csv.DictReader(open(os.path.join(HERE, "results", "per_taskset.csv")))
           if r["det_accept"] == "True" and float(r["utilization"]) <= 0.8 + 1e-9}
    items = sorted((k, v) for k, v in sets.items() if k in det)
    if args.limit:
        count = defaultdict(int)
        items = [it for it in items if (count.__setitem__(it[0][:2], count[it[0][:2]] + 1)
                                        or count[it[0][:2]] <= args.limit)]

    rows = []
    with Pool(args.workers) as pool:
        for k, row in enumerate(pool.imap_unordered(evaluate, items, chunksize=2)):
            rows.append(row)
            if (k + 1) % 500 == 0:
                print(f"{k + 1}/{len(items)} tasksets", flush=True)
    rows.sort(key=lambda r: (r["n_tasks"], r["utilization"], r["taskset_id"]))

    summary = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["n_tasks"], r["utilization"])].append(r)
    for (n, u), g in sorted(groups.items()):
        s = {"n_tasks": n, "utilization": u, "det_feasible": len(g)}
        for m in METHODS:
            vals = [r for r in g if r[f"{m}_noise_pct"] != ""]
            if not vals:
                continue
            s[f"{m}_noise_pct_mean"] = round(float(np.mean([r[f"{m}_noise_pct"] for r in vals])), 2)
            s[f"{m}_nonzero_pct"] = round(100.0 * float(np.mean([r[f"{m}_nonzero"] for r in vals])), 1)
            s[f"{m}_time_ms_mean"] = round(1e3 * float(np.mean([r[f"{m}_time_s"] for r in vals])), 2)
        summary.append(s)

    os.makedirs(OUT, exist_ok=True)
    for name, data in (("per_taskset.csv", rows), ("summary.csv", summary)):
        fields = list(dict.fromkeys(k for r in data for k in r))
        with open(os.path.join(OUT, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(data)
    print(f"done: {len(rows)} tasksets; all solutions passed the reference check")


if __name__ == "__main__":
    main()
