#!/usr/bin/env python3
import argparse
import copy
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

from plotbenchmark import generate_plots


SCRIPT_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = SCRIPT_DIR / "docker_compose" / "docker_compose.yml"
TEMPLATE_MINIMAL = SCRIPT_DIR.parent / "integration_tests" / "bodies" / "post" / "postAssetAdministrationShellMinimal.json"
TEMPLATE_COMPLEX = SCRIPT_DIR.parent / "integration_tests" / "bodies" / "post" / "postAssetAdministrationShellComplex.json"
RESULTS_DIR = SCRIPT_DIR / "results"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def detect_compose_cmd():
    override = os.environ.get("BENCH_COMPOSE_CMD", "").strip()
    if override:
        return override

    candidates = ["podman compose", "docker compose"]
    for candidate in candidates:
        probe = subprocess.run(
            f"{candidate} version",
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return candidate

    raise RuntimeError(
        "Neither 'podman compose' nor 'docker compose' is available. "
        "Set BENCH_COMPOSE_CMD to override."
    )


def run_cmd(cmd, check=True):
    print(f"[{ts()}] ▶ {cmd}")
    result = subprocess.run(cmd, shell=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {cmd}")
    return result


def compose_down(compose_cmd):
    run_cmd(f"{compose_cmd} -f \"{COMPOSE_FILE}\" down -v", check=False)


def compose_up(compose_cmd):
    run_cmd(f"{compose_cmd} -f \"{COMPOSE_FILE}\" up -d --build", check=True)


def wait_for_http(url, timeout_sec=240):
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code < 500:
                print(f"[{ts()}] Service ready at {url} (HTTP {response.status_code})")
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def load_template(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def make_payload(template, scenario, seq):
    payload = copy.deepcopy(template)
    aas_uuid = uuid.uuid4()
    payload["id"] = f"https://example.com/ids/aas/{scenario}/{seq}-{aas_uuid}"

    if "idShort" in payload and isinstance(payload["idShort"], str):
        payload["idShort"] = f"{payload['idShort']}_{seq}"

    asset_info = payload.get("assetInformation")
    if isinstance(asset_info, dict) and "globalAssetId" in asset_info:
        asset_info["globalAssetId"] = f"asset-{scenario}-{seq}-{aas_uuid}"

    if isinstance(payload.get("submodels"), list):
        for idx, sm_ref in enumerate(payload["submodels"]):
            if not isinstance(sm_ref, dict):
                continue
            keys = sm_ref.get("keys")
            if not isinstance(keys, list):
                continue
            for key in keys:
                if isinstance(key, dict) and key.get("type") == "Submodel":
                    key["value"] = f"https://example.com/ids/sm/{scenario}/{seq}-{idx}-{uuid.uuid4()}"

    return payload


def run_scenario(
    compose_cmd,
    scenario,
    template_path,
    target_url,
    total_posts,
    progress_every,
    output_dir,
    manage_compose,
):
    health_url = target_url.rsplit("/", 1)[0] + "/health"

    print(f"[{ts()}] Starting scenario={scenario}, total_posts={total_posts}")
    if manage_compose:
        compose_down(compose_cmd)
        compose_up(compose_cmd)

    if not wait_for_http(health_url):
        raise RuntimeError(f"Service did not become ready at {health_url}")

    template = load_template(template_path)
    status_codes = Counter()
    error_categories = Counter()
    latencies_ms = []
    success_count = 0
    failure_count = 0
    start_time = time.perf_counter()

    session = requests.Session()

    for i in range(1, total_posts + 1):
        payload = make_payload(template, scenario, i)
        req_start = time.perf_counter()
        try:
            response = session.post(target_url, json=payload, timeout=30)
            elapsed_ms = (time.perf_counter() - req_start) * 1000.0
            latencies_ms.append(elapsed_ms)
            status_codes[str(response.status_code)] += 1

            if 200 <= response.status_code <= 299:
                success_count += 1
            else:
                failure_count += 1
                error_categories[f"http_{response.status_code}"] += 1

        except requests.RequestException as ex:
            elapsed_ms = (time.perf_counter() - req_start) * 1000.0
            latencies_ms.append(elapsed_ms)
            failure_count += 1
            error_categories[type(ex).__name__] += 1

        if i % progress_every == 0:
            elapsed = time.perf_counter() - start_time
            current_rps = i / elapsed if elapsed > 0 else 0.0
            print(
                f"[{ts()}] {scenario}: {i}/{total_posts} done | "
                f"success={success_count} failure={failure_count} throughput={current_rps:.2f} req/s"
            )

    total_time_sec = time.perf_counter() - start_time
    sorted_lat = sorted(latencies_ms)
    throughput = total_posts / total_time_sec if total_time_sec > 0 else 0.0

    summary = {
        "scenario": scenario,
        "timestamp": datetime.now().isoformat(),
        "total_requests": total_posts,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate_pct": (success_count / total_posts) * 100.0 if total_posts else 0.0,
        "total_duration_sec": total_time_sec,
        "throughput_req_per_sec": throughput,
        "latency_ms": {
            "min": sorted_lat[0] if sorted_lat else 0.0,
            "max": sorted_lat[-1] if sorted_lat else 0.0,
            "p50": percentile(sorted_lat, 50),
            "p95": percentile(sorted_lat, 95),
            "p99": percentile(sorted_lat, 99),
        },
        "status_codes": dict(status_codes),
        "error_categories": dict(error_categories),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"{scenario}_summary.json"
    latencies_path = output_dir / f"{scenario}_latencies.json"

    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    with latencies_path.open("w", encoding="utf-8") as file:
        json.dump(latencies_ms, file)

    plots = generate_plots(summary_path, latencies_path)

    print(f"[{ts()}] Scenario {scenario} done.")
    print(
        f"[{ts()}] Summary: success_rate={summary['success_rate_pct']:.2f}% "
        f"throughput={summary['throughput_req_per_sec']:.2f} req/s "
        f"p50={summary['latency_ms']['p50']:.2f}ms "
        f"p95={summary['latency_ms']['p95']:.2f}ms "
        f"p99={summary['latency_ms']['p99']:.2f}ms"
    )
    print(f"[{ts()}] Artifacts: {summary_path}, {latencies_path}")
    if plots:
        print(f"[{ts()}] Plot files: {', '.join(str(p) for p in plots)}")


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark AAS Repository POST /shells with two sequential scenarios: "
            "minimal and complex payload, each defaulting to 100k requests."
        )
    )
    parser.add_argument(
        "--total-posts",
        type=int,
        default=int(os.environ.get("BENCH_TOTAL_POSTS", "100000")),
        help="Requests per scenario.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=int(os.environ.get("BENCH_PROGRESS_EVERY", "5000")),
        help="Progress log interval.",
    )
    parser.add_argument(
        "--target-url",
        default=os.environ.get("BENCH_TARGET_URL", "http://localhost:6104/shells"),
        help="AAS Repository POST endpoint.",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=["minimal", "complex", "both"],
        default=None,
        help="Scenario selection.",
    )
    parser.add_argument(
        "--no-clean-results",
        action="store_true",
        help="Do not remove old result folders before writing new outputs.",
    )
    parser.add_argument(
        "--manage-compose",
        choices=["true", "false"],
        default="true",
        help="When true, the script controls compose up/down. Use false in container-runner mode.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    manage_compose = args.manage_compose == "true"

    if args.total_posts <= 0:
        raise ValueError("--total-posts must be > 0")
    if args.progress_every <= 0:
        raise ValueError("--progress-every must be > 0")

    compose_cmd = None
    if manage_compose:
        compose_cmd = detect_compose_cmd()
        print(f"[{ts()}] Using compose command: {compose_cmd}")
    else:
        print(f"[{ts()}] Running in external environment mode (no compose management).")

    stop_state = {"requested": False}

    def on_signal(sig, _frame):
        print(f"[{ts()}] Received signal={sig}; cleaning up compose stack.")
        stop_state["requested"] = True
        if manage_compose and compose_cmd:
            compose_down(compose_cmd)
        sys.exit(1)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / run_id
    if run_dir.exists() and not args.no_clean_results:
        shutil.rmtree(run_dir)

    scenario_tokens = args.scenarios
    if not scenario_tokens:
        raw = os.environ.get("BENCH_SCENARIOS", "minimal")
        scenario_tokens = [token.strip() for token in raw.split(",") if token.strip()]
    scenario_order = ["minimal", "complex"] if "both" in scenario_tokens else scenario_tokens

    allowed = {"minimal", "complex"}
    if not scenario_order or any(item not in allowed for item in scenario_order):
        raise ValueError("Scenario selection must be minimal, complex, or both")
    if not manage_compose and len(scenario_order) > 1:
        print(
            f"[{ts()}] Warning: running multiple scenarios without compose reset between them. "
            "Use separate runs if strict fresh-db isolation is required."
        )

    templates = {
        "minimal": TEMPLATE_MINIMAL,
        "complex": TEMPLATE_COMPLEX,
    }

    try:
        for scenario in scenario_order:
            if stop_state["requested"]:
                break
            run_scenario(
                compose_cmd=compose_cmd,
                scenario=scenario,
                template_path=templates[scenario],
                target_url=args.target_url,
                total_posts=args.total_posts,
                progress_every=args.progress_every,
                output_dir=run_dir,
                manage_compose=manage_compose,
            )
    finally:
        if manage_compose and compose_cmd:
            compose_down(compose_cmd)

    print(f"[{ts()}] Benchmark finished. Run folder: {run_dir}")


if __name__ == "__main__":
    main()
