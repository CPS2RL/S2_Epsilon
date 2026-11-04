# Raspberry Pi 5 PREEMPT_RT setup and experimental data collection

**Project:** S²-EPSILON / SARTS — four hardware metrics, 200 task sets × 5 trials  
**Platform used:** Raspberry Pi 5 (8 GB RAM), 64-bit Debian 12 (Bookworm), ARM64, microSD storage  
**Verified experimental kernel:** `6.12.109+rpt-rpi-v8-rt` with `CONFIG_PREEMPT_RT=y`  
**Scheduling:** Preemptive fixed priority (`SCHED_FIFO`) with Rate-Monotonic (RM) priority assignment  
**Benchmark CPU:** CPU 1 (all four Raspberry Pi 5 cores remain enabled)

This document first describes the **previously verified** Raspberry Pi 5 PREEMPT_RT setup. It then describes a **proposed expanded 200-task-set collection**. The 200-task-set measurements have **not yet been collected**; the available original hardware CSV contains only 10 task sets. It is intended for reproducing the environment and workflow, not for reproducing numerical results on arbitrary future kernel versions. Some installation details (such as `apt` package versions) can change over time. Record your actual versions when repeating the experiment.

> **Important:** We **did not** compile a custom kernel, apply PREEMPT_RT patches ourselves, disable SMP, configure `maxcpus=1`, or change Linux's scheduler implementation. We installed Raspberry Pi's prebuilt PREEMPT_RT-enabled kernel and used user-space real-time threads pinned to CPU 1.

## 1. Prepare the hardware and operating system

1. Use a Raspberry Pi 5 with adequate cooling, an appropriate power supply, and sufficient microSD capacity for tracing (the original setup used a 128 GB card).
2. Install a **64-bit Debian-based Raspberry Pi OS** image (our successful setup used Debian 12 / Bookworm, ARM64). Enable SSH if configuring the Pi remotely.
3. Connect the Pi to power and the network, boot, and open a terminal (locally or via SSH).
4. Inspect the current system:

   ```bash
   cat /etc/os-release
   uname -a
   uname -m
   lscpu
   df -h
   free -h
   ```

   Expected architecture: `aarch64`; Raspberry Pi 5 has four Cortex-A76 cores (`CPU 0`–`CPU 3`).

5. Update the existing packages before changing kernels:

   ```bash
   sudo apt update
   sudo apt upgrade -y
   ```

   If `apt` reports that a reboot is required, reboot before continuing. Check compatibility if upgrading an existing experimental installation; package updates may change the running kernel.

## 2. Back up the boot configuration before installing PREEMPT_RT

The boot configuration is generally located at `/boot/firmware/config.txt` on our Bookworm installation.

```bash
sudo cp -a /boot/firmware/config.txt \
  /boot/firmware/config.txt.pre-rt

sudo mkdir -p /root/pi5_pre_rt_backup
sudo cp -a /boot/firmware/config.txt \
  /root/pi5_pre_rt_backup/config.txt.before_rt

ls -l /boot/firmware/config.txt.pre-rt
```

**Do not overwrite or delete existing Raspberry Pi boot settings.** In our setup we also preserved the old boot files before modifying the kernel selection. If working remotely, keep a recovery option (physical access, backup SD card, or Raspberry Pi `tryboot`) in case the new kernel fails to boot.

## 3. Install the prebuilt PREEMPT_RT kernel

We used the Raspberry Pi-provided real-time kernel, rather than patching or building the kernel from source:

```bash
sudo apt update
sudo apt install -y linux-image-rpi-v8-rt linux-headers-rpi-v8-rt
```

Check which package version is installed and whether the RT kernel image exists:

```bash
dpkg -l | grep -E 'linux-(image|headers)-rpi-v8-rt'
ls -lh /boot/firmware/kernel8_rt.img
```

The package name and availability depend on your configured Raspberry Pi / Debian repositories. **If the package is not found, check your OS and repository configuration; do not substitute an unrelated third-party RT kernel.**

### 3.1 Select the real-time kernel for boot

We set the following kernel selector in `/boot/firmware/config.txt`:

```ini
[all]
kernel=kernel8_rt.img
```

Edit the file with:

```bash
sudo nano /boot/firmware/config.txt
```

