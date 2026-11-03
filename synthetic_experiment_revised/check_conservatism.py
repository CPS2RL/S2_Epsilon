"""Check GP conservatism on the SAME stored tasksets used for Figs. 4-6.

Search delta_i = rho * delta_max_i using exact multi-job RTA, keeping the
paper's assumed stability condition. This is an offline comparison only;
it does not change S2eps's GP or deterministic fallback. See README.md.
"""
import argparse
import csv
import hashlib
import json
import math
import platform
from collections import defaultdict
from pathlib import Path

import numpy as np
import scipy

from run_experiments import load_tasksets
from s2eps import certify, relaxed_bound, stability_window, worst_case_response

HERE = Path(__file__).resolve().parent
NONZERO = 1e-6  # same per-task normalized-noise threshold as run_experiments.py


def unpack(rows):
    rows = sorted(rows, key=lambda r: (float(r['T_ms']), int(r['task_id'])))
    C, T, D = (np.array([float(r[k]) for r in rows]) for k in ('C_ms', 'T_ms', 'D_ms'))
    ctrl, = [i for i, r in enumerate(rows) if r['control'] == 'True']
    dmax = np.array([min(T[i] - float(r['eps_low_ms']), float(r['eps_high_ms']) - T[i])
                     for i, r in enumerate(rows)])
    if np.any(dmax < 0) or np.any(T - dmax <= 0):
        raise ValueError('Invalid candidate inter-arrival bounds')
    return C, T, D, ctrl, dmax


def response_until_limit(i, C, S, bound):
    """Same job-completion recurrence as s2eps.worst_case_response.

    Enumerate q until W_i(q) <= (q+1)S_i, so the level-i busy window
    ends before the next own release. Stop early on a bound violation.
    This avoids constructing enormous busy windows for rejected candidates.
    """
    worst, q = 0.0, 0
    while True:
        W = (q + 1) * C[i]
        while True:
            if W - q * S[i] > bound + 1e-6:
                return math.inf
            nw = (q + 1) * C[i] + sum(math.ceil(W / S[j] - 1e-9) * C[j] for j in range(i))
            if nw <= W + 1e-9:
                break
            W = nw
        worst = max(worst, W - q * S[i])
        if W <= (q + 1) * S[i] + 1e-9:
            return worst
        q += 1


def exact_ok(C, T, D, ctrl, delta, return_response=False):
    S = T - delta
    if np.any(S <= 0) or np.sum(C / S) >= 1.0 - 1e-9:
        return (False, []) if return_response else False
    response = np.zeros(len(C))
    for i in [ctrl] + [j for j in range(len(C)) if j != ctrl]:
        bound = min(D[i], stability_window(C[i])) if i == ctrl else D[i]
        R = response_until_limit(i, C, S, bound)
        if not math.isfinite(R) or R > bound + 1e-6:
            return (False, []) if return_response else False
        response[i] = R
    return (True, response) if return_response else True


def search(C, T, D, ctrl, dmax, tolerance):
    if not exact_ok(C, T, D, ctrl, np.zeros(len(C))):
        raise ValueError('Stored deterministic acceptance disagrees with RTA')
    if exact_ok(C, T, D, ctrl, dmax):
        return 1.0, 1.0
    low, high = 0.0, 1.0
    while high - low > tolerance:
        mid = (low + high) / 2
        if exact_ok(C, T, D, ctrl, mid * dmax):
            low = mid
        else:
            high = mid
    # low is an explicitly checked feasible point. No claim of vector optimality.
    return low, high


