#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MINING_RESULTS = ROOT / "mining" / "results"
MINING_REPOSITORIES = ROOT / "mining" / "repositories"
VALIDATION_ROOT = ROOT / "candidate_validation"
REPOSITORIES_CSV = ROOT / "repositories.csv"
COLLECT_SCRIPT = ROOT / "mining" / "collect_smell_candidates.py"
VALIDATE_SCRIPT = ROOT / "validate_candidates.py"
LOG_ROOT = ROOT / "logs" / "batch_validation"

SMELLS = ("GC", "HM", "IM", "UD")

DEFAULT_EXCLUDED = {
    "imagej2",
    "javaparser",
    "jitsi",
    "opentripplanner",
    "symphony",
}


def clean(value: str | None) -> str:
    return value.strip() if value else ""


def count_csv_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        return sum(1 for _ in csv.DictReader(handle))


def count_removal_candidates(repo_dir: Path) -> dict[str, int]:
    counts = {smell: 0 for smell in SMELLS}
    candidates_dir = repo_dir / "candidates"

    for smell in SMELLS:
        path = candidates_dir / f"{smell}_candidates.csv"
        if not path.is_file():
            continue

        with path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                classification = clean(row.get("Classification"))
                if classification == "smell_removed_candidate":
                    counts[smell] += 1

    return counts


def discover_workloads() -> dict[str, dict[str, int]]:
    if not MINING_RESULTS.is_dir():
        raise RuntimeError(
            f"Missing mining results directory: {MINING_RESULTS}"
        )

    workloads = {}
    for repo_dir in sorted(MINING_RESULTS.iterdir()):
        if not repo_dir.is_dir():
            continue

        counts = count_removal_candidates(repo_dir)
        if sum(counts.values()) == 0:
            continue

        workloads[repo_dir.name] = counts

    return workloads


def validation_is_complete(
    repository: str,
    expected_candidates: int,
) -> bool:
    repo_root = VALIDATION_ROOT / repository
    results = repo_root / "results.csv"
    marker = repo_root / ".batch_validation_complete"

    if not marker.is_file():
        return False

    if not results.is_file():
        return False

    return count_csv_rows(results) == expected_candidates


def build_collect_command(repository: str) -> list[str]:
    output = VALIDATION_ROOT / repository / "candidates.csv"

    return [
        sys.executable,
        str(COLLECT_SCRIPT),
        "--results-root",
        str(MINING_RESULTS),
        "--repositories",
        repository,
        "--smells",
        *SMELLS,
        "--output",
        str(output),
    ]


def build_validation_command(
    repository: str,
    *,
    resume: bool,
) -> list[str]:
    repo_root = VALIDATION_ROOT / repository

    command = [
        sys.executable,
        str(VALIDATE_SCRIPT),
        "--candidates",
        str(repo_root / "candidates.csv"),
        "--repositories-file",
        str(REPOSITORIES_CSV),
        "--validation-root",
        str(repo_root),
        "--repositories-root",
        str(MINING_REPOSITORIES),
        "--mining-results-root",
        str(MINING_RESULTS),
        "--results",
        str(repo_root / "results.csv"),
        "--commits",
        str(repo_root / "commits.csv"),
    ]

    if resume:
        command.append("--resume")

    return command


def run_command(command: list[str], log) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: "
            + " ".join(command)
        )


