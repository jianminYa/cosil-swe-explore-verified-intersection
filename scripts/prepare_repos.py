#!/usr/bin/env python3
"""Materialize immutable SWE-bench base-commit snapshots for the intersection."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        list(args), cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", type=Path, required=True)
    parser.add_argument("--repos-root", type=Path, default=Path("repos"))
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.bench.read_text().splitlines() if line.strip()]
    by_repo: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_repo[row["repo"]].add(row["base_commit"])

    root = args.repos_root.resolve()
    mirrors = root / ".mirrors"
    snapshots = root / ".snapshots"
    mirrors.mkdir(parents=True, exist_ok=True)
    snapshots.mkdir(parents=True, exist_ok=True)

    manifest = []
    for repo in sorted(by_repo):
        owner, name = repo.split("/", 1)
        mirror = mirrors / f"{owner}__{name}.git"
        if not mirror.exists():
            run("git", "clone", "--mirror", f"https://github.com/{repo}.git", str(mirror))
        else:
            run("git", "remote", "update", "--prune", cwd=mirror)

        for commit in sorted(by_repo[repo]):
            snapshot_name = f"{owner}__{name}__{commit}"
            snapshot = snapshots / snapshot_name
            if not snapshot.exists():
                run("git", "cat-file", "-e", f"{commit}^{{commit}}", cwd=mirror)
                run("git", "worktree", "add", "--detach", str(snapshot), commit, cwd=mirror)
            else:
                current = run("git", "rev-parse", "HEAD", cwd=snapshot)
                if current != commit:
                    raise RuntimeError(
                        f"snapshot exists at {snapshot} but is {current}, expected {commit}"
                    )

    for row in rows:
        owner, name = row["repo"].split("/", 1)
        snapshot_name = f"{owner}__{name}__{row['base_commit']}"
        link = root / row["instance_id"]
        target = Path(".snapshots") / snapshot_name
        if link.is_symlink():
            if link.resolve() != (root / target).resolve():
                raise RuntimeError(f"unexpected repository symlink: {link}")
        elif link.exists():
            raise RuntimeError(f"repository path exists and is not a symlink: {link}")
        else:
            link.symlink_to(target)
        manifest.append({
            "instance_id": row["instance_id"],
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "snapshot": str((root / target).relative_to(root)),
            "repo_link": str(link.relative_to(root)),
        })

    (root / "repo_snapshot_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({
        "instances": len(rows),
        "repositories": len(by_repo),
        "unique_base_commit_snapshots": sum(len(v) for v in by_repo.values()),
        "repo_links": len(manifest),
        "repos_root": str(root),
    }, indent=2))


if __name__ == "__main__":
    main()