def self_test():
    C = np.array([8., 12., 4.]); T = np.array([30., 50., 75.])
    assert [worst_case_response(i, C, T) for i in range(3)] == [8., 20., 24.]
    assert [worst_case_response(i, C, np.array([26., 42., 50.])) for i in range(3)] == [8., 20., 24.]
    assert math.isinf(worst_case_response(1, [2., 3.], [4., 4.]))
    # Full-range acceptance and a utilization-limited interior solution.
    c = np.array([1.]); t = np.array([10.]); dm = np.array([5.])
    assert search(c, t, t, 0, dm, 1e-7) == (1., 1.)
    c = np.array([8.]); lo, hi = search(c, t, t, 0, dm, 1e-7)
    assert abs(lo - 0.4) < 1e-6 and hi - lo <= 1e-7
    assert exact_ok(c, t, t, 0, lo * dm)
    # Cross-check the alternate stopping rule against the repo's busy-window
    # implementation on 100 deterministic and perturbed synthetic tasksets.
    rng = np.random.default_rng(20261103)
    for _ in range(100):
        C = rng.uniform(0.1, 3, 4)
        S = np.sort(rng.uniform(5, 30, 4))
        if sum(C / S) >= 0.85:
            continue
        for i in range(4):
            expected = worst_case_response(i, C, S)
            got = response_until_limit(i, C, S, 1e6)
            assert abs(got - expected) < 1e-6, (C, S, i, got, expected)
    # Explicit case in which a later own job is worse than the first.
    C = np.array([3., 3.]); S = np.array([8., 5.])
    assert response_until_limit(1, C, S, 100.) == 7.0
    assert worst_case_response(1, C, S) == 7.0
    print('self-tests and reference-RTA cross-checks passed', flush=True)


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--utilizations', nargs='+', type=float, default=[0.6, 0.7, 0.8])
    ap.add_argument('--rho-tolerance', type=float, default=1e-3)
    ap.add_argument('--output-dir', type=Path, default=HERE / 'results' / 'conservatism')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--verify-reference', action='store_true',
                    help='Recheck every final point using the unmodified repo RTA')
    args = ap.parse_args()
    if not 0 < args.rho_tolerance < 1:
        ap.error('--rho-tolerance must lie in (0,1)')
    if args.self_test:
        self_test()
    input_paths = [HERE / 'data' / 'tasksets.csv', HERE / 'results' / 'per_taskset.csv']
    tasksets = load_tasksets(input_paths[0])
    stored = list(csv.DictReader(input_paths[1].open()))
    selected = [r for r in stored if any(abs(float(r['utilization']) - u) < 1e-10 for u in args.utilizations)]
    outputs, grouped = [], defaultdict(list)
    for r in selected:
        key = (int(r['n_tasks']), float(r['utilization']), int(r['taskset_id']))
        if r['det_accept'] != 'True' or r['s2_gp_feasible'] != 'False':
            continue
        C, T, D, ctrl, dmax = unpack(tasksets[key])
        # Since all relaxed constraints increase with delta, a violation at zero
        # proves GP infeasibility independently of SLSQP's stored solver status.
        ratios = [relaxed_bound(i, C, T, np.ones(len(C)), D[i]) / D[i] for i in range(len(C))]
        X = stability_window(C[ctrl])
        ratios.append(relaxed_bound(ctrl, C, T, np.ones(len(C)), X) / X)
        if max(ratios) <= 1.0 + 1e-7:
            raise ValueError(f'{key}: stored solver failure is not established GP infeasibility')
        low, high = search(C, T, D, ctrl, dmax, args.rho_tolerance)
        delta = low * dmax
        valid, response = exact_ok(C, T, D, ctrl, delta, return_response=True)
        if not valid:
            raise AssertionError(f'{key}: final exact check failed')
        if args.verify_reference:
            dl, st, ref = certify(C, D, T - delta, ctrl)
            if not (dl and st) or not np.allclose(response, ref, atol=1e-6, rtol=0):
                raise AssertionError(f'{key}: reference RTA disagrees')
        row = dict(n_tasks=key[0], utilization=key[1], taskset_id=key[2],
                   rho_feasible=low, rho_upper=high,
                   noise_pct=100 * float(np.mean(delta / T)),
                   nonzero=bool(np.any(delta / T > NONZERO)),
                   zero_noise_gp_max_constraint_ratio=max(ratios),
                   deadline_margin_ms=float(min(D - np.array(response))),
                   stability_margin_ms=float(X - response[ctrl]))
        outputs.append(row); grouped[key[:2]].append(row)
        if len(outputs) % 100 == 0:
            print(f'{len(outputs)} fallback tasksets checked', flush=True)
    summary = []
    for n, u in sorted({(int(r['n_tasks']), float(r['utilization'])) for r in selected}):
        group = grouped[(n, u)]
        total = sum(r['n_tasks'] == str(n) and float(r['utilization']) == u for r in selected)
        det = sum(r['n_tasks'] == str(n) and float(r['utilization']) == u and r['det_accept'] == 'True' for r in selected)
        positive = [r for r in group if r['nonzero']]
        summary.append(dict(n_tasks=n, utilization=u, generated=total, deterministic_feasible=det,
                            gp_fallback=len(group), recovered_nonzero=len(positive),
                            recovered_pct=100 * len(positive) / len(group) if group else 0,
                            noise_pct_mean=float(np.mean([r['noise_pct'] for r in group])) if group else 0,
                            noise_pct_median=float(np.median([r['noise_pct'] for r in group])) if group else 0))
    if not outputs:
        raise ValueError('No matching fallback tasksets')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / 'per_taskset.csv', outputs)
    write_csv(args.output_dir / 'summary.csv', summary)
    metadata = dict(utilizations=args.utilizations, rho_tolerance=args.rho_tolerance,
                    nonzero_normalized_threshold=NONZERO,
                    all_final_points_reference_checked=args.verify_reference,
                    source_sha256={str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths},
                    numpy_version=np.__version__, scipy_version=scipy.__version__,
                    python_version=platform.python_version(),
                    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    method='Bisection along delta_i=rho*delta_max_i; original multi-job RTA and assumed stability condition; offline comparison only')
    (args.output_dir / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    for r in summary:
        print(r, flush=True)


if __name__ == '__main__':
    main()
