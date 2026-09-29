#!/usr/bin/env python3
"""Summarize per-instance SWE-Explore metrics produced by eval_runner."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


METRICS = [
    "precision",
    "recall",
    "f1_score",
    "hit_file_rate",
    "noise_file_rate",
    "hit_region_rate",
    "noise_region_rate",
    "weighted_core_coverage",
    "context_efficiency",
    "optional_coverage",
    "ndcg_at_100",
    "ndcg_at_300",
    "ndcg_at_500",
    "recall_at_100",
    "recall_at_300",
    "recall_at_500",
    "first_useful_hit",
]


def summarize(rows: list[dict]) -> dict:
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        instance_id = row.get("instance_id", "")
        by_repo[instance_id.split("__", 1)[0]].append(row)

    def stats(subset: list[dict]) -> dict:
        out: dict[str, dict[str, float]] = {}
        for metric in METRICS:
            values = [float(row.get("metrics", {}).get(metric, 0.0)) for row in subset]
            out[metric] = {
                "mean": statistics.fmean(values) if values else 0.0,
                "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
                "median": statistics.median(values) if values else 0.0,
            }
        return out

    threshold_metrics = [
        "hit_file_rate",
        "hit_region_rate",
        "precision",
        "recall",
        "f1_score",
        "first_useful_hit",
    ]
    threshold_counts = {}
    for metric in threshold_metrics:
        values = [float(row.get("metrics", {}).get(metric, 0.0)) for row in rows]
        threshold_counts[metric] = {
            "gt_zero": sum(value > 0 for value in values),
            "ge_half": sum(value >= 0.5 for value in values),
            "eq_zero": sum(value == 0 for value in values),
        }

    return {
        "num_records": len(rows),
        "num_unique_instances": len({row.get("instance_id") for row in rows}),
        "explorers": sorted({row.get("explorer") for row in rows}),
        "num_regions": {
            str(k): v
            for k, v in sorted(
                __import__("collections").Counter(row.get("num_regions", 0) for row in rows).items()
            )
        },
        "macro": stats(rows),
        "threshold_counts": threshold_counts,
        "by_repository": {
            repo: {
                "num_records": len(repo_rows),
                "macro": stats(repo_rows),
            }
            for repo, repo_rows in sorted(by_repo.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results/metrics"))
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.predictions.read_text().splitlines()
        if line.strip()
    ]
    summary = summarize(rows)
    summary["source"] = str(args.predictions)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    json_path = args.output_dir / "cosil_top5_summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    csv_path = args.output_dir / "cosil_top5_macro.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "mean", "std", "median"])
        for metric, values in summary["macro"].items():
            writer.writerow([metric, values["mean"], values["std"], values["median"]])

    print(f"records: {summary['num_records']}")
    print(f"wrote: {json_path}")
    print(f"wrote: {csv_path}")
    for metric in METRICS:
        print(f"{metric}: {summary['macro'][metric]['mean']:.9f}")


if __name__ == "__main__":
    main()
