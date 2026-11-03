from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import yaml

from cli.commands.reproduce import (
    ReproductionError,
    group_candidates_by_commit,
    load_valid_candidates,
    reproduction_state,
    run_reproduction,
)
from cli.config import load_config
from cli.repository import repository_name_from_url


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


class UICandidatesError(Exception):
    pass


def _resolve_path(
    value: str | Path,
) -> Path:
    path = Path(value)

    if path.is_absolute():
        return path

    return (
        PROJECT_ROOT
        / path
    ).resolve()


def _load_raw_yaml(
    path: Path,
) -> dict[str, Any]:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = yaml.safe_load(
                handle
            )

    except Exception as exc:
        raise UICandidatesError(
            f"Could not read configuration "
            f"{path}: {exc}"
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise UICandidatesError(
            f"Invalid configuration file: {path}"
        )

    return data


def _git_origin(
    repository_path: Path,
) -> str | None:
    if not (
        repository_path
        / ".git"
    ).exists():
        return None

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_path),
                "remote",
                "get-url",
                "origin",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    except (
        subprocess.CalledProcessError,
        OSError,
    ):
        return None

    value = result.stdout.strip()

    return value or None


def _git_branch(
    repository_path: Path,
) -> str | None:
    if not (
        repository_path
        / ".git"
    ).exists():
        return None

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_path),
                "branch",
                "--show-current",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    except (
        subprocess.CalledProcessError,
        OSError,
    ):
        return None

    value = result.stdout.strip()

    return value or None


def _load_mining_manifest(
    mining_results_root: Path,
    repository: str,
) -> dict[str, Any] | None:
    manifest_path = (
        mining_results_root
        / repository
        / "mining_manifest.json"
    )

    if not manifest_path.is_file():
        return None

    try:
        with manifest_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(
                handle
            )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(
        data,
        dict,
    ):
        return None

    return data


def _resolve_repository_identity(
    *,
    config_path: Path,
    repository: str,
) -> tuple[str, str]:
    config = load_config(
        config_path
    )

    paths = config[
        "paths"
    ]

    mining_results_root = _resolve_path(
        paths[
            "mining_results"
        ]
    )

    mining_repositories_root = _resolve_path(
        paths[
            "repositories"
        ]
    )

    benchmark_root = _resolve_path(
        paths[
            "benchmark"
        ]
    )

    manifest = _load_mining_manifest(
        mining_results_root,
        repository,
    )

    if manifest:
        repository_url = (
            manifest.get(
                "repository_url"
            )
        )

        branch = (
            manifest.get(
                "branch"
            )
        )

        if repository_url:
            return (
                str(repository_url),
                str(
                    branch
                    or "master"
                ),
            )

    mining_repository = (
        mining_repositories_root
        / repository
    )

    repository_url = _git_origin(
        mining_repository
    )

    branch = _git_branch(
        mining_repository
    )

    if repository_url:
        return (
            repository_url,
            branch or "master",
        )

    benchmark_repository = (
        benchmark_root
        / "repositories"
        / repository
        / "repository"
    )

    repository_url = _git_origin(
        benchmark_repository
    )

    branch = _git_branch(
        benchmark_repository
    )

    if repository_url:
        return (
            repository_url,
            branch or "master",
        )

    configured_repository = config.get(
        "repository",
        {},
    )

    configured_url = (
        configured_repository.get(
            "url"
        )
    )

    if configured_url:
        try:
            configured_name = (
                repository_name_from_url(
                    configured_url
                )
            )

        except Exception:
            configured_name = None

        if configured_name == repository:
            return (
                configured_url,
                configured_repository.get(
                    "branch",
                    "master",
                ),
            )

    raise UICandidatesError(
        "Could not determine the repository URL "
        f"for '{repository}'. "
        "Expected a mining manifest, a local Git "
        "repository with an origin remote, or a "
        "matching configured repository."
    )


def _create_reproduction_config(
    *,
    config_path: Path,
    repository: str,
) -> Path:
    raw_config = _load_raw_yaml(
        config_path
    )

    repository_url, branch = (
        _resolve_repository_identity(
            config_path=config_path,
            repository=repository,
        )
    )

    repository_config = (
        raw_config.get(
            "repository"
        )
    )

    if not isinstance(
        repository_config,
        dict,
    ):
        repository_config = {}

    repository_config[
        "url"
    ] = repository_url

    repository_config[
        "branch"
    ] = branch

    raw_config[
        "repository"
    ] = repository_config

    snapshot_root = (
        PROJECT_ROOT
        / "jobs"
        / "configs"
    )

    snapshot_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    snapshot_path = (
        snapshot_root
        / (
            "reproduction_"
            f"{repository}_"
            f"{uuid.uuid4().hex}.yml"
        )
    )

    try:
        with snapshot_path.open(
            "w",
            encoding="utf-8",
        ) as handle:
            yaml.safe_dump(
                raw_config,
                handle,
                sort_keys=False,
                allow_unicode=True,
            )

    except OSError as exc:
        raise UICandidatesError(
            "Could not create reproduction "
            f"configuration snapshot: {exc}"
        ) from exc

    return snapshot_path.resolve()


