# Synthetic experiments (revised)

Design-space exploration of Sec. VI (Figs. 4-6): the deterministic fixed-priority
scheduler, the S²ε-Scheduler, and the ε-Scheduler on synthetic tasksets.

## Setup

- `data/tasksets.csv`: 8,000 tasksets (n ∈ {5, 10, 15, 20}, U ∈ {0.1, ..., 1.0},
  200 tasksets per point; UUniFast utilizations, periods in [50, 200] ms,
  implicit deadlines, one randomly selected control task per taskset). Each task
  carries the ε-Scheduler inter-arrival bounds [T⊥, T⊤] used for comparison.
- Rate-monotonic priorities.
- Control stability: L + αJ ≤ β with α = 1.2 and β = 20.83 ms (DC motor of
  Sec. III-B), using R^b = C. This gives the response-time limit
  X = C + (β − C)/α for the control task.
- Protection duration λ = 160 ms. Equal weights ω_i = 1.

## Method (`s2eps.py`)

- **Exact analysis.** Multi-job response-time analysis for arbitrary deadlines
  (Eqs. (6)-(9)), where every task releases jobs at least S_j apart:
  S_j = T_j (deterministic), S_j = T_j − δ_j (S²ε), S_j = T⊥_j (ε-Scheduler).
  A taskset is accepted if all tasks meet their deadlines and the control task
  satisfies R^w ≤ X.
- **S²ε noise bounds.** Geometric program of Eq. (24), solved in log space
  (SciPy SLSQP). The schedulability constraint bounds the workload over D_i and
  the stability constraint over X_i. If the program is infeasible, δ = 0
  (fallback to the deterministic schedule). Every GP solution is re-checked
  with the exact analysis.
- **Metrics.** Acceptance ratio (Fig. 4); noise percentage
  100/|Γ| Σ δ_i/T_i, where the ε-Scheduler uses min(T_i − T⊥_i, T⊤_i − T_i)
  (Fig. 5); maximum protected job count max_i ⌈λ / S_i⌉ (Fig. 6).

## Running

```
pip install numpy scipy matplotlib
python run_experiments.py      # ~5 min on 10 cores -> results/per_taskset.csv, results/s2eps_bounds.csv
python plots.py                # -> figures/*.pdf, results/summary.csv
```

## Outputs

| File | Content |
|---|---|
| `results/per_taskset.csv` | acceptance, GP status, noise percentage, job counts per taskset |
| `results/s2eps_bounds.csv` | δ_i and δ_i^max of every task |
| `results/summary.csv` | per (n, U): acceptance ratios, share of feasible tasksets with δ > 0, mean noise, mean job counts |
| `figures/acceptance_n*.pdf` | Fig. 4 |
| `figures/epsilon_proposed_vs_sarts_accepted_n*.pdf` | Fig. 5 (S²ε: accepted tasksets; ε-Scheduler: all tasksets) |
| `figures/protection_duration_*.pdf` | Fig. 6 |
