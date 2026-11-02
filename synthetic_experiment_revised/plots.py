"""Figures 4-6 of Sec. VI from results/per_taskset.csv.

Output (figures/):
  acceptance_n{5,10,15,20}.pdf                          Fig. 4, acceptance ratio
  epsilon_proposed_vs_sarts_accepted_n{5,10,15,20}.pdf  Fig. 5, inter-arrival noise
  protection_duration_{5,10,15,20}.pdf                  Fig. 6, maximum job count
Also prints the summary statistics used in the text (results/summary.csv).
"""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
UTILS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
SIZES = [5, 10, 15, 20]

LBL_DET, LBL_S2, LBL_EPS = "Deterministic", r"S$^2\epsilon$", r"$\epsilon$"
STY_DET = dict(color="black", linestyle="-", marker="o", markerfacecolor="none")
STY_S2 = dict(color="green", linestyle=":", marker="^", markerfacecolor="none")
STY_EPS = dict(color="red", linestyle="-.", marker="s", markerfacecolor="none")


def load():
    data = defaultdict(list)
    with open(os.path.join(HERE, "results", "per_taskset.csv")) as f:
        for r in csv.DictReader(f):
            for k in r:
                if r[k] in ("True", "False"):
                    r[k] = r[k] == "True"
            data[(int(r["n_tasks"]), round(float(r["utilization"]), 1))].append(r)
    return data


def style_axes(ax, fs):
    ax.grid(True, linestyle=":", linewidth=0.8, alpha=0.6)
    ax.tick_params(labelsize=fs)
    ax.set_xlabel("Utilization", fontsize=fs)


def legend_top(ax, fs, ncol, **kw):
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=ncol, frameon=False,
              fontsize=fs, handlelength=1.4, columnspacing=0.8, handletextpad=0.3, **kw)


def fig_acceptance(data, n):
    fs = 40
    fig, ax = plt.subplots(figsize=(9.0, 5.6))
    pct = lambda key: [100.0 * np.mean([r[key] for r in data[(n, u)]]) for u in UTILS]
    ax.plot(UTILS, pct("det_accept"), label=LBL_DET, linewidth=2.5, markersize=13, markeredgewidth=2, **STY_DET)
    ax.plot(UTILS, pct("s2_accept"), label=LBL_S2, linewidth=2.5, markersize=10, markeredgewidth=2, **STY_S2)
    ax.plot(UTILS, pct("eps_accept"), label=LBL_EPS, linewidth=2.5, markersize=10, markeredgewidth=2, **STY_EPS)
    ax.set_ylabel("Acceptance\nRatio (%)", fontsize=fs)
    ax.set_xticks(UTILS); ax.set_xlim(0.07, 0.83); ax.set_ylim(-3, 103)
    ax.yaxis.set_major_locator(MultipleLocator(20))
    style_axes(ax, fs)
    legend_top(ax, fs, 3)
    fig.savefig(os.path.join(OUT, f"acceptance_n{n}.pdf"), bbox_inches="tight")
    plt.close(fig)


def fig_noise(data, n):
    fs = 30
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    s2 = [[r["s2_noise_pct"] for r in data[(n, u)] if r["s2_accept"]] for u in UTILS]
    ep = [[r["eps_noise_pct"] for r in data[(n, u)]] for u in UTILS]
    for vals, lbl, sty in ((s2, LBL_S2, STY_S2), (ep, LBL_EPS, STY_EPS)):
        m = [np.mean(v) if v else np.nan for v in vals]
        sd = [np.std(v) if v else np.nan for v in vals]
        ax.errorbar(UTILS, m, yerr=sd, label=lbl, linewidth=2.5, markersize=8, markeredgewidth=1.5,
                    capsize=4, elinewidth=1.2, **sty)
    ax.set_ylabel("Inter-Arrival\nNoise (%)", fontsize=fs)
    ax.set_xticks(UTILS); ax.set_xlim(0.0, 0.83)
    ax.yaxis.set_major_locator(MultipleLocator(20))
    style_axes(ax, fs)
    h, l = ax.get_legend_handles_labels()
    ax.legend([x[0] for x in h], l, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False,
              fontsize=fs, handlelength=1.6, columnspacing=1.0, handletextpad=0.3)
    fig.savefig(os.path.join(OUT, f"epsilon_proposed_vs_sarts_accepted_n{n}.pdf"), bbox_inches="tight")
    plt.close(fig)


