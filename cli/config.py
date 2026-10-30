from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


def load_yaml(path: str | Path) -> dict:
    path = Path(path)

    if not path.exists():
        raise ConfigError(
            f"Configuration file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ConfigError(
            f"Invalid YAML configuration: {path}"
        )

    return data


def load_smell_registry(path: str | Path) -> dict:
    data = load_yaml(path)

    smells = data.get("smells")

    if not isinstance(smells, dict):
        raise ConfigError(
            "smells.yml must contain a 'smells' mapping."
        )

    required_fields = {
        "display_name",
        "granularity",
        "detector",
    }

    for smell_id, definition in smells.items():

        if not isinstance(definition, dict):
            raise ConfigError(
                f"Invalid definition for smell '{smell_id}'."
            )

        missing = required_fields.difference(
            definition.keys()
        )

        if missing:
            raise ConfigError(
                f"Smell '{smell_id}' is missing fields: "
                f"{sorted(missing)}"
            )

        detector = definition["detector"]

        if not isinstance(detector, dict):
            raise ConfigError(
                f"Invalid detector definition for "
                f"smell '{smell_id}'."
            )

        detector_required = {
            "tool",
            "category",
            "artifact",
            "smell_name",
        }

        detector_missing = (
            detector_required.difference(detector.keys())
        )

        if detector_missing:
            raise ConfigError(
                f"Smell '{smell_id}' detector is missing: "
                f"{sorted(detector_missing)}"
            )

    return smells


def load_config(path: str | Path) -> dict:
    path = Path(path)
    config = load_yaml(path)

    repository = config.get("repository")

    if not isinstance(repository, dict):
        raise ConfigError(
            "raven.yml must contain a 'repository' section."
        )

    if not repository.get("url"):
        raise ConfigError(
            "repository.url is required."
        )

    if not repository.get("branch"):
        raise ConfigError(
            "repository.branch is required."
        )

    analysis = config.get("analysis")

    if not isinstance(analysis, dict):
        raise ConfigError(
            "raven.yml must contain an 'analysis' section."
        )

    selected_smells = analysis.get("smells")

    if not isinstance(selected_smells, list):
        raise ConfigError(
            "analysis.smells must be a list."
        )

    paths = config.get("paths", {})

    smell_registry_path = paths.get(
        "smell_registry",
        "config/smells.yml",
    )

    registry = load_smell_registry(
        smell_registry_path
    )

    unknown = [
        smell
        for smell in selected_smells
        if smell not in registry
    ]

    if unknown:
        raise ConfigError(
            "Unknown smell identifiers in raven.yml: "
            f"{unknown}"
        )

    config["_smells"] = registry

    return config