Add `kernel=kernel8_rt.img` in the appropriate `[all]` section while keeping existing settings. Ensure there is not another conflicting `kernel=` setting that applies to the same boot configuration.

**Optional safer test, particularly over SSH:** Raspberry Pi's one-time `tryboot` mechanism was used during our initial verification. On a supported installation, copy the current config to `tryboot.txt`, edit only the test copy to select `kernel8_rt.img`, then request a one-time boot:

```bash
sudo cp -a /boot/firmware/config.txt /boot/firmware/tryboot.txt
sudo nano /boot/firmware/tryboot.txt
sudo reboot 0 tryboot
```

Check the Raspberry Pi `tryboot` documentation before relying on it for recovery. A temporary successful boot does **not** permanently change `config.txt`; after testing, apply the kernel selector to the normal `config.txt`. If you have already selected the RT kernel in `config.txt`, the optional test should instead be performed *before* making that permanent change.

Reboot after the permanent configuration:

```bash
sudo reboot
```

## 4. Verify that the correct kernel is running

After reconnecting:

```bash
uname -a
uname -r
```

Our verified output contained:

```text
6.12.109+rpt-rpi-v8-rt
... PREEMPT_RT ... aarch64
```

Verify the build configuration:

```bash
grep '^CONFIG_PREEMPT_RT=' /boot/config-"$(uname -r)"
```

Expected:

```text
CONFIG_PREEMPT_RT=y
```

`/sys/kernel/realtime` may not exist on this particular kernel build; absence of that path is **not** by itself evidence that PREEMPT_RT is disabled. Use `uname` and the kernel configuration as the primary verification.

**Version caveat:** A fresh installation at a later date may install a different PREEMPT_RT release. For an exact reproduction, document and preserve the package version and kernel build used for the new measurements. Do not claim kernel `6.12.109` unless `uname -r` confirms it.

## 5. Install the benchmark and tracing dependencies

```bash
sudo apt update
sudo apt install -y \
  build-essential gcc make \
  python3 python3-numpy python3-pandas \
  trace-cmd rt-tests zip tmux
```

The runner also calls `vcgencmd` to read PMIC telemetry. Check it first:

```bash
command -v vcgencmd
vcgencmd pmic_read_adc | head -20
```

If `vcgencmd` is missing, install the appropriate Raspberry Pi userland utilities provided by your OS image/repositories; verify its exact package name on that image. Do **not** silently proceed with missing PMIC readings when evaluating power.

Check important binaries:

```bash
command -v gcc
command -v python3
command -v trace-cmd
command -v tmux
python3 -c 'import numpy, pandas; print("Python dependencies OK")'
```

## 6. Check real-time scheduling support

Linux provides the `SCHED_FIFO` policy on both ordinary and PREEMPT_RT kernels. PREEMPT_RT improves kernel preemptibility; it does not itself assign task priorities.

```bash
chrt --max
```

The benchmark uses `pthread_setschedparam()` to assign `SCHED_FIFO` and static priority according to nominal period (RM), and `pthread_setaffinity_np()` to pin each task thread to **CPU 1**. The benchmark therefore needs suitable real-time scheduling privileges. We ran it as root via `sudo`.

The real-time scheduler uses fixed priorities; the `FIFO` part applies to ordering among threads at the *same* priority. Higher-priority threads can preempt lower-priority threads.

Check that all four cores remain online:

```bash
lscpu -e=CPU,ONLINE,MAXMHZ
cat /sys/devices/system/cpu/online
```

**What we did not do:** no `CONFIG_SMP=n`, no `maxcpus=1`, and no `isolcpus=` configuration as part of this benchmark. CPU affinity restricts the benchmark's task threads but does not prevent unrelated Linux work or interrupts from using CPU 1.

## 7. Verify the CPU frequency governor

Our experimental runner selects a CPU frequency *governor*, not a fixed MHz clock. The `performance` policy was used for scheduling-related timing; the power experiment also used `ondemand`.

Check governors available for the selected CPU:

```bash
CPU=1
cat /sys/devices/system/cpu/cpu${CPU}/cpufreq/scaling_available_governors
cat /sys/devices/system/cpu/cpu${CPU}/cpufreq/scaling_governor
cat /sys/devices/system/cpu/cpu${CPU}/cpufreq/scaling_min_freq
cat /sys/devices/system/cpu/cpu${CPU}/cpufreq/scaling_max_freq
cat /sys/devices/system/cpu/cpu${CPU}/cpufreq/scaling_cur_freq
```