def list_candidate_repositories(
    config_path: str | Path,
) -> list[str]:
    try:
        config = load_config(
            config_path
        )

        validation_root = _resolve_path(
            config[
                "paths"
            ][
                "candidate_validation"
            ]
        )

    except Exception as exc:
        raise UICandidatesError(
            str(exc)
        ) from exc

    if not validation_root.exists():
        return []

    repositories = []

    for path in validation_root.iterdir():
        if not path.is_dir():
            continue

        results_csv = (
            path
            / "results.csv"
        )

        if results_csv.is_file():
            repositories.append(
                path.name
            )

    return sorted(
        repositories
    )


def _load_repository_targets(
    *,
    config_path: Path,
    repository: str,
    benchmark_root: Path,
    validation_root: Path,
) -> dict[str, Any]:
    results_csv = (
        validation_root
        / repository
        / "results.csv"
    )

    try:
        rows = load_valid_candidates(
            results_csv
        )

        grouped = (
            group_candidates_by_commit(
                rows
            )
        )

    except Exception as exc:
        raise UICandidatesError(
            f"Could not load candidates for "
            f"'{repository}': {exc}"
        ) from exc

    targets = []

    for commit, candidates in grouped.items():
        state = reproduction_state(
            benchmark_root=benchmark_root,
            repository=repository,
            commit=commit,
        )

        targets.append(
            {
                "commit":
                    commit,
                "short_commit":
                    commit[:12],
                "repository":
                    repository,
                "state":
                    state,
                "candidates":
                    candidates,
                "candidate_count":
                    len(
                        candidates
                    ),
                "smells":
                    sorted(
                        {
                            candidate[
                                "SmellAlias"
                            ]
                            for candidate
                            in candidates
                        }
                    ),
            }
        )

    targets.sort(
        key=lambda item: (
            item[
                "repository"
            ],
            item[
                "commit"
            ],
        )
    )

    return {
        "repository":
            repository,
        "results_csv":
            results_csv,
        "targets":
            targets,
        "valid_candidate_count":
            len(
                rows
            ),
        "reproduction_target_count":
            len(
                targets
            ),
    }


def load_candidate_targets(
    config_path: str | Path,
    repository: str | None = None,
) -> dict[str, Any]:
    try:
        resolved_config_path = (
            Path(
                config_path
            )
            .expanduser()
            .resolve()
        )

        config = load_config(
            resolved_config_path
        )

        paths = config[
            "paths"
        ]

        validation_root = _resolve_path(
            paths[
                "candidate_validation"
            ]
        )

        benchmark_root = _resolve_path(
            paths[
                "benchmark"
            ]
        )

        repositories = (
            list_candidate_repositories(
                resolved_config_path
            )
        )

    except UICandidatesError:
        raise

    except Exception as exc:
        raise UICandidatesError(
            str(exc)
        ) from exc

    if (
        repository is not None
        and repository
        not in repositories
    ):
        raise UICandidatesError(
            "Unknown candidate repository: "
            f"{repository}"
        )

    selected_repositories = (
        [repository]
        if repository
        else repositories
    )

    all_targets = []

    repository_summaries = {}

    valid_candidate_count = 0
    reproduction_target_count = 0

    for repository_name in (
        selected_repositories
    ):
        data = (
            _load_repository_targets(
                config_path=(
                    resolved_config_path
                ),
                repository=(
                    repository_name
                ),
                benchmark_root=(
                    benchmark_root
                ),
                validation_root=(
                    validation_root
                ),
            )
        )

        repository_summaries[
            repository_name
        ] = data

        all_targets.extend(
            data[
                "targets"
            ]
        )

        valid_candidate_count += (
            data[
                "valid_candidate_count"
            ]
        )

        reproduction_target_count += (
            data[
                "reproduction_target_count"
            ]
        )

    return {
        "repository":
            repository
            or "All repositories",
        "repositories":
            repositories,
        "selected_repositories":
            selected_repositories,
        "repository_count":
            len(
                selected_repositories
            ),
        "repository_summaries":
            repository_summaries,
        "targets":
            all_targets,
        "valid_candidate_count":
            valid_candidate_count,
        "reproduction_target_count":
            reproduction_target_count,
        "validation_root":
            validation_root,
    }


def start_reproduction(
    *,
    config_path: str | Path,
    repository: str,
    commit: str,
) -> dict[str, Any]:
    resolved_config_path = (
        Path(
            config_path
        )
        .expanduser()
        .resolve()
    )

    try:
        reproduction_config = (
            _create_reproduction_config(
                config_path=(
                    resolved_config_path
                ),
                repository=repository,
            )
        )

        return run_reproduction(
            config_path=(
                reproduction_config
            ),
            commit=commit,
        )

    except ReproductionError as exc:
        raise UICandidatesError(
            str(exc)
        ) from exc

    except UICandidatesError:
        raise

    except Exception as exc:
        raise UICandidatesError(
            str(exc)
        ) from exc