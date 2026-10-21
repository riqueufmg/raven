#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

csv.field_size_limit(sys.maxsize)

HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")

SMELLS = {
    "IM": ("Insufficient Modularization", "DesignSmells.csv", "class"),
    "HM": ("Hub-like Modularization", "DesignSmells.csv", "class"),
    "GC": ("God Component", "ArchitectureSmells.csv", "package"),
    "UD": ("Unstable Dependency", "ArchitectureSmells.csv", "package"),
}


@dataclass(frozen=True)
class Occurrence:
    entity: str
    package: str
    class_name: str
    file: str


def run(cmd: Sequence[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"{result.stderr.strip()}"
        )
    return result


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(["git", "-C", str(repo), *args], check=check).stdout.strip()


def validate_repo(repo: Path) -> None:
    if not repo.is_dir():
        raise NotADirectoryError(f"Repository not found: {repo}")
    if git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        raise ValueError(f"Not a Git repository: {repo}")


def resolve_branch(repo: Path, branch: str | None) -> str:
    if branch:
        git(repo, "rev-parse", "--verify", f"{branch}^{{commit}}")
        return branch

    branch = git(repo, "branch", "--show-current")
    if not branch:
        raise ValueError("Detached HEAD. Supply --branch.")
    return branch


def result_commits(repo_results: Path) -> set[str]:
    commits = {
        p.name.lower()
        for p in repo_results.iterdir()
        if p.is_dir() and HASH_RE.fullmatch(p.name)
    }
    if not commits:
        raise RuntimeError(f"No commit directories found in {repo_results}")
    return commits


def ordered_result_commits(
    repo: Path,
    branch: str,
    available: set[str],
) -> list[str]:
    history = git(repo, "rev-list", "--reverse", "--topo-order", branch).splitlines()
    ordered = [c for c in history if c.lower() in available]
    if not ordered:
        raise RuntimeError("No result commits are reachable from the selected branch.")
    return ordered


def first_parent(repo: Path, commit: str) -> str | None:
    r = run(
        ["git", "-C", str(repo), "rev-parse", f"{commit}^1"],
        check=False,
    )
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def read_occurrences(
    commit_dir: Path,
    alias: str,
) -> dict[str, Occurrence]:
    smell, csv_name, granularity = SMELLS[alias]
    csv_path = commit_dir / csv_name

    if not csv_path.is_file():
        raise FileNotFoundError(f"Missing result file: {csv_path}")

    occurrences: dict[str, Occurrence] = {}

    with csv_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            return occurrences

        required = {"Package", "Smell"}
        if granularity == "class":
            required.add("Class")

        missing = required.difference(reader.fieldnames)
        if missing:
            raise RuntimeError(
                f"{csv_path} is missing columns {sorted(missing)}. "
                f"Found: {reader.fieldnames}"
            )

        for row in reader:
            if (row.get("Smell") or "").strip().casefold() != smell.casefold():
                continue

            package = (row.get("Package") or "").strip()
            class_name = (row.get("Class") or "").strip()
            file_path = (row.get("File") or "").strip()

            if granularity == "class":
                entity = (
                    f"{package}.{class_name}"
                    if package and class_name
                    else class_name or package
                )
            else:
                entity = package

            if entity:
                occurrences[entity] = Occurrence(
                    entity=entity,
                    package=package,
                    class_name=class_name,
                    file=file_path,
                )

    return occurrences


def java_files(repo: Path, commit: str) -> list[str]:
    return [
        p.strip().replace("\\", "/")
        for p in git(repo, "ls-tree", "-r", "--name-only", commit).splitlines()
        if p.strip().endswith(".java")
    ]


def class_exists(
    occurrence: Occurrence,
    files: Sequence[str],
) -> bool | None:
    suffixes: list[str] = []

    if occurrence.file:
        normalized = occurrence.file.replace("\\", "/").lstrip("./")
        suffixes.append(normalized)

    if occurrence.package and occurrence.class_name:
        suffixes.append(
            occurrence.package.replace(".", "/")
            + "/"
            + occurrence.class_name
            + ".java"
        )

    if not suffixes:
        return None

    return any(
        any(path.endswith(suffix) for suffix in suffixes)
        for path in files
    )


def package_exists(
    occurrence: Occurrence,
    files: Sequence[str],
) -> bool | None:
    if not occurrence.package:
        return None

    package_path = occurrence.package.replace(".", "/").strip("/")
    marker = f"/{package_path}/"

    for path in files:
        padded = "/" + path.lstrip("/")
        if marker in padded or padded.startswith(f"/{package_path}/"):
            return True

    return False


def entity_exists(
    occurrence: Occurrence,
    granularity: str,
    files: Sequence[str],
) -> bool | None:
    if granularity == "class":
        return class_exists(occurrence, files)
    return package_exists(occurrence, files)


def classify(
    is_direct_child: bool,
    exists: bool | None,
) -> tuple[str, str]:
    if not is_direct_child:
        return "unknown", "invalid_non_parent_transition"
    if exists is True:
        return "true", "smell_removed_candidate"
    if exists is False:
        return "false", "entity_missing_after"
    return "unknown", "entity_existence_unknown"


def analyze_smell(
    repo: Path,
    repo_results: Path,
    commits: Sequence[str],
    alias: str,
) -> list[dict[str, str]]:
    smell, _, granularity = SMELLS[alias]

    by_commit = {
        commit: read_occurrences(repo_results / commit, alias)
        for commit in commits
    }

    rows: list[dict[str, str]] = []

    for previous_commit, current_commit in zip(commits, commits[1:]):
        before = by_commit[previous_commit]
        after = by_commit[current_commit]

        removed = sorted(set(before) - set(after))
        if not removed:
            continue

        parent = first_parent(repo, current_commit)
        direct = parent == previous_commit

        files = java_files(repo, current_commit) if direct else []

        for entity in removed:
            occurrence = before[entity]
            exists = (
                entity_exists(occurrence, granularity, files)
                if direct
                else None
            )
            exists_text, classification = classify(direct, exists)

            rows.append(
                {
                    "Smell": smell,
                    "Entity": entity,
                    "Granularity": granularity,
                    "CommitWithSmell": previous_commit,
                    "CommitWithoutSmell": current_commit,
                    "FirstParentOfCommitWithoutSmell": parent or "",
                    "IsDirectChild": str(direct).lower(),
                    "EntityExistsAfter": exists_text,
                    "Classification": classification,
                    "Package": occurrence.package,
                    "Class": occurrence.class_name,
                    "FileBefore": occurrence.file,
                }
            )

    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "Smell",
        "Entity",
        "Granularity",
        "CommitWithSmell",
        "CommitWithoutSmell",
        "FirstParentOfCommitWithoutSmell",
        "IsDirectChild",
        "EntityExistsAfter",
        "Classification",
        "Package",
        "Class",
        "FileBefore",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read DesigniteJava results for one repository and generate "
            "candidate-removal CSVs for IM, HM, GC, and UD."
        )
    )
    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        help="Git repository path, e.g. data/repositories/javaparser",
    )
    parser.add_argument(
        "--results-root",
        required=True,
        type=Path,
        help=(
            "Root containing <repo_name>/<commit_hash>/, "
            "e.g. samples/results"
        ),
    )
    parser.add_argument(
        "--branch",
        help="Branch used for Git ordering. Defaults to current branch.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Output directory. Default: "
            "<results-root>/<repo_name>/candidates"
        ),
    )

    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    results_root = args.results_root.expanduser().resolve()

    validate_repo(repo)
    branch = resolve_branch(repo, args.branch)

    repo_name = repo.name
    repo_results = results_root / repo_name

    if not repo_results.is_dir():
        raise NotADirectoryError(f"Results not found: {repo_results}")

    output = (
        args.output.expanduser().resolve()
        if args.output
        else repo_results / "candidates"
    )

    available = result_commits(repo_results)
    commits = ordered_result_commits(repo, branch, available)

    print(f"Repository: {repo}")
    print(f"Results:    {repo_results}")
    print(f"Branch:     {branch}")
    print(f"Commits:    {len(commits)}")
    print(f"Output:     {output}")

    for alias in ("IM", "HM", "GC", "UD"):
        rows = analyze_smell(
            repo=repo,
            repo_results=repo_results,
            commits=commits,
            alias=alias,
        )

        path = output / f"{alias}_candidates.csv"
        write_csv(path, rows)

        direct = sum(r["IsDirectChild"] == "true" for r in rows)
        invalid = len(rows) - direct
        valid_candidates = sum(
            r["Classification"] == "smell_removed_candidate"
            for r in rows
        )

        print(
            f"{alias}: {len(rows)} transitions; "
            f"{direct} direct parent-child; "
            f"{invalid} non-parent pairs; "
            f"{valid_candidates} removal candidates"
        )
        print(f"  -> {path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValueError,
        FileNotFoundError,
        NotADirectoryError,
        RuntimeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)