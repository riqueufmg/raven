from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_JOBS_ROOT = Path("jobs")
DEFAULT_LOGS_ROOT = Path("logs/jobs")


class JobError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def read_job(
    path: str | Path,
) -> dict[str, Any]:
    path = Path(path)

    if not path.is_file():
        raise JobError(
            f"Job file not found: {path}"
        )

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

    except json.JSONDecodeError as exc:
        raise JobError(
            f"Invalid job metadata: {path}"
        ) from exc

    if not isinstance(data, dict):
        raise JobError(
            f"Invalid job metadata: {path}"
        )

    return data


def process_is_alive(
    pid: int | None,
) -> bool:
    if not pid:
        return False

    try:
        os.kill(pid, 0)

    except ProcessLookupError:
        return False

    except PermissionError:
        return True

    return True


def reconcile_job(
    path: str | Path,
) -> dict[str, Any]:
    path = Path(path)

    job = read_job(path)

    if (
        job.get("status") == "running"
        and not process_is_alive(
            job.get("pid")
        )
    ):
        job["status"] = "failed"

        job["finished_at"] = (
            job.get("finished_at")
            or utc_now()
        )

        job["message"] = (
            "The background process is no longer running "
            "and did not record a final status."
        )

        write_json_atomic(
            path,
            job,
        )

    return job


def list_jobs(
    jobs_root: str | Path = DEFAULT_JOBS_ROOT,
) -> list[dict[str, Any]]:
    jobs_root = Path(jobs_root)

    if not jobs_root.is_dir():
        return []

    jobs = []

    for path in jobs_root.glob("*.json"):
        try:
            job = reconcile_job(path)

        except JobError:
            continue

        job["_metadata_path"] = str(path)

        jobs.append(job)

    jobs.sort(
        key=lambda job: (
            job.get("created_at")
            or ""
        ),
        reverse=True,
    )

    return jobs


def find_active_job(
    *,
    job_type: str,
    repository: str,
    target: str | None = None,
    jobs_root: str | Path = DEFAULT_JOBS_ROOT,
) -> dict[str, Any] | None:
    for job in list_jobs(
        jobs_root=jobs_root,
    ):
        if (
            job.get("type") != job_type
            or job.get("repository") != repository
        ):
            continue

        if (
            target is not None
            and job.get("target") != target
        ):
            continue

        if job.get("status") in {
            "pending",
            "running",
        }:
            return job

    return None


def start_job(
    *,
    job_type: str,
    repository: str,
    command: Sequence[str],
    target: str | None = None,
    jobs_root: str | Path = DEFAULT_JOBS_ROOT,
    logs_root: str | Path = DEFAULT_LOGS_ROOT,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    if not command:
        raise JobError(
            "A background job requires a command."
        )

    jobs_root = Path(jobs_root)
    logs_root = Path(logs_root)

    jobs_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    logs_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    short_id = uuid.uuid4().hex[:8]

    timestamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )

    parts = [
        repository,
        job_type,
    ]

    if target:
        parts.append(
            target[:12]
        )

    parts.extend(
        [
            timestamp,
            short_id,
        ]
    )

    job_id = "-".join(parts)

    metadata_path = (
        jobs_root
        / f"{job_id}.json"
    )

    log_path = (
        logs_root
        / f"{job_id}.log"
    )

    working_directory = (
        Path(cwd).resolve()
        if cwd
        else Path.cwd().resolve()
    )

    metadata = {
        "id": job_id,
        "type": job_type,
        "repository": repository,
        "target": target,
        "status": "pending",
        "pid": None,
        "runner_pid": None,
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "command": [
            str(part)
            for part in command
        ],
        "cwd": str(
            working_directory
        ),
        "log": str(log_path),
        "message": None,
    }

    write_json_atomic(
        metadata_path,
        metadata,
    )

    runner_command = [
        sys.executable,
        "-m",
        "cli.job_runner",
        "--job-file",
        str(
            metadata_path.resolve()
        ),
        "--log-file",
        str(
            log_path.resolve()
        ),
        "--",
        *[
            str(part)
            for part in command
        ],
    ]

    try:
        process = subprocess.Popen(
            runner_command,
            cwd=str(
                working_directory
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

    except OSError as exc:
        metadata["status"] = "failed"
        metadata["finished_at"] = utc_now()
        metadata["message"] = (
            "Could not start background job: "
            f"{exc}"
        )

        write_json_atomic(
            metadata_path,
            metadata,
        )

        raise JobError(
            metadata["message"]
        ) from exc

    metadata["runner_pid"] = (
        process.pid
    )

    write_json_atomic(
        metadata_path,
        metadata,
    )

    return metadata