The last three values are in **kHz**. For example, `2400000` kHz = 2.4 GHz. Do not assume actual CPU frequency was continuously fixed at 2.4 GHz; frequency caps and thermal throttling are possible.

**We did not need to manually leave a governor permanently set.** The supplied 200-task-set runner chooses `performance` or `ondemand` before each test and attempts to restore the prior setting afterward. If either governor is unavailable, fix that before collecting the corresponding dataset.

## 8. Check the tracing interface and kernel function names

Our experiments used Linux 6.12's **`pick_task_rt()`**, not the older `pick_next_task_rt()` label. It is important to use the function actually supported by the running kernel.

```bash
sudo mount -t tracefs nodev /sys/kernel/tracing 2>/dev/null || true

sudo grep -w 'pick_task_rt' \
  /sys/kernel/tracing/available_filter_functions

sudo grep -w 'function_graph' \
  /sys/kernel/tracing/available_tracers

sudo test -d /sys/kernel/tracing/events/sched/sched_switch \
  && echo 'sched_switch tracepoint available'
```

If `pick_task_rt` is not available, **do not substitute an unrelated function name silently**. The function symbol may differ across kernel versions, so validate the new name and report it accurately in the paper.

### 8.1 Smoke-test function tracing on CPU 1

We verified a CPU 1 function-graph trace using `trace-cmd`:

```bash
sudo trace-cmd record \
  -M 2 \
  -p function_graph \
  -g pick_task_rt \
  -o pick_task_rt_cpu1.dat \
  taskset -c 1 sleep 5

sudo trace-cmd report -i pick_task_rt_cpu1.dat | head -40
```

`-M 2` is the **CPU mask** for CPU 1 (`1 << 1`). Do not use `-C 1`: that argument is a clock option in `trace-cmd`, not the CPU selector.

The updated trace pass also records `sched:sched_switch`. It derives its *benchmark-involved* switch count from events containing `pi_benchmark`, so it is not necessarily a count of every CPU-wide scheduling event.

`pick_task_rt()` is not equivalent to the older `pick_next_task_rt()` symbol. Do not directly compare their absolute costs as though they were the same function.

## 9. Four hardware metrics reported in the paper

This revised experiment collects **only four categories of overhead**, for **DPS (ε-Scheduler)** and **S²-EPSILON (SARTS)**. TS is not measured or displayed in this expanded comparison.

| Paper metric | Collection method | Saved field |
|---|---|---|
| **(1) Context switches per completed job** | `sched:sched_switch` events involving `pi_benchmark`, divided by **jobs recorded in the same traced run** | `context_switches_per_job` |
| **(2) Kernel task-selection time** | `function_graph` timing of `pick_task_rt()` on CPU 1 | `pick_task_rt_mean_us` |
| **(3) Randomization function time** | User-space function timer from an **untraced** performance-governor run | `randomization_mean_us` |
| **(4) Power consumption** | PMIC monitored-rail estimate from **untraced** runs under both `performance` and `ondemand` governors | `pmic_rail_W` |

Power uses two governor conditions but is **one metric category**. The raw benchmark may still output jobs, deadlines, attempts and fallback diagnostics internally; these are used for validation and **not presented as additional paper metrics**.

**Methodological caveat:** The trace parser counts `sched_switch` events containing the benchmark's process name. This is a *benchmark-involved* switch count, not necessarily all kernel-wide switches. The denominator comes from the **same traced run**, avoiding a mismatch with job counts from untraced experiments. Describe this definition explicitly in the paper.

## 10. Input requirement: 200 distinct task sets

The expanded benchmark fixes the following design:

| Setting | Value |
|---|---|
| Number of task sets | **200 distinct task sets** |
| Tasks per set | 10 |
| Nominal utilization | 0.5 |
| Trials per task set and scheduler | **5** |
| Schedulers | DPS and SARTS only |
| Duration | 60 s per run |
| Hardware CPU | CPU 1 |
| Timing and tracing governor | `performance` |
| Power governors | `performance` and `ondemand` |

Place a CSV named **`task_parameters_200.csv`** in the same directory as the runner. It must contain 200 **independently generated or otherwise valid, genuinely distinct** task sets, each with 10 rows at `n_tasks=10` and `utilization=0.5`. The CSV must provide the previously computed DPS bounds and SARTS bounds:

```text
n_tasks,utilization,taskset_id,task_id,C_ms,T_ms,eps_low_ms,eps_high_ms,sarts_delta_ms
```

Other columns (e.g. `control`, `D_ms`, `sarts_low_ms`) are allowed. For each task set, retain the same parameters across all five trials and across both schedulers. The runner checks uniqueness, counts, and basic interval validity and **refuses to start** if fewer than 200 sets are provided.

> **Do not reuse or replicate 10 old task sets 20 times.** The previously used hardware CSV contains **only 10 task sets**, and another available analytical file contains only **100** at `n=10, U=0.5`. Neither is a valid 200-task-set input. Generate or export 200 valid sets with offline bounds before running the experiment. The Pi benchmark **does not solve the stability optimization**; it consumes precomputed bounds.

## 11. Install the updated collection package

Extract `SARTS_PREEMPT_RT_200_tasksets_4metrics.zip` on the Pi, or copy its files into a new directory:

```bash
cd ~/Downloads
unzip SARTS_PREEMPT_RT_200_tasksets_4metrics.zip -d sarts_200_experiment
cd sarts_200_experiment
chmod +x run_all.sh
```

Expected files:

```text
README.md
benchmark.c
run_all.sh
runner_200.py
summarize_200.py
```

**Before proceeding**, copy your genuine 200-task-set CSV:

```bash
cp /path/to/your/task_parameters_200.csv ./task_parameters_200.csv
```

There is **no populated `task_parameters_200.csv` in the supplied ZIP**, because the source data needed for a genuine 200-task-set trial were not supplied. Do not rename the 10-task-set CSV to bypass this requirement.

The benchmark code uses user-space `SCHED_FIFO` threads, RM priorities, `pthread_setaffinity_np()` (CPU 1), bounded Laplace release sampling, and absolute `clock_nanosleep()` releases. No Linux scheduler source code is modified. The `benchmark.c` in this package comes from the previously used reconstructed v2 benchmark.

## 12. Verify and smoke-test **before** collecting full data

First, verify the CSV is complete **without** running any real-time jobs:

```bash
cd ~/Downloads/sarts_200_experiment
DRY_RUN=1 PASS=plain TRIALS=5 DURATION=60 ./run_all.sh
DRY_RUN=1 PASS=trace TRIALS=5 DURATION=60 ./run_all.sh
```

Expected reports: **4000 plain configurations** and **2000 traced configurations**.

Check resources and tracer availability:

```bash
df -h .
grep '^CONFIG_PREEMPT_RT=y' /boot/config-"$(uname -r)"
sudo grep -w pick_task_rt /sys/kernel/tracing/available_filter_functions
command -v vcgencmd
vcgencmd pmic_read_adc | head -10
```

For a short *real* smoke test, create a **separate working copy** of the package with a valid 200-set CSV, set `DURATION=5`, and run the two passes. The runner still iterates all 200 task sets; therefore, smoke testing all configurations remains nontrivial. To test just one task set without contaminating the final dataset, use a separately prepared test runner or the old 10-set v2 package. **Do not run the 60-second full experiment without first confirming that the trace pass extracts both the benchmark's job count and trace events.**

**Trace stdout compatibility:** The new runner parses the benchmark's CSV result from the `trace-cmd record` stdout stream to obtain the *same-run job count*. If your installed `trace-cmd` does not forward that stdout, it stops with an error instead of silently combining mismatched runs. Verify this with a short trace test before committing to the full campaign.

## 13. Run all 200 task sets, five trials each

For a long SSH connection, first create a `tmux` session:

```bash
tmux new -s sarts_200
```

Then, from inside the session:

```bash
cd ~/Downloads/sarts_200_experiment

sudo -E PASS=plain DURATION=60 TRIALS=5 ./run_all.sh && \
sudo -E PASS=trace DURATION=60 TRIALS=5 ./run_all.sh && \
sudo chown -R "$(id -un):$(id -gn)" results_200 && \
python3 summarize_200.py && \
cat results_200/four_metric_summary.csv
```

This performs:

- **Plain:** 200 sets × 5 trials × 2 schedulers × 2 governors = **4000 runs**.
- **Trace:** 200 sets × 5 trials × 2 schedulers × 1 governor = **2000 runs**.
- **Total:** **6000 runs**, each configured for 60 seconds.

