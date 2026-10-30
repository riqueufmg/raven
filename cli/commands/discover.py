from __future__ import annotations

import sys
from pathlib import Path

from cli.config import load_config
from cli.jobs import (
    JobError,
    find_active_job,
    start_job,
)
from cli.repository import (
    prepare_repository,
)


class DiscoveryError(Exception):
    pass


def run_discovery(
    config_path: str | Path,
    restart: bool = False,
) -> dict:
    config_path = (
        Path(config_path)
        .expanduser()
        .resolve()
    )

    config = load_config(
        config_path
    )

    repository = config[
        "repository"
    ]

    paths = config[
        "paths"
    ]

    repo_path = prepare_repository(
        url=repository["url"],
        branch=repository["branch"],
        repositories_root=(
            paths["repositories"]
        ),
    )

    repo_name = (
        repo_path.name
    )

    active = find_active_job(
        job_type="discovery",
        repository=repo_name,
    )

    if active:
        raise DiscoveryError(
            "A discovery job is already active "
            f"for repository '{repo_name}'. "
            f"Job: {active['id']}"
        )

    command = [
        sys.executable,
        "-m",
        "cli.discovery_runner",
        "--config",
        str(config_path),
    ]

    if restart:
        command.append(
            "--restart"
        )

    try:
        job = start_job(
            job_type="discovery",
            repository=repo_name,
            command=command,
        )

    except JobError as exc:
        raise DiscoveryError(
            str(exc)
        ) from exc

    return job