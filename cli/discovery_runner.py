from __future__ import annotations

import argparse
from pathlib import Path

from cli.commands.analyze import (
    run_analysis,
)
from cli.commands.mine import (
    run_mining,
)
from cli.commands.validate import (
    run_validation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete RAVen "
            "candidate discovery pipeline."
        )
    )

    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help=(
            "Path to the RAVen "
            "configuration file."
        ),
    )

    parser.add_argument(
        "--restart",
        action="store_true",
        help=(
            "Restart discovery from the "
            "beginning instead of reusing "
            "existing results."
        ),
    )

    args = parser.parse_args()

    config_path = (
        args.config
        .expanduser()
        .resolve()
    )

    print()
    print("=" * 78)
    print(
        "RAVen discovery pipeline"
    )
    print("=" * 78)

    if args.restart:
        print(
            "Mode: restart"
        )
    else:
        print(
            "Mode: reuse existing results"
        )

    print()
    print(
        "[1/3] Mining historical commits"
    )
    print("-" * 78)

    run_mining(
        config_path=config_path,
        dry_run=False,
        overwrite=args.restart,
    )

    print()
    print(
        "[2/3] Analyzing "
        "smell-removal candidates"
    )
    print("-" * 78)

    run_analysis(
        config_path=config_path,
        dry_run=False,
    )

    print()
    print(
        "[3/3] Validating candidates"
    )
    print("-" * 78)

    run_validation(
        config_path=config_path,
        dry_run=False,
        resume=not args.restart,
    )

    print()
    print("=" * 78)
    print(
        "RAVen discovery completed "
        "successfully."
    )
    print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )