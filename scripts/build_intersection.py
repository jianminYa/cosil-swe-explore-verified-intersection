#!/usr/bin/env python3
"""Build the 451-instance SWE-Explore/Verified intersection.

The released SWE-Explore JSONL contains benchmark ground truth and repository
paths but intentionally omits the full SWE-bench issue record.  This script
joins it with the pinned SWE-bench Verified parquet by ``instance_id`` and
emits both the evaluator input and the CoSIL input dataset.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swe-explore", type=Path, required=True)
    parser.add_argument("--verified", type=Path, required=True)
    parser.add_argument("--bench-output", type=Path, required=True)
    parser.add_argument("--cosil-output", type=Path, required=True)
    parser.add_argument("--issue-map-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()

    explore_rows = read_jsonl(args.swe_explore)
    verified_rows = pq.read_table(args.verified).to_pylist()
    verified_by_id = {str(row["instance_id"]): row for row in verified_rows}

    intersection: list[dict[str, Any]] = []
    missing_fields: list[str] = []
    for explore in explore_rows:
        instance_id = str(explore["instance_id"])
        if instance_id not in verified_by_id:
            continue
        verified = verified_by_id[instance_id]
        record = dict(explore)
        for field in (
            "repo",
            "base_commit",
            "problem_statement",
            "patch",
            "test_patch",
            "FAIL_TO_PASS",
            "PASS_TO_PASS",
            "environment_setup_commit",
            "version",
            "difficulty",
        ):
            if field in verified:
                record[field] = verified[field]
        record["dataset"] = "verified"
        record["repo_dir"] = record.get("repo_dir") or f"repos/{instance_id}"
        if not record.get("problem_statement") or not record.get("base_commit"):
            missing_fields.append(instance_id)
        intersection.append(record)

    if missing_fields:
        raise SystemExit(f"Missing required Verified fields for: {missing_fields[:5]}")

    intersection.sort(key=lambda row: row["instance_id"])
    cosil_rows = [
        {
            "instance_id": row["instance_id"],
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "problem_statement": row["problem_statement"],
            "patch": row.get("patch", ""),
        }
        for row in intersection
    ]
    issue_map = {row["instance_id"]: row["problem_statement"] for row in intersection}
    manifest = [
        {
            "instance_id": row["instance_id"],
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "repo_dir": row["repo_dir"],
        }
        for row in intersection
    ]

    write_jsonl(args.bench_output, intersection)
    write_jsonl(args.cosil_output, cosil_rows)
    args.issue_map_output.parent.mkdir(parents=True, exist_ok=True)
    args.issue_map_output.write_text(json.dumps(issue_map, ensure_ascii=False, indent=2))
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    print(json.dumps({
        "swe_explore_rows": len(explore_rows),
        "verified_rows": len(verified_rows),
        "intersection_rows": len(intersection),
        "output": str(args.bench_output),
    }, indent=2))


if __name__ == "__main__":
    main()

