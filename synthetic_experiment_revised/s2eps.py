"""Analysis used by the synthetic experiments (Sec. VI).

All times are in ms. Tasks are given in priority order (index 0 = highest
priority). A task is described by its WCET C, nominal period T, deadline D,
and a minimum inter-arrival time S (S = T for the deterministic scheduler,
S = T - delta for the S2eps-Scheduler, S = T^perp for the epsilon-Scheduler).
"""
import math

import numpy as np
from scipy.optimize import minimize

ALPHA = 1.2     # plant coefficient alpha (DC motor, Sec. III-B)
BETA = 20.83    # stability threshold beta in ms (DC motor, Sec. III-B)
EPS = 1e-9


def stability_window(C):
    """X_i = C_i + J_i^max with R_i^b = C_i (L + alpha*J <= beta, Eq. (2)-(3))."""
    return C + (BETA - C) / ALPHA


# ------------------------------------------------------------------ exact RTA
def worst_case_response(i, C, S, limit=1e7):
    """Exact multi-job response-time analysis (Eqs. (6)-(9)) for task i when
    every task j releases jobs at least S[j] apart. Returns math.inf if the
    level-i workload is unbounded."""
    hep = range(i + 1)
    if sum(C[j] / S[j] for j in hep) >= 1.0 - EPS:
        return math.inf
    # level-i busy window, Eq. (6)
    B = sum(C[j] for j in hep)
    while True:
        nb = sum(math.ceil(B / S[j] - EPS) * C[j] for j in hep)
        if nb <= B + EPS:
            break
        B = nb
        if B > limit:
            return math.inf
    n_jobs = math.ceil(B / S[i] - EPS)
    worst = 0.0
    for q in range(n_jobs):
        # completion time of the q-th job, Eq. (7)
        W = (q + 1) * C[i]
        while True:
            nw = (q + 1) * C[i] + sum(math.ceil(W / S[j] - EPS) * C[j] for j in range(i))
            if nw <= W + EPS:
                break
            W = nw
        worst = max(worst, W - q * S[i])          # Eq. (8)-(9)
    return worst


def certify(C, D, S, ctrl):
    """Schedulability (R_i^w <= D_i, Eq. (10)) for all tasks and stability
    (R_c^w <= X_c, Eq. (11) with R^b = C) for the control task ctrl."""
    R = [worst_case_response(i, C, S) for i in range(len(C))]
    deadline_ok = all(R[i] <= D[i] + 1e-6 for i in range(len(C)))
    stability_ok = R[ctrl] <= stability_window(C[ctrl]) + 1e-6
    return deadline_ok, stability_ok, R


# ------------------------------------------------------------ geometric program
def relaxed_bound(i, C, T, y, W):
    """Relaxed workload bound over a window of length W, Eq. (21):
    sum_{j in hep(i)} (W / (T_j y_j) + 1) C_j."""
    return sum((W / (T[j] * y[j]) + 1.0) * C[j] for j in range(i + 1))


def solve_gp(C, T, D, ctrl, delta_max, weights=None):
    """Solve Eq. (24) in log space. Returns delta (np.array) or None if the
    program is infeasible. delta_max[i] = min(T_i - T_i^perp, T_i^top - T_i)."""
    C = np.asarray(C, float); T = np.asarray(T, float); D = np.asarray(D, float)
    n = len(C)
    w = np.ones(n) if weights is None else np.asarray(weights, float)
    ylow = np.clip(1.0 - np.asarray(delta_max, float) / T, 1e-6, 1.0)
    X = stability_window(C[ctrl])

    cons = [{"type": "ineq", "fun": (lambda x, i=i: 1.0 - relaxed_bound(i, C, T, np.exp(x), D[i]) / D[i])}
            for i in range(n)]
    cons.append({"type": "ineq", "fun": lambda x: 1.0 - relaxed_bound(ctrl, C, T, np.exp(x), X) / X})
    bounds = [(math.log(l), 0.0) for l in ylow]

    def feasible(x):
        return all(c["fun"](x) >= -1e-7 for c in cons)

    best = None
    for x0 in (np.full(n, -1e-6), 0.5 * np.log(ylow)):
        r = minimize(lambda x: float(np.dot(w, np.exp(x))), x0, bounds=bounds, constraints=cons,
                     method="SLSQP", options={"ftol": 1e-10, "maxiter": 500})
        x = np.clip(r.x, [b[0] for b in bounds], 0.0)
        if feasible(x) and (best is None or np.dot(w, np.exp(x)) < np.dot(w, np.exp(best))):
            best = x
    if best is None:
        return None
    return T * (1.0 - np.exp(best))
