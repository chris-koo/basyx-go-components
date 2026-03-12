# AAS Repository POST Benchmark

This benchmark posts Asset Administration Shells to `POST /shells` in two separate runs:

1. `minimal` payload scenario (default: 100000 requests)
2. `complex` payload scenario (default: 100000 requests)

The recommended execution mode is containerized, so no local Python installation is required.

## Prerequisites

1. `podman compose` or `docker compose`.

## Containerized run (recommended)

Run commands from this folder:

`internal/aasrepository/benchmark_results`

The benchmark runner is part of compose under the `benchmark` profile.

### One command for both scenarios (recommended)

This helper runs `minimal` and `complex` sequentially and resets DB volumes between runs:

```powershell
.\run_benchmarks.ps1
```

The helper auto-creates the local `results` directory before starting compose, which is required for podman bind mounts.

Optional parameters:

```powershell
.\run_benchmarks.ps1 -TotalPosts 100000 -ProgressEvery 5000 -ComposeCommand "docker compose"
```

If you use podman:

```powershell
.\run_benchmarks.ps1 -ComposeCommand "podman compose"
```

### 1) Minimal payload benchmark with fresh DB

```bash
set BENCH_SCENARIOS=minimal
set BENCH_TOTAL_POSTS=100000
set BENCH_PROGRESS_EVERY=5000
docker compose -f docker_compose/docker_compose.yml --profile benchmark up --build --abort-on-container-exit aas_repository_benchmark_runner
docker compose -f docker_compose/docker_compose.yml down -v
```

### 2) Complex payload benchmark with fresh DB

```bash
set BENCH_SCENARIOS=complex
set BENCH_TOTAL_POSTS=100000
set BENCH_PROGRESS_EVERY=5000
docker compose -f docker_compose/docker_compose.yml --profile benchmark up --build --abort-on-container-exit aas_repository_benchmark_runner
docker compose -f docker_compose/docker_compose.yml down -v
```

## Optional local Python run

You can still run locally if needed:

```bash
pip install -r requirements.txt
python benchmark.py
```

## Output

Outputs are written to timestamped run folders:

`results/YYYYMMDD_HHMMSS/`

Per scenario artifacts:

1. `<scenario>_summary.json`
2. `<scenario>_latencies.json`
3. `<scenario>_benchmark_timeseries.png`
4. `<scenario>_benchmark_timeseries.pdf`
5. `<scenario>_benchmark_distribution.png`
6. `<scenario>_benchmark_distribution.pdf`

The summary JSON includes:

1. total requests
2. success/failure counts
3. success rate
4. total duration
5. throughput (`req/s`)
6. p50/p95/p99 latency
7. status code counts
8. error category counts
