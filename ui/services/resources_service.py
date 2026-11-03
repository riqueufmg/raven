from __future__ import annotations

import time
from typing import Any

import psutil


class UIResourcesError(Exception):
    pass


def bytes_to_gb(value: int | float) -> float:
    return round(
        float(value) / (1024 ** 3),
        2,
    )


def get_machine_resources() -> dict[str, Any]:
    try:
        memory = psutil.virtual_memory()

        return {
            "cpu_percent": round(
                psutil.cpu_percent(
                    interval=0.1,
                ),
                1,
            ),
            "memory_total_gb": bytes_to_gb(
                memory.total
            ),
            "memory_used_gb": bytes_to_gb(
                memory.used
            ),
            "memory_available_gb": bytes_to_gb(
                memory.available
            ),
            "memory_percent": round(
                memory.percent,
                1,
            ),
            "cpu_count_logical": (
                psutil.cpu_count(
                    logical=True
                )
                or 0
            ),
            "cpu_count_physical": (
                psutil.cpu_count(
                    logical=False
                )
                or 0
            ),
        }

    except Exception as exc:
        raise UIResourcesError(
            f"Could not read machine resources: {exc}"
        ) from exc


def _collect_process_tree(
    pid: int,
) -> list[psutil.Process]:
    try:
        root = psutil.Process(
            pid
        )
    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):
        return []

    processes = [
        root
    ]

    try:
        processes.extend(
            root.children(
                recursive=True
            )
        )
    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):
        pass

    unique: dict[
        int,
        psutil.Process,
    ] = {}

    for process in processes:
        unique[
            process.pid
        ] = process

    return list(
        unique.values()
    )


def get_process_tree_resources(
    pid: int | None,
    sample_interval: float = 0.15,
) -> dict[str, Any]:
    if not pid:
        return {
            "available": False,
            "cpu_percent": 0.0,
            "memory_gb": 0.0,
            "process_count": 0,
        }

    processes = (
        _collect_process_tree(
            pid
        )
    )

    if not processes:
        return {
            "available": False,
            "cpu_percent": 0.0,
            "memory_gb": 0.0,
            "process_count": 0,
        }

    sampled_processes = []

    for process in processes:
        try:
            process.cpu_percent(
                interval=None
            )
            sampled_processes.append(
                process
            )
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            continue

    if sample_interval > 0:
        time.sleep(
            sample_interval
        )

    cpu_percent = 0.0
    memory_bytes = 0
    alive_count = 0

    for process in sampled_processes:
        try:
            cpu_percent += (
                process.cpu_percent(
                    interval=None
                )
            )

            memory_bytes += (
                process.memory_info().rss
            )

            alive_count += 1

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            continue

    return {
        "available": (
            alive_count > 0
        ),
        "cpu_percent": round(
            cpu_percent,
            1,
        ),
        "memory_gb": bytes_to_gb(
            memory_bytes
        ),
        "process_count": (
            alive_count
        ),
    }


def get_job_resources(
    jobs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    resources = {}

    active_jobs = [
        job
        for job in jobs
        if job.get(
            "status"
        ) in {
            "pending",
            "running",
        }
        or job.get(
            "phase"
        ) in {
            "Pending",
            "Analyzing",
            "Preparing repository",
            "Preparing environment",
            "Running Codex",
            "Offline validation",
        }
    ]

    for job in active_jobs:
        job_id = job.get(
            "id"
        )

        if not job_id:
            continue

        pid = job.get(
            "pid"
        )

        try:
            pid_value = (
                int(pid)
                if pid is not None
                else None
            )
        except (
            TypeError,
            ValueError,
        ):
            pid_value = None

        resources[
            job_id
        ] = (
            get_process_tree_resources(
                pid_value
            )
        )

    return resources