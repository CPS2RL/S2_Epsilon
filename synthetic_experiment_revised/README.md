# Synthetic experiments (revised)

Design-space exploration with synthetic tasksets: the deterministic fixed-priority
scheduler, the S²ε-Scheduler, and the ε-Scheduler on synthetic tasksets.

## Setup

- `data/tasksets.csv`: 8,000 tasksets (n ∈ {5, 10, 15, 20}, U ∈ {0.1, ..., 1.0},
  200 tasksets per point; UUniFast utilizations, periods in [50, 150] ms,
  implicit deadlines, one randomly selected control task per taskset). Each task
  carries the ε-Scheduler inter-arrival bounds [T⊥, T⊤] used for comparison.
- `data/original_evaluation/`: the unmodified outputs of the original evaluation
  (`task_parameters.csv`, `per_taskset_scheduler_results.csv`), from which
  `data/tasksets.csv` was extracted (task parameters and ε-Scheduler bounds only;
  the original S²ε results, computed with the earlier GP and stability check, are
  kept for reference).
- Rate-monotonic priorities.
- Control stability: L + αJ ≤ β with α = 1.2 and β = 20.83 ms (DC motor
  plant), using R^b = C. This gives the response-time limit
  X = C + (β − C)/α for the control task.
- Protection duration λ = 160 ms. Equal weights ω_i = 1.

## Method (`s2eps.py`)

- **Exact analysis.** Multi-job response-time analysis for arbitrary deadlines,
  where every task releases jobs at least S_j apart:
  S_j = T_j (deterministic), S_j = T_j − δ_j (S²ε), S_j = T⊥_j (ε-Scheduler).
  A taskset is accepted if all tasks meet their deadlines and the control task
  satisfies R^w ≤ X.
- **S²ε noise bounds.** Geometric program, solved in log space
  (SciPy SLSQP). The schedulability constraint bounds the workload over D_i and
  the stability constraint over X_i. If the program is infeasible, δ = 0
  (fallback to the deterministic schedule). Every GP solution is re-checked
  with the exact analysis.
- **Metrics.** Acceptance ratio; noise percentage
  100/|Γ| Σ δ_i/T_i, where the ε-Scheduler uses min(T_i − T⊥_i, T⊤_i − T_i);
  number of protected jobs max_i ⌈λ / S_i⌉.

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
| `figures/acceptance_n*.pdf` | acceptance ratio vs. utilization |
| `figures/epsilon_proposed_vs_sarts_accepted_n*.pdf` | inter-arrival noise vs. utilization (S²ε: accepted tasksets; ε-Scheduler: all tasksets) |
| `figures/protection_duration_*.pdf` | number of protected jobs vs. utilization |

## Note

Opus 5.5 was used for some of the implementations. However, all the code and results were fully reviewed and approved by the authors.
