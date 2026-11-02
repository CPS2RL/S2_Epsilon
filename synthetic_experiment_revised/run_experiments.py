"""Synthetic experiments of Sec. VI (Figs. 4-6) for the deterministic scheduler,
the S2eps-Scheduler, and the epsilon-Scheduler.

Input : data/tasksets.csv (one row per task)
Output: results/per_taskset.csv (one row per taskset)
        results/s2eps_bounds.csv (noise bound of every task)

Usage : python run_experiments.py [--workers N]
"""
import argparse
import csv
import math
import os
from collections import defaultdict
from multiprocessing import Pool

import numpy as np

from s2eps import certify, solve_gp

HERE = os.path.dirname(os.path.abspath(__file__))
LAMBDA = 160.0          # protection duration in ms (Table III)
NONZERO = 1e-6          # delta_i / T_i above this counts as randomized


def load_tasksets(path):
    sets = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            key = (int(r["n_tasks"]), float(r["utilization"]), int(r["taskset_id"]))
            sets[key].append(r)
    return sets


def evaluate(item):
    key, rows = item
    # rate-monotonic priority order (ties broken by task id)
    rows = sorted(rows, key=lambda r: (float(r["T_ms"]), int(r["task_id"])))
    C = [float(r["C_ms"]) for r in rows]
    T = [float(r["T_ms"]) for r in rows]
    D = [float(r["D_ms"]) for r in rows]
    lo = [float(r["eps_low_ms"]) for r in rows]
    hi = [float(r["eps_high_ms"]) for r in rows]
    ctrl = [k for k, r in enumerate(rows) if r["control"] == "True"][0]
    dmax = [min(T[k] - lo[k], hi[k] - T[k]) for k in range(len(T))]

    # deterministic scheduler: S_j = T_j
    det_dl, det_st, _ = certify(C, D, T, ctrl)
    det_ok = det_dl and det_st

    # epsilon-Scheduler with the designer-given bounds: S_j = T_j^perp
    eps_dl, eps_st, _ = certify(C, D, lo, ctrl)

    # S2eps-Scheduler: geometric program (Eq. (24)); fallback delta = 0
    delta = solve_gp(C, T, D, ctrl, dmax)
    gp_feasible = delta is not None
    if not gp_feasible:
        delta = np.zeros(len(T))
    S = [T[k] - delta[k] for k in range(len(T))]
    s2_dl, s2_st, _ = certify(C, D, S, ctrl)   # independent check of the GP solution
    randomized = gp_feasible and bool(np.any(delta / np.array(T) > NONZERO))

    row = {
        "n_tasks": key[0], "utilization": key[1], "taskset_id": key[2],
        "control_priority": ctrl + 1,
        "det_deadline": det_dl, "det_stability": det_st, "det_accept": det_ok,
        "eps_deadline": eps_dl, "eps_stability": eps_st, "eps_accept": eps_dl and eps_st,
        "s2_gp_feasible": gp_feasible, "s2_randomized": randomized,
        "s2_deadline": s2_dl, "s2_stability": s2_st, "s2_accept": s2_dl and s2_st,
        # noise percentage 100/|Gamma| sum delta_i / T_i (Sec. VI-B2)
        "eps_noise_pct": 100.0 * float(np.mean([dmax[k] / T[k] for k in range(len(T))])),
        "s2_noise_pct": 100.0 * float(np.mean(delta / np.array(T))),
        # protected job count max_i ceil(lambda / min inter-arrival), Eqs. (26)-(27)
        "eps_jobs": max(math.ceil(LAMBDA / lo[k] - 1e-9) for k in range(len(T))),
        "s2_jobs": max(math.ceil(LAMBDA / S[k] - 1e-9) for k in range(len(T))),
    }
    bounds = [{"n_tasks": key[0], "utilization": key[1], "taskset_id": key[2],
               "task_id": rows[k]["task_id"], "priority": k + 1, "control": rows[k]["control"],
               "T_ms": T[k], "delta_max_ms": dmax[k], "delta_ms": float(delta[k])}
              for k in range(len(T))]
    return row, bounds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()

    sets = load_tasksets(os.path.join(HERE, "data", "tasksets.csv"))
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    rows, bounds = [], []
    with Pool(args.workers) as pool:
        for k, (row, b) in enumerate(pool.imap_unordered(evaluate, sorted(sets.items()), chunksize=8)):
            rows.append(row); bounds.extend(b)
            if (k + 1) % 1000 == 0:
                print(f"{k + 1}/{len(sets)} tasksets", flush=True)
    order = lambda r: (r["n_tasks"], r["utilization"], r["taskset_id"])
    rows.sort(key=order); bounds.sort(key=lambda r: (order(r), r["priority"]))
    for name, data in (("per_taskset.csv", rows), ("s2eps_bounds.csv", bounds)):
        with open(os.path.join(HERE, "results", name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader(); w.writerows(data)

    bad = [r for r in rows if r["s2_gp_feasible"] and not r["s2_accept"]]
    print(f"done: {len(rows)} tasksets; GP solutions failing the exact check: {len(bad)}")


if __name__ == "__main__":
    main()
