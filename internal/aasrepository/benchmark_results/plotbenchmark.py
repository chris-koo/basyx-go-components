#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def _load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _maybe_import_matplotlib():
    try:
        import matplotlib.pyplot as plt

        return plt
    except Exception as ex:
        print(f"Plot generation skipped (matplotlib unavailable): {ex}")
        return None


def _save_all_formats(fig, base_path):
    png = base_path.with_suffix(".png")
    pdf = base_path.with_suffix(".pdf")
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    return [png, pdf]


def generate_plots(summary_path, latencies_path):
    summary_path = Path(summary_path)
    latencies_path = Path(latencies_path)

    plt = _maybe_import_matplotlib()
    if plt is None:
        return []

    summary = _load_json(summary_path)
    latencies = _load_json(latencies_path)

    if not isinstance(latencies, list) or not latencies:
        print(f"No latency data in {latencies_path}; skipping plots.")
        return []

    scenario = summary.get("scenario", "unknown")
    output_prefix = summary_path.parent / f"{scenario}_benchmark"

    created = []

    fig1 = plt.figure(figsize=(10, 4.8))
    ax1 = fig1.add_subplot(1, 1, 1)
    ax1.plot(latencies, linewidth=0.8, color="#0f766e")
    ax1.set_title(f"{scenario} latency per request")
    ax1.set_xlabel("Request index")
    ax1.set_ylabel("Latency (ms)")
    ax1.grid(True, linestyle="--", alpha=0.4)
    fig1.tight_layout()
    created.extend(_save_all_formats(fig1, output_prefix.with_name(f"{output_prefix.name}_timeseries")))
    plt.close(fig1)

    fig2 = plt.figure(figsize=(10, 4.8))
    ax2 = fig2.add_subplot(1, 1, 1)
    ax2.hist(latencies, bins=80, color="#1d4ed8", alpha=0.85)
    ax2.set_title(f"{scenario} latency distribution")
    ax2.set_xlabel("Latency (ms)")
    ax2.set_ylabel("Count")
    ax2.grid(True, linestyle="--", alpha=0.4)
    fig2.tight_layout()
    created.extend(_save_all_formats(fig2, output_prefix.with_name(f"{output_prefix.name}_distribution")))
    plt.close(fig2)

    return created


def main():
    parser = argparse.ArgumentParser(description="Generate png/pdf plots for benchmark outputs.")
    parser.add_argument("summary", type=Path, help="Path to scenario summary JSON.")
    parser.add_argument("latencies", type=Path, help="Path to scenario latency JSON.")
    args = parser.parse_args()

    files = generate_plots(args.summary, args.latencies)
    if files:
        print("Generated plot files:")
        for file in files:
            print(file)


if __name__ == "__main__":
    main()
