#!/usr/bin/env python3
"""
Run DesigniteJava over a commit range and identify candidate smell removals.

Example:
    python -m mining.search_candidates \
        --repo mining/repositories/jsoup \
        --date 07-31-2023 \
        --smell "Insufficient Modularization" \
        --designite-jar tools/DesigniteJava.jar \
        --output mining/results/jsoup \
        --branch refs/heads/master \
        --regular \
        --overwrite

DesigniteJava output expected:

    <output>/
      <commit_hash>/
        DesignSmells.csv
        ArchitectureSmells.csv
        ...

The script generates:

    <output>/candidates.csv
    <output>/analysis_manifest.json

A candidate transition is an entity that has the selected smell in one commit
and does not have it in the immediately following analyzed commit.

The classification is intentionally conservative:
- smell_removed_candidate: the entity still exists after the transition.
- entity_missing_after: the entity is not found after the transition; it may
  have been deleted, moved, or renamed.
- entity_existence_unknown: the entity could not be checked reliably.

This script does not prove that a refactoring removed the smell. That requires
a later validation step, for example with RefactoringMiner.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


SMELL_CONFIG = {
    "Insufficient Modularization": {
        "csv": "DesignSmells.csv",
        "granularity": "class",
    },
    "Hub-like Modularization": {
        "csv": "DesignSmells.csv",
        "granularity": "class",
    },
    "God Component": {
        "csv": "ArchitectureSmells.csv",
        "granularity": "package",
    },
    "Unstable Dependency": {
        "csv": "ArchitectureSmells.csv",
        "granularity": "package",
    },
}

SMELL_ALIASES = {
    "IM": "Insufficient Modularization",
    "HM": "Hub-like Modularization",
    "GC": "God Component",
    "UD": "Unstable Dependency",
}


@dataclass(frozen=True)
class AnalysisConfig:
    repository: str
    branch: str
    requested_start_date: str
    first_commit: str
    last_commit: str
    smell: str
    designite_mode: str
    analyzed_commit_count: int
    candidate_count: int


@dataclass(frozen=True)
class SmellOccurrence:
    entity: str
    package: str
    class_name: str
    file: str


@dataclass(frozen=True)
class Candidate:
    smell: str
    entity: str
    granularity: str
    commit_with_smell: str
    commit_without_smell: str
    entity_exists_after: str
    classification: str
    package: str
    class_name: str
    file_before: str


def run(
    command: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
    )

    if check and result.returncode != 0:
        rendered = " ".join(str(part) for part in command)
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}:\n"
            f"{rendered}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    return result


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(
        ["git", "-C", str(repo), *args],
        check=check,
    ).stdout.strip()


def parse_mm_dd_yyyy(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%m-%d-%Y")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Expected MM-DD-YYYY, "
            "for example 07-31-2023."
        ) from exc


def normalize_smell(value: str) -> str:
    cleaned = value.strip()
    upper = cleaned.upper()

    if upper in SMELL_ALIASES:
        return SMELL_ALIASES[upper]

    for smell in SMELL_CONFIG:
        if cleaned.casefold() == smell.casefold():
            return smell

    supported = ", ".join(SMELL_CONFIG)
    raise argparse.ArgumentTypeError(
        f"Unsupported smell {value!r}. Supported values: {supported}; "
        "aliases: IM, HM, GC, UD."
    )


def validate_repository(repo: Path) -> None:
    if not repo.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo}")

    if not repo.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {repo}")

    inside_work_tree = git(repo, "rev-parse", "--is-inside-work-tree")
    if inside_work_tree != "true":
        raise ValueError(f"Path is not a Git working tree: {repo}")


def validate_inputs(
    repo: Path,
    designite_jar: Path,
    output: Path,
    skip_analysis: bool,
) -> None:
    validate_repository(repo)

    if not skip_analysis and not designite_jar.is_file():
        raise FileNotFoundError(
            f"DesigniteJava JAR does not exist: {designite_jar}"
        )

    if output == repo or repo in output.parents:
        raise ValueError(
            "The output directory must not be the repository itself or a "
            "directory inside the repository."
        )


def resolve_branch(repo: Path, branch: str | None) -> str:
    if branch:
        git(repo, "rev-parse", "--verify", f"{branch}^{{commit}}")
        return branch

    current_branch = git(repo, "branch", "--show-current")
    if not current_branch:
        raise ValueError(
            "The repository is in detached HEAD state. "
            "Supply --branch explicitly."
        )

    return current_branch


def find_first_commit(
    repo: Path,
    branch: str,
    start_date: datetime,
) -> str:
    iso_date = start_date.strftime("%Y-%m-%d 00:00:00")

    output = git(
        repo,
        "rev-list",
        "--reverse",
        "--topo-order",
        f"--since={iso_date}",
        branch,
    )

    commits = [line.strip() for line in output.splitlines() if line.strip()]

    if not commits:
        raise ValueError(
            f"No commits were found on branch {branch!r} on or after "
            f"{start_date.strftime('%m-%d-%Y')}."
        )

    return commits[0]


def find_last_commit(repo: Path, branch: str) -> str:
    return git(repo, "rev-parse", f"{branch}^{{commit}}")


def commits_in_range(
    repo: Path,
    first_commit: str,
    last_commit: str,
) -> list[str]:
    if first_commit == last_commit:
        return [first_commit]

    output = git(
        repo,
        "rev-list",
        "--reverse",
        "--topo-order",
        "--ancestry-path",
        f"{first_commit}..{last_commit}",
    )

    commits = [first_commit]
    commits.extend(
        line.strip()
        for line in output.splitlines()
        if line.strip()
    )

    return deduplicate_preserving_order(commits)


def deduplicate_preserving_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)

    return result


def prepare_output_directory(
    output: Path,
    overwrite: bool,
) -> None:
    if output.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists: {output}\n"
                "Use --overwrite to remove it before analysis, or use "
                "--skip-analysis to parse the existing results."
            )

        shutil.rmtree(output)

    output.mkdir(parents=True, exist_ok=False)


def run_designite(
    *,
    repo: Path,
    output: Path,
    designite_jar: Path,
    branch: str,
    first_commit: str,
    last_commit: str,
    java_command: str,
    optimized: bool,
) -> None:
    mode = "-aco" if optimized else "-ac"

    command = [
        java_command,
        "-jar",
        str(designite_jar),
        "-i",
        str(repo),
        "-o",
        str(output),
        mode,
        branch,
        "-fr",
        first_commit,
        "-to",
        last_commit,
    ]

    print("Executing DesigniteJava:", file=sys.stderr)
    print(" ".join(command), file=sys.stderr)

    result = run(command, check=False)

    if result.stdout:
        print(result.stdout, file=sys.stderr)

    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"DesigniteJava failed with exit code {result.returncode}."
        )


def clean_csv_value(value: str | None) -> str:
    return (value or "").strip()


def join_fqn(package: str, class_name: str) -> str:
    package = package.strip(". ")
    class_name = class_name.strip(". ")

    if package and class_name:
        return f"{package}.{class_name}"
    return class_name or package


def read_smell_occurrences(
    commit_dir: Path,
    smell: str,
) -> dict[str, SmellOccurrence]:
    config = SMELL_CONFIG[smell]
    csv_path = commit_dir / config["csv"]

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Expected DesigniteJava result not found: {csv_path}"
        )

    occurrences: dict[str, SmellOccurrence] = {}

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            return occurrences

        required = {"Package", "Smell"}
        missing = required.difference(reader.fieldnames)
        if missing:
            raise RuntimeError(
                f"Missing columns in {csv_path}: {sorted(missing)}. "
                f"Found: {reader.fieldnames}"
            )

        if config["granularity"] == "class" and "Class" not in reader.fieldnames:
            raise RuntimeError(
                f"Column 'Class' is required in {csv_path}. "
                f"Found: {reader.fieldnames}"
            )

        for row in reader:
            row_smell = clean_csv_value(row.get("Smell"))
            if row_smell.casefold() != smell.casefold():
                continue

            package = clean_csv_value(row.get("Package"))
            class_name = clean_csv_value(row.get("Class"))
            file_path = clean_csv_value(row.get("File"))

            if config["granularity"] == "class":
                entity = join_fqn(package, class_name)
            else:
                entity = package

            if not entity:
                continue

            # Deduplicate repeated rows for the same entity and smell.
            occurrences[entity] = SmellOccurrence(
                entity=entity,
                package=package,
                class_name=class_name,
                file=file_path,
            )

    return occurrences


def normalize_repo_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def git_path_exists(
    repo: Path,
    commit: str,
    path: str,
) -> bool:
    normalized = normalize_repo_path(path)
    if not normalized:
        return False

    result = run(
        [
            "git",
            "-C",
            str(repo),
            "cat-file",
            "-e",
            f"{commit}:{normalized}",
        ],
        check=False,
    )
    return result.returncode == 0


def find_class_paths_in_commit(
    repo: Path,
    commit: str,
    occurrence: SmellOccurrence,
) -> list[str]:
    candidates: list[str] = []

    if occurrence.file:
        candidates.append(normalize_repo_path(occurrence.file))

    if occurrence.package and occurrence.class_name:
        suffix = (
            occurrence.package.replace(".", "/")
            + "/"
            + occurrence.class_name
            + ".java"
        )

        output = git(
            repo,
            "ls-tree",
            "-r",
            "--name-only",
            commit,
        )
        for path in output.splitlines():
            normalized = normalize_repo_path(path)
            if normalized.endswith(suffix):
                candidates.append(normalized)

    return deduplicate_preserving_order(
        candidate for candidate in candidates if candidate
    )


def class_exists_after(
    repo: Path,
    commit: str,
    occurrence: SmellOccurrence,
) -> bool | None:
    candidates = find_class_paths_in_commit(repo, commit, occurrence)

    if not candidates:
        return None

    return any(
        git_path_exists(repo, commit, candidate)
        for candidate in candidates
    )


def package_exists_after(
    repo: Path,
    commit: str,
    package: str,
) -> bool | None:
    package_path = package.replace(".", "/").strip("/")

    if not package_path:
        return None

    output = git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        commit,
    )

    expected_fragment = f"/{package_path}/"

    for raw_path in output.splitlines():
        path = "/" + normalize_repo_path(raw_path)
        if not path.endswith(".java"):
            continue

        if expected_fragment in path:
            return True

        # Handles source trees where the package is at the beginning.
        if path.startswith(f"/{package_path}/"):
            return True

    return False


def entity_exists_after(
    repo: Path,
    commit: str,
    occurrence: SmellOccurrence,
    granularity: str,
) -> bool | None:
    if granularity == "class":
        return class_exists_after(repo, commit, occurrence)

    if granularity == "package":
        return package_exists_after(repo, commit, occurrence.package)

    return None


def classify_existence(exists: bool | None) -> tuple[str, str]:
    if exists is True:
        return "true", "smell_removed_candidate"

    if exists is False:
        return "false", "entity_missing_after"

    return "unknown", "entity_existence_unknown"


def find_candidates(
    repo: Path,
    output: Path,
    commits: Sequence[str],
    smell: str,
) -> tuple[list[Candidate], list[str]]:
    granularity = SMELL_CONFIG[smell]["granularity"]
    occurrences_by_commit: dict[str, dict[str, SmellOccurrence]] = {}
    missing_commit_results: list[str] = []

    for commit in commits:
        commit_dir = output / commit

        if not commit_dir.is_dir():
            missing_commit_results.append(commit)
            continue

        occurrences_by_commit[commit] = read_smell_occurrences(
            commit_dir=commit_dir,
            smell=smell,
        )

    if missing_commit_results:
        missing_preview = ", ".join(missing_commit_results[:5])
        suffix = "..." if len(missing_commit_results) > 5 else ""
        raise RuntimeError(
            f"DesigniteJava results are missing for "
            f"{len(missing_commit_results)} commit(s): "
            f"{missing_preview}{suffix}"
        )

    candidates: list[Candidate] = []

    for commit_with, commit_without in zip(commits, commits[1:]):
        before = occurrences_by_commit[commit_with]
        after = occurrences_by_commit[commit_without]

        removed_entities = sorted(set(before).difference(after))

        for entity in removed_entities:
            occurrence = before[entity]
            exists = entity_exists_after(
                repo=repo,
                commit=commit_without,
                occurrence=occurrence,
                granularity=granularity,
            )
            exists_text, classification = classify_existence(exists)

            candidates.append(
                Candidate(
                    smell=smell,
                    entity=entity,
                    granularity=granularity,
                    commit_with_smell=commit_with,
                    commit_without_smell=commit_without,
                    entity_exists_after=exists_text,
                    classification=classification,
                    package=occurrence.package,
                    class_name=occurrence.class_name,
                    file_before=occurrence.file,
                )
            )

    return candidates, missing_commit_results


def write_candidates_csv(
    output: Path,
    candidates: Sequence[Candidate],
) -> Path:
    path = output / "candidates.csv"

    fieldnames = [
        "Smell",
        "Entity",
        "Granularity",
        "CommitWithSmell",
        "CommitWithoutSmell",
        "EntityExistsAfter",
        "Classification",
        "Package",
        "Class",
        "FileBefore",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for candidate in candidates:
            writer.writerow(
                {
                    "Smell": candidate.smell,
                    "Entity": candidate.entity,
                    "Granularity": candidate.granularity,
                    "CommitWithSmell": candidate.commit_with_smell,
                    "CommitWithoutSmell": candidate.commit_without_smell,
                    "EntityExistsAfter": candidate.entity_exists_after,
                    "Classification": candidate.classification,
                    "Package": candidate.package,
                    "Class": candidate.class_name,
                    "FileBefore": candidate.file_before,
                }
            )

    return path


def write_manifest(
    output: Path,
    config: AnalysisConfig,
) -> Path:
    manifest_path = output / "analysis_manifest.json"
    manifest_path.write_text(
        json.dumps(
            asdict(config),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run DesigniteJava over a date-based commit range and identify "
            "candidate transitions where a selected smell disappears."
        )
    )

    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        help="Path to the Git repository.",
    )
    parser.add_argument(
        "--date",
        required=True,
        type=parse_mm_dd_yyyy,
        metavar="MM-DD-YYYY",
        help="Inclusive initial date, based on Git committer date.",
    )
    parser.add_argument(
        "--smell",
        required=True,
        type=normalize_smell,
        help=(
            "Smell name or alias: Insufficient Modularization (IM), "
            "Hub-like Modularization (HM), God Component (GC), "
            "or Unstable Dependency (UD)."
        ),
    )
    parser.add_argument(
        "--designite-jar",
        required=True,
        type=Path,
        help="Path to DesigniteJava.jar.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directory where DesigniteJava writes results.",
    )
    parser.add_argument(
        "--branch",
        help="Branch or revision to analyze. Defaults to the current branch.",
    )
    parser.add_argument(
        "--java",
        default="java",
        help="Java executable. Default: java.",
    )
    parser.add_argument(
        "--regular",
        action="store_true",
        help="Use regular -ac mode instead of optimized -aco mode.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete the output directory first if it already exists.",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help=(
            "Do not execute DesigniteJava. Parse the existing results in "
            "--output instead."
        ),
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    repo = args.repo.expanduser().resolve()
    designite_jar = args.designite_jar.expanduser().resolve()
    output = args.output.expanduser().resolve()

    validate_inputs(
        repo=repo,
        designite_jar=designite_jar,
        output=output,
        skip_analysis=args.skip_analysis,
    )

    branch = resolve_branch(repo, args.branch)
    first_commit = find_first_commit(
        repo=repo,
        branch=branch,
        start_date=args.date,
    )
    last_commit = find_last_commit(
        repo=repo,
        branch=branch,
    )
    commits = commits_in_range(
        repo=repo,
        first_commit=first_commit,
        last_commit=last_commit,
    )

    mode = "-ac" if args.regular else "-aco"

    print(f"Repository:    {repo}", file=sys.stderr)
    print(f"Branch:        {branch}", file=sys.stderr)
    print(
        f"Initial date:  {args.date.strftime('%m-%d-%Y')}",
        file=sys.stderr,
    )
    print(f"First commit:  {first_commit}", file=sys.stderr)
    print(f"Last commit:   {last_commit}", file=sys.stderr)
    print(f"Commit count:  {len(commits)}", file=sys.stderr)
    print(f"Smell:         {args.smell}", file=sys.stderr)
    print(f"Mode:          {mode}", file=sys.stderr)

    if args.skip_analysis:
        if not output.is_dir():
            raise FileNotFoundError(
                f"Output directory does not exist: {output}"
            )
    else:
        prepare_output_directory(
            output=output,
            overwrite=args.overwrite,
        )

        run_designite(
            repo=repo,
            output=output,
            designite_jar=designite_jar,
            branch=branch,
            first_commit=first_commit,
            last_commit=last_commit,
            java_command=args.java,
            optimized=not args.regular,
        )

    candidates, _ = find_candidates(
        repo=repo,
        output=output,
        commits=commits,
        smell=args.smell,
    )

    candidates_path = write_candidates_csv(
        output=output,
        candidates=candidates,
    )

    config = AnalysisConfig(
        repository=str(repo),
        branch=branch,
        requested_start_date=args.date.strftime("%m-%d-%Y"),
        first_commit=first_commit,
        last_commit=last_commit,
        smell=args.smell,
        designite_mode=mode,
        analyzed_commit_count=len(commits),
        candidate_count=len(candidates),
    )

    manifest_path = write_manifest(
        output=output,
        config=config,
    )

    print(f"Candidate transitions: {len(candidates)}")
    print(f"Candidates CSV:        {candidates_path}")
    print(f"Manifest:              {manifest_path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValueError,
        FileNotFoundError,
        FileExistsError,
        NotADirectoryError,
        RuntimeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
