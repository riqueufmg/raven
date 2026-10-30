from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.jobs import (
    DEFAULT_JOBS_ROOT,
    list_jobs,
)


STATUS_LABELS = {
    "pending": "Pending",
    "running": "Running",
    "succeeded": "Succeeded",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


def short_target(
    target: str | None,
) -> str:
    if not target:
        return "-"

    return target[:12]


def short_time(
    value: str | None,
) -> str:
    if not value:
        return "-"

    return value[:19].replace(
        "T",
        " ",
    )


def reproduction_environment(
    job: dict[str, Any],
) -> Path | None:
    repository = (
        job.get("repository")
        or ""
    )

    target = (
        job.get("target")
        or ""
    )

    cwd = (
        job.get("cwd")
        or ""
    )

    if (
        not repository
        or not target
        or not cwd
    ):
        return None

    return (
        Path(cwd)
        / "benchmark"
        / "repositories"
        / repository
        / "commits"
        / target[:12]
    )


def manifest_result(
    manifest: Path,
) -> str | None:
    if not manifest.is_file():
        return None

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
        return "pass"

    if (
        "offline reproduction result: fail"
        in content
    ):
        return "fail"

    return None


def reproduction_phase(
    job: dict[str, Any],
) -> str:
    status = (
        job.get("status")
        or ""
    )

    environment = (
        reproduction_environment(
            job
        )
    )

    if environment is None:
        return STATUS_LABELS.get(
            status,
            status or "-",
        )

    manifest = (
        environment
        / "manifest.txt"
    )

    validation_log = (
        environment
        / "validation.log"
    )

    codex_trace = (
        environment
        / "codex_trace.log"
    )

    result = manifest_result(
        manifest
    )

    if result == "pass":
        return "Reproduced"

    if result == "fail":
        return "Validation failed"

    if status == "failed":
        return "Failed"

    if status == "cancelled":
        return "Cancelled"

    if status == "succeeded":
        return "Succeeded"

    if status == "pending":
        return "Pending"

    if status != "running":
        return STATUS_LABELS.get(
            status,
            status or "-",
        )

    if validation_log.is_file():
        return "Offline validation"

    if codex_trace.is_file():
        return "Running Codex"

    if environment.exists():
        return "Preparing environment"

    return "Preparing repository"


def job_phase(
    job: dict[str, Any],
) -> str:
    if (
        job.get("type")
        == "reproduction"
    ):
        return reproduction_phase(
            job
        )

    status = (
        job.get("status")
        or ""
    )

    if (
        job.get("type")
        == "discovery"
    ):
        if status == "pending":
            return "Pending"

        if status == "running":
            return "Analyzing"

        if status == "succeeded":
            return "Analyzed"

        if status == "failed":
            return "Analysis failed"

        if status == "cancelled":
            return "Cancelled"

    return STATUS_LABELS.get(
        status,
        status or "-",
    )


def run_status(
    jobs_root: str | Path = (
        DEFAULT_JOBS_ROOT
    ),
) -> None:
    jobs = list_jobs(
        jobs_root=jobs_root,
    )

    if not jobs:
        print(
            "No RAVen jobs found."
        )
        return

    headers = (
        "Repository",
        "Task",
        "Target",
        "Status",
        "Started",
    )

    rows = []

    for job in jobs:
        rows.append(
            (
                (
                    job.get(
                        "repository"
                    )
                    or "-"
                ),
                (
                    job.get(
                        "type"
                    )
                    or "-"
                ),
                short_target(
                    job.get(
                        "target"
                    )
                ),
                job_phase(
                    job
                ),
                short_time(
                    job.get(
                        "started_at"
                    )
                ),
            )
        )

    widths = [
        max(
            len(
                headers[index]
            ),
            *[
                len(
                    row[index]
                )
                for row in rows
            ],
        )
        for index
        in range(
            len(headers)
        )
    ]

    def format_row(
        row,
    ) -> str:
        return "  ".join(
            value.ljust(
                widths[index]
            )
            for index, value
            in enumerate(row)
        )

    print(
        format_row(
            headers
        )
    )

    print(
        "  ".join(
            "-" * width
            for width in widths
        )
    )

    for row in rows:
        print(
            format_row(
                row
            )
        )