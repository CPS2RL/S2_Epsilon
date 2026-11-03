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

## Conservatism check (additional experiment)

`check_conservatism.py` uses the stored Fig. 4-6 tasksets and solver results;
it does not regenerate workloads or change the GP/fallback results in those
figures. It selects deterministically feasible tasksets with an infeasible GP
at U in {0.6, 0.7, 0.8}. For every selected taskset, violation of the relaxed
constraints at delta = 0 independently establishes GP infeasibility, since
these constraints only increase as delta increases.

The script searches delta_i = rho * delta_max_i, 0 <= rho <= 1, by bisection
until the rho bracket is at most 0.001 wide. It retains the checked feasible
endpoint, requiring all deadlines and the control task's response-time limit
X = C + (beta - C)/alpha. The stability claim remains conditional on the
paper's assumed stability condition for the sampling intervals considered.
This search gives a feasible allocation, not a globally optimal allocation.
A taskset has non-zero noise when some delta_i/T_i > 1e-6, matching the
existing experiment's threshold.

The job-completion recurrence is the same as in `s2eps.py`. To avoid building
long busy windows for failing candidates, the search checks each successive
job and stops on a response-time violation, or when the busy window ends
before the next own release. `--verify-reference` additionally checks every
final allocation with the unmodified `s2eps.certify` implementation and
compares response-time values. The self-tests include a case in which a
later job has a larger response time than the first, plus randomized
cross-checks against the original implementation.

```
python check_conservatism.py --self-test --verify-reference
```

Results are in `results/conservatism/`:

- `per_taskset.csv`: feasible rho, search bracket, normalized noise, relaxed
  constraint violation at zero noise, and response-time margins.
- `summary.csv`: fallback counts, recovered non-zero counts and percentages,
  and mean/median normalized noise per (n, U).
- `metadata.json`: input hashes, script hash, package versions, precision,
  threshold, and whether all final points were reference-checked.

All 694 selected fallback tasksets admit non-zero noise. Mean normalized
noise across taskset sizes is 28.5-32.7% at U=0.6, 16.6-23.6% at U=0.7,
and 4.9-11.0% at U=0.8. These are offline comparison results, not a change
to the proposed scheduler or Figs. 4-6.
