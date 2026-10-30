from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from cli.jobs import (
    read_job,
    utc_now,
    write_json_atomic,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Internal RAVen background job runner."
        )
    )

    parser.add_argument(
        "--job-file",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--log-file",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
    )

    args = parser.parse_args()

    command = list(
        args.command
    )

    if (
        command
        and command[0] == "--"
    ):
        command = command[1:]

    if not command:
        raise RuntimeError(
            "No command was provided "
            "to the job runner."
        )

    job_file = (
        args.job_file
        .expanduser()
        .resolve()
    )

    log_file = (
        args.log_file
        .expanduser()
        .resolve()
    )

    job = read_job(
        job_file
    )

    job["status"] = "running"
    job["started_at"] = utc_now()
    job["message"] = None

    log_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    environment = (
        os.environ.copy()
    )

    environment[
        "PYTHONUNBUFFERED"
    ] = "1"

    with log_file.open(
        "a",
        encoding="utf-8",
        buffering=1,
    ) as log:
        log.write(
            f"RAVen job: "
            f"{job['id']}\n"
        )

        log.write(
            "Command: "
            + " ".join(command)
            + "\n"
        )

        log.write(
            f"Started: "
            f"{job['started_at']}\n"
        )

        log.write(
            "=" * 78
            + "\n"
        )

        log.flush()

        try:
            process = (
                subprocess.Popen(
                    command,
                    cwd=job["cwd"],
                    stdin=(
                        subprocess.DEVNULL
                    ),
                    stdout=log,
                    stderr=(
                        subprocess.STDOUT
                    ),
                    text=True,
                    env=environment,
                )
            )

            job["pid"] = (
                process.pid
            )

            write_json_atomic(
                job_file,
                job,
            )

            return_code = (
                process.wait()
            )

            job["exit_code"] = (
                return_code
            )

            job["finished_at"] = (
                utc_now()
            )

            if return_code == 0:
                job["status"] = (
                    "succeeded"
                )

                job["message"] = (
                    None
                )

            else:
                job["status"] = (
                    "failed"
                )

                job["message"] = (
                    "The command exited "
                    f"with code {return_code}."
                )

            write_json_atomic(
                job_file,
                job,
            )

            log.write(
                "\n"
                + "=" * 78
                + "\n"
            )

            log.write(
                f"Finished: "
                f"{job['finished_at']}\n"
            )

            log.write(
                f"Exit code: "
                f"{return_code}\n"
            )

            log.flush()

            return return_code

        except Exception as exc:
            job["status"] = (
                "failed"
            )

            job["finished_at"] = (
                utc_now()
            )

            job["message"] = str(
                exc
            )

            write_json_atomic(
                job_file,
                job,
            )

            log.write(
                "\n"
                + "=" * 78
                + "\n"
            )

            log.write(
                f"Runner error: "
                f"{exc}\n"
            )

            log.flush()

            return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )