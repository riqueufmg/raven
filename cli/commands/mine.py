from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cli.config import load_config
from cli.repository import prepare_repository


HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")

MANIFEST_NAME = "mining_manifest.json"


class MiningError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_repository_url(
    url: str,
) -> str:
    value = url.strip().rstrip("/")

    if value.endswith(".git"):
        value = value[:-4]

    return value.casefold()


def result_commit_directories(
    output_path: Path,
) -> list[Path]:
    if not output_path.is_dir():
        return []

    return sorted(
        child
        for child in output_path.iterdir()
        if (
            child.is_dir()
            and HASH_RE.fullmatch(
                child.name
            )
        )
    )


def has_mining_results(
    output_path: Path,
) -> bool:
    return bool(
        result_commit_directories(
            output_path
        )
    )


def manifest_path(
    output_path: Path,
) -> Path:
    return (
        output_path
        / MANIFEST_NAME
    )


def load_manifest(
    output_path: Path,
) -> dict[str, Any] | None:
    path = manifest_path(
        output_path
    )

    if not path.is_file():
        return None

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

    except json.JSONDecodeError as exc:
        raise MiningError(
            f"Invalid mining manifest: {path}"
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise MiningError(
            f"Invalid mining manifest: {path}"
        )

    return data


def expected_manifest(
    *,
    repository_url: str,
    branch: str,
    since: str,
) -> dict[str, str]:
    return {
        "repository_url":
            repository_url,
        "branch":
            branch,
        "since":
            str(since),
        "designite_mode":
            "regular",
    }


def manifest_matches(
    manifest: dict[str, Any],
    expected: dict[str, str],
) -> bool:
    actual_repository = (
        manifest.get(
            "repository_url",
            "",
        )
    )

    if (
        normalize_repository_url(
            str(actual_repository)
        )
        !=
        normalize_repository_url(
            expected[
                "repository_url"
            ]
        )
    ):
        return False

    for field in (
        "branch",
        "since",
        "designite_mode",
    ):
        if (
            str(
                manifest.get(
                    field,
                    "",
                )
            )
            !=
            str(
                expected[field]
            )
        ):
            return False

    return True


def describe_manifest_mismatch(
    manifest: dict[str, Any],
    expected: dict[str, str],
) -> list[str]:
    differences = []

    actual_repository = (
        manifest.get(
            "repository_url"
        )
    )

    if (
        normalize_repository_url(
            str(
                actual_repository
                or ""
            )
        )
        !=
        normalize_repository_url(
            expected[
                "repository_url"
            ]
        )
    ):
        differences.append(
            "repository_url: "
            f"{actual_repository!r} "
            "!= "
            f"{expected['repository_url']!r}"
        )

    for field in (
        "branch",
        "since",
        "designite_mode",
    ):
        actual = manifest.get(
            field
        )

        expected_value = (
            expected[field]
        )

        if (
            str(actual or "")
            != str(
                expected_value
            )
        ):
            differences.append(
                f"{field}: "
                f"{actual!r} "
                "!= "
                f"{expected_value!r}"
            )

    return differences


def write_manifest(
    *,
    output_path: Path,
    expected: dict[str, str],
) -> Path:
    path = manifest_path(
        output_path
    )

    commit_count = len(
        result_commit_directories(
            output_path
        )
    )

    data = {
        **expected,
        "status":
            "completed",
        "completed_at":
            utc_now(),
        "analyzed_commit_count":
            commit_count,
    }

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

    temporary.replace(
        path
    )

    return path


def validate_existing_results(
    *,
    output_path: Path,
    expected: dict[str, str],
) -> bool:
    if not has_mining_results(
        output_path
    ):
        return False

    manifest = load_manifest(
        output_path
    )

    if manifest is None:
        raise MiningError(
            "Existing historical mining results were found, "
            "but no mining manifest is available.\n"
            f"Results:  {output_path}\n"
            f"Manifest: {manifest_path(output_path)}\n\n"
            "RAVen cannot safely determine whether these results "
            "were generated with the current repository, branch, "
            "date range, and analysis mode.\n"
            "Use discovery --restart to generate a new compatible "
            "mining dataset."
        )

    if (
        manifest.get(
            "status"
        )
        != "completed"
    ):
        raise MiningError(
            "The existing mining manifest does not describe "
            "a completed analysis.\n"
            f"Manifest: {manifest_path(output_path)}"
        )

    if not manifest_matches(
        manifest,
        expected,
    ):
        differences = (
            describe_manifest_mismatch(
                manifest,
                expected,
            )
        )

        details = "\n".join(
            f"  - {difference}"
            for difference
            in differences
        )

        raise MiningError(
            "Existing mining results are not compatible "
            "with the current configuration.\n"
            f"Results: {output_path}\n"
            f"Manifest: {manifest_path(output_path)}\n"
            f"Differences:\n{details}\n\n"
            "Use discovery --restart if you want to replace "
            "the existing mining results."
        )

    return True


def run_mining(
    config_path: str | Path,
    dry_run: bool = False,
    overwrite: bool | None = None,
) -> None:
    config = load_config(
        config_path
    )

    repository = config[
        "repository"
    ]

    analysis = config[
        "analysis"
    ]

    paths = config[
        "paths"
    ]

    mining = config.get(
        "mining",
        {},
    )

    repo_path = prepare_repository(
        url=repository["url"],
        branch=repository["branch"],
        repositories_root=(
            paths["repositories"]
        ),
    )

    results_root = Path(
        paths[
            "mining_results"
        ]
    )

    output_path = (
        results_root
        / repo_path.name
    )

    overwrite_enabled = (
        mining.get(
            "overwrite",
            False,
        )
        if overwrite is None
        else overwrite
    )

    expected = expected_manifest(
        repository_url=(
            repository["url"]
        ),
        branch=(
            repository["branch"]
        ),
        since=(
            analysis["since"]
        ),
    )

    print()
    print("RAVen mining")
    print("=" * 60)

    print(
        f"Repository:  "
        f"{repository['url']}"
    )

    print(
        f"Local path:  "
        f"{repo_path}"
    )

    print(
        f"Branch:      "
        f"{repository['branch']}"
    )

    print(
        f"Since:       "
        f"{analysis['since']}"
    )

    print(
        f"Output:      "
        f"{output_path}"
    )

    print(
        f"Overwrite:   "
        f"{str(overwrite_enabled).lower()}"
    )

    print("=" * 60)
    print()

    if (
        not overwrite_enabled
        and has_mining_results(
            output_path
        )
    ):
        reusable = (
            validate_existing_results(
                output_path=output_path,
                expected=expected,
            )
        )

        if reusable:
            manifest = load_manifest(
                output_path
            )

            print(
                "Compatible historical mining "
                "results were found."
            )

            print(
                "Mining will be skipped and "
                "the existing results will be reused."
            )

            if manifest:
                print(
                    "Analyzed commits: "
                    f"{manifest.get('analyzed_commit_count', 'unknown')}"
                )

            print(
                f"Results: {output_path}"
            )

            return

    designite_jar = Path(
        paths["designite"]
    )

    if not designite_jar.is_file():
        raise MiningError(
            f"DesigniteJava not found: "
            f"{designite_jar}"
        )

    command = [
        sys.executable,
        "-m",
        "mining.search_candidates",
        "--repo",
        str(repo_path),
        "--date",
        str(
            analysis["since"]
        ),
        "--designite-jar",
        str(designite_jar),
        "--output",
        str(output_path),
        "--branch",
        (
            "refs/heads/"
            f"{repository['branch']}"
        ),
        "--regular",
    ]

    if overwrite_enabled:
        command.append(
            "--overwrite"
        )

    print("Command:")

    print(
        " ".join(
            str(part)
            for part
            in command
        )
    )

    print()

    if dry_run:
        print(
            "Dry run completed. "
            "Mining was not executed."
        )
        return

    result = subprocess.run(
        command,
        check=False,
    )

    if result.returncode != 0:
        raise MiningError(
            "Mining failed with exit code "
            f"{result.returncode}."
        )

    if not has_mining_results(
        output_path
    ):
        raise MiningError(
            "Mining finished successfully, but no historical "
            "commit result directories were found in "
            f"{output_path}."
        )

    written_manifest = (
        write_manifest(
            output_path=output_path,
            expected=expected,
        )
    )

    print()
    print(
        "Mining completed successfully."
    )

    print(
        f"Results:  {output_path}"
    )

    print(
        f"Manifest: {written_manifest}"
    )