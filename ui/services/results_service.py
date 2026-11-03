from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ui.services.candidates_service import (
    UICandidatesError,
    load_candidate_targets,
)


class UIResultsError(Exception):
    pass


SMELL_ORDER = [
    "IM",
    "HM",
    "GC",
    "UD",
]


STATUS_ORDER = [
    "Not reproduced",
    "Running",
    "Existing",
    "Reproduced",
]


def ordered_counts(
    counts: Counter[str],
    preferred_order: list[str],
) -> dict[str, int]:
    result: dict[str, int] = {}

    for key in preferred_order:
        if key in counts:
            result[key] = counts[
                key
            ]

    remaining = sorted(
        key
        for key in counts
        if key not in result
    )

    for key in remaining:
        result[
            key
        ] = counts[
            key
        ]

    return result


def load_results_summary(
    config_path: str | Path,
    repository: str | None = None,
) -> dict[str, Any]:
    try:
        candidate_data = (
            load_candidate_targets(
                config_path,
                repository=repository,
            )
        )

    except UICandidatesError as exc:
        raise UIResultsError(
            str(exc)
        ) from exc

    targets = candidate_data[
        "targets"
    ]

    smell_counts: Counter[str] = (
        Counter()
    )

    status_counts: Counter[str] = (
        Counter()
    )

    table_rows = []

    for target in targets:
        state = target[
            "state"
        ]

        status_counts[
            state
        ] += 1

        for candidate in target[
            "candidates"
        ]:
            smell_counts[
                candidate[
                    "SmellAlias"
                ]
            ] += 1

        ordered_smells = [
            smell
            for smell in SMELL_ORDER
            if smell in target[
                "smells"
            ]
        ]

        ordered_smells.extend(
            sorted(
                smell
                for smell
                in target[
                    "smells"
                ]
                if smell
                not in ordered_smells
            )
        )

        table_rows.append(
            {
                "Repository":
                    target[
                        "repository"
                    ],
                "Commit":
                    target[
                        "short_commit"
                    ],
                "Full commit":
                    target[
                        "commit"
                    ],
                "Smells":
                    ", ".join(
                        ordered_smells
                    ),
                "Candidates":
                    target[
                        "candidate_count"
                    ],
                "Status":
                    state,
            }
        )

    reproduced = (
        status_counts.get(
            "Reproduced",
            0,
        )
    )

    running = (
        status_counts.get(
            "Running",
            0,
        )
    )

    not_reproduced = (
        status_counts.get(
            "Not reproduced",
            0,
        )
    )

    existing = (
        status_counts.get(
            "Existing",
            0,
        )
    )

    return {
        "repository":
            candidate_data[
                "repository"
            ],
        "repositories":
            candidate_data[
                "repositories"
            ],
        "repository_count":
            candidate_data[
                "repository_count"
            ],
        "valid_candidates":
            candidate_data[
                "valid_candidate_count"
            ],
        "reproduction_targets":
            candidate_data[
                "reproduction_target_count"
            ],
        "reproduced":
            reproduced,
        "running":
            running,
        "not_reproduced":
            not_reproduced,
        "existing":
            existing,
        "smell_counts":
            ordered_counts(
                smell_counts,
                SMELL_ORDER,
            ),
        "status_counts":
            ordered_counts(
                status_counts,
                STATUS_ORDER,
            ),
        "table_rows":
            table_rows,
    }