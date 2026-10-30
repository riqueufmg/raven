from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

from cli.config import load_config
from cli.jobs import (
    JobError,
    find_active_job,
    list_jobs,
    start_job,
)
from cli.repository import prepare_repository


class ReproductionError(Exception):
    pass


def clean(
    value: str | None,
) -> str:
    return (
        value.strip()
        if value
        else ""
    )


def load_valid_candidates(
    results_csv: Path,
) -> list[dict[str, str]]:
    if not results_csv.is_file():
        raise ReproductionError(
            "Validated candidate results were not found: "
            f"{results_csv}\n"
            "Run 'raven discover' or 'raven validate' first."
        )

    with results_csv.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle
        )

        if not reader.fieldnames:
            raise ReproductionError(
                f"Empty validation results: {results_csv}"
            )

        required = {
            "Repository",
            "SmellAlias",
            "Entity",
            "CommitWithSmell",
            "Valid",
        }

        missing = (
            required
            .difference(
                reader.fieldnames
            )
        )

        if missing:
            raise ReproductionError(
                f"{results_csv} is missing columns: "
                f"{sorted(missing)}"
            )

        rows = []

        for row in reader:
            normalized = {
                key: clean(value)
                for key, value
                in row.items()
            }

            if (
                normalized.get(
                    "Valid"
                )
                != "true"
            ):
                continue

            rows.append(
                normalized
            )

    return rows


