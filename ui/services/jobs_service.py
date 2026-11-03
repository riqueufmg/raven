from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.commands.status import job_phase
from cli.jobs import list_jobs


class UIJobsError(Exception):
    pass


def get_jobs() -> list[dict[str, Any]]:
    jobs = list_jobs()

    enriched = []

    for job in jobs:
        item = dict(job)

        item["phase"] = job_phase(
            job
        )

        target = (
            job.get("target")
            or ""
        )

        item["short_target"] = (
            target[:12]
            if target
            else "-"
        )

        enriched.append(
            item
        )

    enriched.sort(
        key=lambda item: (
            item.get(
                "created_at"
            )
            or ""
        ),
        reverse=True,
    )

    return enriched


def get_repository_jobs(
    repository: str,
) -> list[dict[str, Any]]:
    return [
        job
        for job in get_jobs()
        if (
            job.get(
                "repository"
            )
            == repository
        )
    ]


def get_latest_job(
    *,
    repository: str,
    job_type: str,
) -> dict[str, Any] | None:
    for job in get_jobs():
        if (
            job.get(
                "repository"
            )
            == repository
            and job.get(
                "type"
            )
            == job_type
        ):
            return job

    return None


def read_job_log(
    job: dict[str, Any],
    *,
    max_lines: int = 200,
) -> str:
    log_value = (
        job.get("log")
        or ""
    )

    if not log_value:
        return ""

    log_path = Path(
        log_value
    )

    if not log_path.is_absolute():
        cwd = (
            job.get("cwd")
            or Path.cwd()
        )

        log_path = (
            Path(cwd)
            / log_path
        )

    if not log_path.is_file():
        return ""

    try:
        lines = (
            log_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            .splitlines()
        )

    except OSError as exc:
        raise UIJobsError(
            f"Could not read job log: "
            f"{log_path}"
        ) from exc

    if max_lines > 0:
        lines = lines[
            -max_lines:
        ]

    return "\n".join(
        lines
    )


def status_category(
    job: dict[str, Any],
) -> str:
    phase = (
        job.get("phase")
        or ""
    ).casefold()

    if (
        "failed" in phase
        or phase == "failed"
    ):
        return "error"

    if (
        phase
        in {
            "reproduced",
            "analyzed",
            "succeeded",
        }
    ):
        return "success"

    if (
        phase
        in {
            "running codex",
            "offline validation",
            "analyzing",
            "preparing repository",
            "preparing environment",
            "running",
        }
    ):
        return "running"

    return "neutral"