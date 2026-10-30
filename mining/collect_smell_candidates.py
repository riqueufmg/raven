#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

SMELL_NAMES = {
    "IM": "Insufficient Modularization",
    "HM": "Hub-like Modularization",
    "GC": "God Component",
    "UD": "Unstable Dependency",
}

DEFAULT_SMELLS = ("IM", "HM", "GC", "UD")

EXPECTED_FIELDS = [
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

OUTPUT_FIELDS = [
    "Repository",
    "SmellAlias",
    *EXPECTED_FIELDS,
]


def normalize_smells(values):
    result = []
    seen = set()

    for value in values:
        alias = value.strip().upper()
        if alias not in SMELL_NAMES:
            supported = ", ".join(SMELL_NAMES)
            raise ValueError(
                f"Unsupported smell {value!r}. Supported values: {supported}."
            )

        if alias not in seen:
            seen.add(alias)
            result.append(alias)

    return result


def find_candidate_files(
    results_root: Path,
    smells,
    repositories=None,
):
    found = []

    selected_repositories = (
        set(repositories)
        if repositories
        else None
    )

    for repo_dir in sorted(results_root.iterdir()):
        if not repo_dir.is_dir():
            continue

        if (
            selected_repositories is not None
            and repo_dir.name not in selected_repositories
        ):
            continue

        candidates_dir = repo_dir / "candidates"
        if not candidates_dir.is_dir():
            continue

        for alias in smells:
            csv_path = candidates_dir / f"{alias}_candidates.csv"
            if csv_path.is_file():
                found.append((repo_dir.name, alias, csv_path))

    return found


def read_candidates(repository, alias, path: Path, include_all):
    rows = []

    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            return rows

        missing = set(EXPECTED_FIELDS).difference(reader.fieldnames)
        if missing:
            raise RuntimeError(
                f"{path} is missing expected columns: {sorted(missing)}. "
                f"Found: {reader.fieldnames}"
            )

        for row in reader:
            classification = (row.get("Classification") or "").strip()

            if not include_all and classification != "smell_removed_candidate":
                continue

            output_row = {
                "Repository": repository,
                "SmellAlias": alias,
            }

            for field in EXPECTED_FIELDS:
                output_row[field] = (row.get(field) or "").strip()

            rows.append(output_row)

    return rows


def deduplicate_rows(rows):
    unique = {}

    for row in rows:
        key = (
            row["Repository"],
            row["SmellAlias"],
            row["Entity"],
            row["CommitWithSmell"],
            row["CommitWithoutSmell"],
        )
        unique[key] = row

    return list(unique.values())


def write_output(output: Path, rows):
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Consolidate candidate CSVs produced by analyze_results.py "
            "across multiple repositories."
        )
    )

    parser.add_argument(
        "--results-root",
        required=True,
        type=Path,
        help="Directory containing one subdirectory per repository.",
    )

    parser.add_argument(
        "--smells",
        nargs="+",
        default=list(DEFAULT_SMELLS),
        metavar="SMELL",
        help="Smell aliases to consolidate: IM HM GC UD. Default: all four.",
    )

    parser.add_argument(
        "--repositories",
        nargs="+",
        metavar="REPOSITORY",
        help=(
            "Repository directory names to include. "
            "Defaults to all repositories under --results-root."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output CSV path. Default: <results-root>/smell_candidates.csv.",
    )

    parser.add_argument(
        "--include-all",
        action="store_true",
        help=(
            "Include all transitions instead of only "
            "Classification=smell_removed_candidate."
        ),
    )

    args = parser.parse_args()

    results_root = args.results_root.expanduser().resolve()
    if not results_root.is_dir():
        raise NotADirectoryError(
            f"Results root does not exist: {results_root}"
        )

    smells = normalize_smells(args.smells)

    output = (
        args.output.expanduser().resolve()
        if args.output
        else results_root / "smell_candidates.csv"
    )

    candidate_files = find_candidate_files(
        results_root,
        smells,
        args.repositories,
    )

    if not candidate_files:
        raise RuntimeError(
            "No candidate CSV files were found for the requested smells."
        )

    all_rows = []
    files_per_smell = {alias: 0 for alias in smells}
    rows_per_smell = {alias: 0 for alias in smells}
    repositories_seen = set()

    for repository, alias, path in candidate_files:
        repositories_seen.add(repository)
        files_per_smell[alias] += 1

        rows = read_candidates(
            repository=repository,
            alias=alias,
            path=path,
            include_all=args.include_all,
        )

        rows_per_smell[alias] += len(rows)
        all_rows.extend(rows)

    before_dedup = len(all_rows)
    all_rows = deduplicate_rows(all_rows)
    all_rows.sort(
        key=lambda row: (
            row["SmellAlias"],
            row["Repository"].casefold(),
            row["Entity"].casefold(),
            row["CommitWithSmell"],
        )
    )

    write_output(output, all_rows)

    print(f"Repositories scanned: {len(repositories_seen)}")
    print(f"Candidate files read: {len(candidate_files)}")
    print(
        "Filter: "
        + (
            "all transitions"
            if args.include_all
            else "Classification=smell_removed_candidate"
        )
    )

    for alias in smells:
        print(
            f"{alias}: "
            f"{rows_per_smell[alias]} rows from "
            f"{files_per_smell[alias]} repositories"
        )

    print(f"Rows before deduplication: {before_dedup}")
    print(f"Consolidated rows:         {len(all_rows)}")
    print(f"Output:                    {output}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValueError,
        NotADirectoryError,
        RuntimeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