def group_candidates_by_commit(
    rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[
        str,
        list[dict[str, str]],
    ] = {}

    for row in rows:
        commit = row[
            "CommitWithSmell"
        ]

        grouped.setdefault(
            commit,
            [],
        ).append(
            row
        )

    return dict(
        sorted(
            grouped.items(),
            key=lambda item: item[0],
        )
    )


def environment_directory(
    *,
    benchmark_root: Path,
    repository: str,
    commit: str,
) -> Path:
    return (
        benchmark_root
        / "repositories"
        / repository
        / "commits"
        / commit[:12]
    )


def reproduction_state(
    *,
    benchmark_root: Path,
    repository: str,
    commit: str,
) -> str:
    active_jobs = list_jobs()

    for job in active_jobs:
        if (
            job.get("type")
            == "reproduction"
            and job.get("repository")
            == repository
            and job.get("target")
            == commit
            and job.get("status")
            in {
                "pending",
                "running",
            }
        ):
            return "Running"

    environment = (
        environment_directory(
            benchmark_root=benchmark_root,
            repository=repository,
            commit=commit,
        )
    )

    manifest = (
        environment
        / "manifest.txt"
    )

    if manifest.is_file():
        content = (
            manifest.read_text(
                encoding="utf-8",
                errors="replace",
            )
            .casefold()
        )

        if (
            "offline reproduction result: pass"
            in content
        ):
            return "Reproduced"

        return "Existing"

    if (
        environment.is_dir()
        and any(
            environment.iterdir()
        )
    ):
        return "Existing"

    return "Not reproduced"


def resolve_commit(
    requested: str,
    available: list[str],
) -> str:
    requested = (
        requested
        .strip()
        .lower()
    )

    matches = [
        commit
        for commit in available
        if (
            commit.lower()
            == requested
            or commit.lower().startswith(
                requested
            )
        )
    ]

    if not matches:
        raise ReproductionError(
            "The requested commit is not one of the "
            "validated reproduction targets: "
            f"{requested}"
        )

    if len(matches) > 1:
        raise ReproductionError(
            "The commit prefix is ambiguous: "
            f"{requested}"
        )

    return matches[0]


def print_candidates(
    *,
    grouped: dict[
        str,
        list[dict[str, str]],
    ],
    benchmark_root: Path,
    repository: str,
) -> list[str]:
    commits = list(
        grouped
    )

    print()
    print(
        "Validated historical commits"
    )
    print("=" * 78)
    print()

    for index, commit in enumerate(
        commits,
        start=1,
    ):
        rows = grouped[
            commit
        ]

        state = (
            reproduction_state(
                benchmark_root=benchmark_root,
                repository=repository,
                commit=commit,
            )
        )

        print(
            f"[{index}] "
            f"{commit[:12]}  "
            f"{state}"
        )

        for row in rows:
            print(
                "    "
                f"{row['SmellAlias']} | "
                f"{row['Entity']}"
            )

        print()

    return commits


def select_commit_interactively(
    *,
    grouped: dict[
        str,
        list[dict[str, str]],
    ],
    benchmark_root: Path,
    repository: str,
) -> str:
    commits = print_candidates(
        grouped=grouped,
        benchmark_root=benchmark_root,
        repository=repository,
    )

    if not commits:
        raise ReproductionError(
            "No validated commits are available "
            "for reproduction."
        )

    try:
        value = input(
            "Select a commit to reproduce "
            "[number or commit prefix]: "
        ).strip()

    except EOFError as exc:
        raise ReproductionError(
            "Interactive selection is unavailable. "
            "Use --commit <SHA>."
        ) from exc

    if not value:
        raise ReproductionError(
            "No reproduction target was selected."
        )

    if value.isdigit():
        index = int(value)

        if (
            index < 1
            or index > len(commits)
        ):
            raise ReproductionError(
                f"Invalid selection: {value}"
            )

        return commits[
            index - 1
        ]

    return resolve_commit(
        value,
        commits,
    )


def run_reproduction(
    config_path: str | Path,
    commit: str | None = None,
) -> dict[str, Any]:
    config_path = (
        Path(config_path)
        .expanduser()
        .resolve()
    )

    config = load_config(
        config_path
    )

    repository_config = (
        config["repository"]
    )

    paths = config[
        "paths"
    ]

    repo_path = prepare_repository(
        url=repository_config["url"],
        branch=repository_config["branch"],
        repositories_root=(
            paths["repositories"]
        ),
    )

    repository = (
        repo_path.name
    )

    validation_root = (
        Path(
            paths[
                "candidate_validation"
            ]
        )
        / repository
    )

    results_csv = (
        validation_root
        / "results.csv"
    )

    rows = load_valid_candidates(
        results_csv
    )

    grouped = (
        group_candidates_by_commit(
            rows
        )
    )

    if not grouped:
        raise ReproductionError(
            "No valid historical commits were found "
            f"in {results_csv}."
        )

    available_commits = list(
        grouped
    )

    benchmark_root = Path(
        paths["benchmark"]
    )

    if commit:
        selected_commit = (
            resolve_commit(
                commit,
                available_commits,
            )
        )
    else:
        selected_commit = (
            select_commit_interactively(
                grouped=grouped,
                benchmark_root=benchmark_root,
                repository=repository,
            )
        )

    state = reproduction_state(
        benchmark_root=benchmark_root,
        repository=repository,
        commit=selected_commit,
    )

    if state == "Reproduced":
        raise ReproductionError(
            "The selected commit already has a successful "
            "offline reproduction.\n"
            f"Commit: {selected_commit}"
        )

    if state == "Existing":
        environment = (
            environment_directory(
                benchmark_root=benchmark_root,
                repository=repository,
                commit=selected_commit,
            )
        )

        raise ReproductionError(
            "A non-empty reproduction environment already "
            "exists for this commit.\n"
            f"Commit: {selected_commit}\n"
            f"Path:   {environment}\n"
            "RAVen will not overwrite it automatically."
        )

    active = find_active_job(
        job_type="reproduction",
        repository=repository,
    )

    if active:
        raise ReproductionError(
            "A reproduction job is already active for "
            f"repository '{repository}'.\n"
            f"Job:    {active['id']}\n"
            f"Target: {active.get('target') or '-'}\n\n"
            "The current reproduction pipeline uses a shared "
            "repository checkout, so parallel reproduction jobs "
            "for the same repository are not safe."
        )

    command = [
        sys.executable,
        "repro.py",
        "--repo",
        repository_config["url"],
        "--commit",
        selected_commit,
    ]

    try:
        job = start_job(
            job_type="reproduction",
            repository=repository,
            target=selected_commit,
            command=command,
        )

    except JobError as exc:
        raise ReproductionError(
            str(exc)
        ) from exc

    return job