def validate_repository(
    repository: str,
    candidate_count: int,
    *,
    resume: bool,
) -> tuple[str, bool, str]:
    repo_validation_root = VALIDATION_ROOT / repository
    repo_validation_root.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)

    completion_marker = (
        repo_validation_root
        / ".batch_validation_complete"
    )

    if completion_marker.exists():
        completion_marker.unlink()

    log_file = LOG_ROOT / f"{repository}.log"

    with log_file.open("w", encoding="utf-8") as log:
        try:
            log.write(f"Repository: {repository}\n")
            log.write(f"Expected candidates: {candidate_count}\n")
            log.write(f"Resume: {resume}\n\n")
            log.flush()

            collect_command = build_collect_command(repository)
            log.write("Collect command:\n" + " ".join(collect_command) + "\n\n")
            log.flush()
            run_command(collect_command, log)

            collected = repo_validation_root / "candidates.csv"
            collected_count = count_csv_rows(collected)
            log.write(f"\nCollected candidates: {collected_count}\n")
            log.flush()

            if collected_count != candidate_count:
                raise RuntimeError(
                    f"Candidate count mismatch for {repository}: "
                    f"expected {candidate_count}, collected {collected_count}"
                )

            validation_command = build_validation_command(
                repository,
                resume=resume,
            )
            log.write(
                "\nValidation command:\n"
                + " ".join(validation_command)
                + "\n\n"
            )
            log.flush()
            run_command(validation_command, log)

            results = repo_validation_root / "results.csv"
            result_count = count_csv_rows(results)
            if result_count != candidate_count:
                raise RuntimeError(
                    f"Validation finished with {result_count} result rows; "
                    f"expected {candidate_count}"
                )

            completion_marker.touch()

            return repository, True, str(log_file)

        except Exception as exc:
            log.write(f"\nERROR: {exc}\n")
            log.flush()
            return repository, False, str(log_file)


def format_counts(counts: dict[str, int]) -> str:
    return (
        f"GC={counts['GC']} "
        f"HM={counts['HM']} "
        f"IM={counts['IM']} "
        f"UD={counts['UD']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate RAVen repositories in parallel using historical "
            "Designite mining results."
        )
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Maximum repositories validated in parallel. Default: 4.",
    )
    parser.add_argument(
        "--include",
        nargs="+",
        help="Validate only these repositories.",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Additional repositories to exclude.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume partial results produced by this validation "
            "implementation."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show repositories without executing validation.",
    )

    args = parser.parse_args()

    if args.workers < 1:
        raise RuntimeError("--workers must be at least 1")

    workloads = discover_workloads()
    excluded = DEFAULT_EXCLUDED | set(args.exclude)
    selected = []

    for repository, counts in workloads.items():
        if repository in excluded:
            continue

        if args.include and repository not in args.include:
            continue

        total = sum(counts.values())

        if validation_is_complete(repository, total):
            print(f"SKIP complete: {repository} ({total})")
            continue

        selected.append((repository, total, counts))

    selected.sort(key=lambda item: (item[1], item[0].casefold()))

    print()
    print("=" * 78)
    print("RAVen batch candidate validation")
    print("=" * 78)
    print(f"Workers:      {args.workers}")
    print(f"Resume:       {args.resume}")
    print(f"Repositories: {len(selected)}")
    print(f"Candidates:   {sum(item[1] for item in selected)}")
    print("=" * 78)

    for repository, total, counts in selected:
        print(
            f"{repository:30} {total:6}  {format_counts(counts)}"
        )

    if args.dry_run:
        print()
        print("Dry run completed.")
        return 0

    if not selected:
        print()
        print("Nothing to validate.")
        return 0

    failures = []

    print()
    print(f"Validation started. Logs: {LOG_ROOT}")
    print()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(
                validate_repository,
                repository,
                total,
                resume=args.resume,
            ): (repository, total)
            for repository, total, _ in selected
        }

        for future in as_completed(future_map):
            repository, total = future_map[future]

            try:
                _, success, log_file = future.result()
            except Exception as exc:
                success = False
                log_file = str(LOG_ROOT / f"{repository}.log")
                print(f"FAILED  {repository} ({total}): {exc}")

            if success:
                print(f"DONE    {repository} ({total}) | {log_file}")
            else:
                failures.append(repository)
                print(f"FAILED  {repository} ({total}) | {log_file}")

    print()
    print("=" * 78)
    print("BATCH FINISHED")
    print("=" * 78)
    print(f"Successful: {len(selected) - len(failures)}")
    print(f"Failed:     {len(failures)}")

    if failures:
        print()
        print("Failed repositories:")
        for repository in failures:
            print(f"  - {repository}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