def fig_jobs(data, n):
    fs = 30
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    rng = np.random.default_rng(0)
    for u in UTILS:
        ep = [r["eps_jobs"] for r in data[(n, u)]]
        s2 = [r["s2_jobs"] for r in data[(n, u)] if r["s2_accept"]]
        ax.scatter(u - 0.012 + rng.uniform(-0.012, 0.012, len(ep)), ep, marker="s", s=28,
                   facecolors="none", edgecolors="red", alpha=0.6, linewidths=1.2,
                   label=LBL_EPS if u == UTILS[0] else None)
        ax.scatter(u + 0.012 + rng.uniform(-0.012, 0.012, len(s2)), s2, marker="^", s=32,
                   facecolors="none", edgecolors="green", alpha=0.6, linewidths=1.2,
                   label=LBL_S2 if u == UTILS[0] else None)
    ax.set_ylabel("Number of\nProtected Jobs", fontsize=fs)
    ax.set_xticks(UTILS); ax.set_xlim(0.05, 0.85); ax.set_ylim(0, 18)
    ax.yaxis.set_major_locator(MultipleLocator(5))
    style_axes(ax, fs)
    h, l = ax.get_legend_handles_labels()
    order = [l.index(LBL_S2), l.index(LBL_EPS)]
    ax.legend([h[i] for i in order], [l[i] for i in order], loc="lower center", bbox_to_anchor=(0.5, 1.0),
              ncol=2, frameon=False, fontsize=fs, handletextpad=0.2, columnspacing=1.0, markerscale=2.0,
              scatterpoints=1)
    for lh in ax.get_legend().legend_handles:
        lh.set_alpha(1)
    fig.savefig(os.path.join(OUT, f"protection_duration_{n}.pdf"), bbox_inches="tight")
    plt.close(fig)


def summary(data):
    rows = []
    for n in SIZES:
        for u in UTILS:
            d = data[(n, u)]
            det = [r for r in d if r["det_accept"]]
            acc = [r for r in d if r["s2_accept"]]
            rows.append({
                "n_tasks": n, "utilization": u, "tasksets": len(d),
                "det_accept_pct": round(100 * len(det) / len(d), 1),
                "s2_accept_pct": round(100 * len(acc) / len(d), 1),
                "eps_accept_pct": round(100 * np.mean([r["eps_accept"] for r in d]), 1),
                "s2_randomized_pct_of_feasible": round(100 * np.mean([r["s2_randomized"] for r in det]), 1) if det else "",
                "s2_noise_pct_mean": round(np.mean([r["s2_noise_pct"] for r in acc]), 1) if acc else "",
                "eps_noise_pct_mean": round(np.mean([r["eps_noise_pct"] for r in d]), 1),
                "s2_jobs_mean": round(np.mean([r["s2_jobs"] for r in acc]), 1) if acc else "",
                "eps_jobs_mean": round(np.mean([r["eps_jobs"] for r in d]), 1),
            })
    with open(os.path.join(HERE, "results", "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    data = load()
    for k, v in data.items():
        for r in v:
            for key in ("s2_noise_pct", "eps_noise_pct"):
                r[key] = float(r[key])
            for key in ("s2_jobs", "eps_jobs"):
                r[key] = int(r[key])
    for n in SIZES:
        fig_acceptance(data, n); fig_noise(data, n); fig_jobs(data, n)
    for r in summary(data):
        print(r)


if __name__ == "__main__":
    main()
