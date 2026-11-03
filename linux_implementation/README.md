# Linux implementation

Analysis of recorded runtime overhead and power measurements for the ε-Scheduler and S²ε-Scheduler.

## Setup

- `RPi_Overhead_Analysis.ipynb`: analysis notebook.
- `rpi_overhead.zip`: measurement archive; place it beside the notebook.

## Method

Reports mean and sample standard deviation across five runs or trials for:

- Task-selection overhead (µs).
- Arrival-randomization overhead (µs).
- PMIC rail power (W) under the `performance` and `ondemand` governors.

## Running

```bash
pip install numpy pandas jupyterlab
cd linux_implementation
jupyter lab RPi_Overhead_Analysis.ipynb
```

Run all notebook cells. The ZIP is read directly without extraction.

## Outputs

A printed table comparing both schedulers using mean ± SD for each metric.
