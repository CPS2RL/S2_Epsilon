"""Figure for the pessimism experiment from results/pessimism/per_taskset.csv.

Output (figures/):
  pessimism_noise_n5.pdf   average noise of the GP and the exhaustive search vs. utilization
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

from plots import LBL_S2, STY_S2, style_axes

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
UTILS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
N = 5

LBL_GRID = "Exhaustive"
STY_GRID = dict(color="black", linestyle="-", marker="s", markerfacecolor="none")


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = [r for r in csv.DictReader(open(os.path.join(HERE, "results", "pessimism", "per_taskset.csv")))
            if int(r["n_tasks"]) == N]
    mean = lambda col, u: np.mean([float(r[col]) for r in rows if round(float(r["utilization"]), 1) == u])

    fs = 30
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    for col, lbl, sty in (("gp_noise_pct", "Geometric Program", STY_S2), ("grid_noise_pct", LBL_GRID, STY_GRID)):
        ax.plot(UTILS, [mean(col, u) for u in UTILS], label=lbl, linewidth=2.5, markersize=8,
                markeredgewidth=1.5, **sty)
    ax.set_ylabel("Inter-Arrival\nNoise (%)", fontsize=fs)
    ax.set_xticks(UTILS); ax.set_xlim(0.05, 0.85); ax.set_ylim(-2, 52)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    style_axes(ax, fs)
    # one entry per row, so the legend is no wider than the plot and the figure keeps the
    # size of the other panels
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=1, frameon=False, fontsize=fs,
              handlelength=1.6, handletextpad=0.3, labelspacing=0.35)
    fig.savefig(os.path.join(OUT, f"pessimism_noise_n{N}.pdf"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
