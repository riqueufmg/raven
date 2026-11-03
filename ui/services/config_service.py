from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


class UIConfigError(Exception):
    pass


def _read_yaml(
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

    except FileNotFoundError as exc:
        raise UIConfigError(
            f"Configuration file not found: {path}"
        ) from exc

    except yaml.YAMLError as exc:
        raise UIConfigError(
            f"Invalid YAML file: {path}: {exc}"
        ) from exc

    except OSError as exc:
        raise UIConfigError(
            f"Could not read configuration file "
            f"{path}: {exc}"
        ) from exc

    if data is None:
        return {}

    if not isinstance(
        data,
        dict,
    ):
        raise UIConfigError(
            f"Expected a YAML mapping in {path}."
        )

    return data


def _write_yaml_atomic(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_name(
        f".{path.name}.{uuid.uuid4().hex}.tmp"
    )

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as handle:
            yaml.safe_dump(
                data,
                handle,
                sort_keys=False,
                allow_unicode=True,
            )

        temporary_path.replace(
            path
        )

    except OSError as exc:
        try:
            temporary_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass

        raise UIConfigError(
            f"Could not write configuration file "
            f"{path}: {exc}"
        ) from exc


def _resolve_path(
    value: str | Path,
) -> Path:
    path = Path(
        value
    )

    if path.is_absolute():
        return path

    return (
        PROJECT_ROOT
        / path
    ).resolve()


def _create_discovery_snapshot(
    config_path: Path,
) -> Path:
    snapshot_directory = (
        PROJECT_ROOT
        / "jobs"
        / "configs"
    )

    snapshot_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    snapshot_name = (
        "discovery_"
        f"{uuid.uuid4().hex}.yml"
    )

    snapshot_path = (
        snapshot_directory
        / snapshot_name
    )

    try:
        shutil.copy2(
            config_path,
            snapshot_path,
        )

    except OSError as exc:
        raise UIConfigError(
            "Could not create discovery "
            f"configuration snapshot: {exc}"
        ) from exc

    return snapshot_path.resolve()


def load_ui_config(
    config_path: str | Path,
) -> dict[str, Any]:
    resolved_config_path = (
        _resolve_path(
            config_path
        )
    )

    config = _read_yaml(
        resolved_config_path
    )

    paths = config.get(
        "paths"
    )

    if not isinstance(
        paths,
        dict,
    ):
        raise UIConfigError(
            "Missing or invalid 'paths' "
            "section in RAVen configuration."
        )

    smell_registry_value = (
        paths.get(
            "smell_registry"
        )
    )

    if not smell_registry_value:
        raise UIConfigError(
            "Missing paths.smell_registry "
            "in RAVen configuration."
        )

    smell_registry_path = (
        _resolve_path(
            smell_registry_value
        )
    )

    smell_registry_data = (
        _read_yaml(
            smell_registry_path
        )
    )

    smells = smell_registry_data.get(
        "smells"
    )

    if not isinstance(
        smells,
        dict,
    ):
        raise UIConfigError(
            "The smell registry must contain "
            "a 'smells' mapping."
        )

    return {
        "config":
            config,
        "smells":
            smells,
        "config_path":
            resolved_config_path,
        "smell_registry_path":
            smell_registry_path,
    }


def save_discovery_config(
    *,
    config_path: str | Path,
    repository_url: str,
    branch: str,
    since: str,
    smells: list[str],
) -> Path:
    resolved_config_path = (
        _resolve_path(
            config_path
        )
    )

    config = _read_yaml(
        resolved_config_path
    )

    repository_url = (
        repository_url.strip()
    )

    branch = branch.strip()
    since = since.strip()

    if not repository_url:
        raise UIConfigError(
            "Repository URL is required."
        )

    if not branch:
        raise UIConfigError(
            "Repository branch is required."
        )

    if not since:
        raise UIConfigError(
            "Analysis starting date is required."
        )

    if not smells:
        raise UIConfigError(
            "At least one smell must be selected."
        )

    repository = config.get(
        "repository"
    )

    if not isinstance(
        repository,
        dict,
    ):
        repository = {}

    repository[
        "url"
    ] = repository_url

    repository[
        "branch"
    ] = branch

    config[
        "repository"
    ] = repository

    analysis = config.get(
        "analysis"
    )

    if not isinstance(
        analysis,
        dict,
    ):
        analysis = {}

    analysis[
        "since"
    ] = since

    analysis[
        "smells"
    ] = list(
        smells
    )

    config[
        "analysis"
    ] = analysis

    _write_yaml_atomic(
        resolved_config_path,
        config,
    )

    return _create_discovery_snapshot(
        resolved_config_path
    )