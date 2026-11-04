# Raspberry Pi 5 PREEMPT_RT setup and experimental data collection

**Project:** S²-EPSILON / SARTS — four hardware metrics, 200 task sets × 5 trials  
**Platform used:** Raspberry Pi 5 (8 GB RAM), 64-bit Debian 12 (Bookworm), ARM64, microSD storage  
**Verified experimental kernel:** `6.12.109+rpt-rpi-v8-rt` with `CONFIG_PREEMPT_RT=y`  
**Scheduling:** Preemptive fixed priority (`SCHED_FIFO`) with Rate-Monotonic (RM) priority assignment  
**Benchmark CPU:** CPU 1 (all four Raspberry Pi 5 cores remain enabled)



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

## 2. Install the prebuilt PREEMPT_RT kernel

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

### 2.1 Select the real-time kernel for boot

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

## 3. Verify that the correct kernel is running


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


## 4. Install the benchmark and tracing dependencies

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

## 5. Check real-time scheduling support

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

## 6. Verify the CPU frequency governor

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


## 7. Check the tracing interface and kernel function names

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


### 7.1 Smoke-test function tracing on CPU 1

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

## 8. Three hardware metrics reported in the paper


| Paper metric | Collection method | Saved field |
|---|---|---|
| **(1) Kernel task-selection time** | `function_graph` timing of `pick_task_rt()` on CPU 1 | `pick_task_rt_mean_us` |
| **(2) Randomization function time** | User-space function timer from an **untraced** performance-governor run | `randomization_mean_us` |
| **(3) Power consumption** | PMIC monitored-rail estimate from **untraced** runs under both `performance` and `ondemand` governors | `pmic_rail_W` |

## 9. Input requirement: 200 distinct task sets

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


## 10. Install the updated collection package

Extract `rpi_linux_kernel_setup.zip` on the Pi, or copy its files into a new directory:

```bash
cd ~/Downloads
unzip rpi_linux_kernel_setup.zip -d sarts_200_experiment
cd sarts_200_experiment
chmod +x run_all.sh
```

Expected files:

```text
benchmark.c
run_all.sh
runner_200.py
summarize_200.py
```


## 11. Run all 200 task sets, five trials each

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

## 12. Output files and statistics

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


## References

- Raspberry Pi kernel documentation: https://www.raspberrypi.com/documentation/computers/linux_kernel.html
- Linux real-time scheduling: https://man7.org/linux/man-pages/man7/sched.7.html
- `trace-cmd` options: https://www.trace-cmd.org/Documentation/trace-cmd/trace-cmd-record.1.html