The nominal measurement duration alone is **100 hours** (6000 × 60 s), **plus** compilation, runtime initialization, PMIC polling, trace processing, and other overhead. Expect multiple days, not the ~6–9 hours of the earlier ten-set experiment. Ensure adequate cooling, disk storage, stable power and SSH session handling. Trace files can consume substantial space. **Do not claim completion or produce final paper statistics until the 6000 runs really finish.**

The updated runner saves the aggregate CSV after every successful configuration, and **skips completed run keys** when restarted with the same input, so a stopped pass can be resumed. Do not change the input CSV, duration, CPU, or code between a partial run and its resumed runs. If such settings change, start with a fresh output directory instead.

To detach from `tmux`, press `Ctrl+B` then `D`. Reconnect using `tmux attach -t sarts_200`.

## 14. Output files and statistics

After a complete run:

```text
results_200/
├── plain/
│   ├── runtime_all.csv          # randomization overhead and PMIC rail power
│   ├── taskset_0001.csv ...     # task inputs for each set
│   └── <governor>_set<id>_trial<trial>_<scheduler>.csv ...
├── trace/
│   ├── trace_all.csv            # context switches/job and pick_task_rt timing
│   ├── <governor>_set<id>_trial<trial>_<scheduler>.dat ...
│   └── ...
└── four_metric_summary.csv      # two schedulers, four metric families
```

The summarizer refuses incomplete datasets and reports **mean ± sample SD across the 200 task-set means**, after averaging the five trials for each set. This prevents counting five repeated trials of the same task set as five independent task sets. The output includes **five rows** because the single power metric is reported separately for `performance` and `ondemand`.

```bash
python3 summarize_200.py
cat results_200/four_metric_summary.csv
```

Both run-level CSV files retain the unique tuple `(taskset_id, trial, scheduler, governor)` for reproducibility and checking. Raw `.dat` files preserve trace evidence. These results are **not wall-plug power**; the reported values are sums of selected PMIC monitored rail estimates.

## 15. Back up the final 200-task-set experiment

After completion:

```bash
cd ~/Downloads/sarts_200_experiment
sudo chown -R "$(id -un):$(id -gn)" results_200
zip -qr ~/Downloads/SARTS_200sets_5trials_4metrics_results.zip results_200
zip -q ~/Downloads/SARTS_200sets_5trials_4metrics_source.zip \
  README.md benchmark.c run_all.sh runner_200.py summarize_200.py task_parameters_200.csv
```

Record `uname -a`, package versions, compiler version, CPU governor configuration, and the task-set generation seed separately for the artifact/reproducibility statement. Neither the PREEMPT_RT kernel source nor the kernel scheduling algorithm was customized in this implementation.

## 16. Interpretation and limitations

- **Only DPS and S²-EPSILON** are evaluated here. No TS configuration is run or displayed.
- **Four metrics:** benchmark-involved context switches per completed job, `pick_task_rt()` execution time, user-space randomization time, and PMIC rail-power estimate (two governors).
- **Uniprocessor approximation:** all benchmark task threads run on CPU 1, but other Pi cores remain online and CPU 1 is not fully isolated from other Linux work.
- **Workload:** the provided C benchmark simulates CPU execution time, and the inter-arrival bounds must be supplied from prior offline analysis. Results do not independently prove control stability or analytic schedulability.
- **Potential instrumentation effects:** kernel tracing affects execution and can create overhead. Randomization is timed in the separate untraced pass.
- **Frequency:** the governors are policies, not fixed frequencies; do not assert a constant 2.4 GHz without frequency logging.
- **Input availability:** the 200-set CSV is required but is **not included**, so this package cannot honestly produce 200 task-set measurements until it is supplied.
- **Reconstructed implementation:** results measure the v2 reconstructed user-space benchmark, not a bit-identical reproduction of the original kernel-modifying ε-Scheduler implementation.

## References

- Raspberry Pi kernel documentation: https://www.raspberrypi.com/documentation/computers/linux_kernel.html
- Linux real-time scheduling: https://man7.org/linux/man-pages/man7/sched.7.html
- `trace-cmd` options: https://www.trace-cmd.org/Documentation/trace-cmd/trace-cmd-record.1.html
