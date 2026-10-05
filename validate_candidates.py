#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent

CANDIDATES_CSV = ROOT / "smell_candidates.csv"
REPOSITORIES_CSV = ROOT / "repositories.csv"

VALIDATE_PAIR = ROOT / "validate_pair.py"

VALIDATION_ROOT = ROOT / "candidate_validation"
RESULTS_CSV = VALIDATION_ROOT / "results.csv"

COMMITS_CSV = ROOT / "commits.csv"


# ----------------------------------------------------------------------
# Expected input    
# ----------------------------------------------------------------------

REQUIRED_CANDIDATE_FIELDS = {
    "Repository",
    "SmellAlias",
    "Smell",
    "Entity",
    "Granularity",
    "CommitWithSmell",
    "CommitWithoutSmell",
}

REQUIRED_REPOSITORY_FIELDS = {
    "repository",
    "url",
}

SUPPORTED_SMELLS = {
    "IM",
    "HM",
    "GC",
    "UD",
}


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------

RESULT_FIELDS = [
    "Repository",
    "SmellAlias",
    "Smell",
    "Entity",
    "Granularity",
    "CommitWithSmell",
    "CommitWithoutSmell",
    "DirectChild",
    "EntityExistsAfter",
    "SmellInC",
    "SmellInCPrime",
    "SmellRemoved",
    "RefactoringCount",
    "Valid",
]

COMMIT_FIELDS = [
    "repository",
    "url",
    "commit",
]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def bool_text(value):
    """
    Convert Python/JSON boolean to CSV text.

    None means that the validation step was never reached because
    an earlier filter rejected the candidate.
    """

    if value is None:
        return ""

    return (
        "true"
        if bool(value)
        else "false"
    )


def clean(value):
    return (
        value.strip()
        if value is not None
        else ""
    )


def candidate_key(row):
    """
    Unique candidate identifier.

    Two different smell entities may share the same C -> C' pair,
    therefore Entity and SmellAlias are part of the key.
    """

    return (
        clean(row["Repository"]),
        clean(row["SmellAlias"]).upper(),
        clean(row["Entity"]),
        clean(row["CommitWithSmell"]),
        clean(row["CommitWithoutSmell"]),
    )


# ----------------------------------------------------------------------
# repositories.csv
# ----------------------------------------------------------------------

def load_repositories():
    if not REPOSITORIES_CSV.is_file():
        raise RuntimeError(
            f"Missing repositories file: "
            f"{REPOSITORIES_CSV}"
        )

    with REPOSITORIES_CSV.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:

        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            raise RuntimeError(
                f"Empty CSV: {REPOSITORIES_CSV}"
            )

        missing = (
            REQUIRED_REPOSITORY_FIELDS
            .difference(reader.fieldnames)
        )

        if missing:
            raise RuntimeError(
                f"{REPOSITORIES_CSV} is missing "
                f"columns: {sorted(missing)}"
            )

        repositories = {}

        for row in reader:

            name = clean(
                row.get("repository")
            )

            url = clean(
                row.get("url")
            )

            if not name or not url:
                continue

            if name in repositories:
                if repositories[name] != url:
                    raise RuntimeError(
                        f"Repository {name!r} has "
                        f"multiple URLs in "
                        f"{REPOSITORIES_CSV}"
                    )

            repositories[name] = url

    if not repositories:
        raise RuntimeError(
            f"No repositories found in "
            f"{REPOSITORIES_CSV}"
        )

    return repositories


# ----------------------------------------------------------------------
# smell_candidates.csv
# ----------------------------------------------------------------------

def load_candidates():

    if not CANDIDATES_CSV.is_file():
        raise RuntimeError(
            f"Missing candidate file: "
            f"{CANDIDATES_CSV}"
        )

    with CANDIDATES_CSV.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:

        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            raise RuntimeError(
                f"Empty CSV: "
                f"{CANDIDATES_CSV}"
            )

        missing = (
            REQUIRED_CANDIDATE_FIELDS
            .difference(reader.fieldnames)
        )

        if missing:
            raise RuntimeError(
                f"{CANDIDATES_CSV} is missing "
                f"columns: {sorted(missing)}"
            )

        rows = []

        seen = set()

        for row in reader:

            normalized = {
                key: clean(value)
                for key, value in row.items()
            }

            alias = (
                normalized[
                    "SmellAlias"
                ]
                .upper()
            )

            normalized[
                "SmellAlias"
            ] = alias

            if alias not in SUPPORTED_SMELLS:
                raise RuntimeError(
                    f"Unsupported smell alias: "
                    f"{alias!r}"
                )

            key = candidate_key(
                normalized
            )

            if key in seen:
                continue

            seen.add(key)

            rows.append(
                normalized
            )

    return rows


# ----------------------------------------------------------------------
# Validation-result JSON written by validate_pair.py
# ----------------------------------------------------------------------

def pair_result_file(
    repository,
    c,
    cprime,
):
    pairs_dir = VALIDATION_ROOT / "pairs"

    expected_name = (
        f"{repository}_"
        f"{c[:12]}_"
        f"{cprime[:12]}.json"
    )

    exact = pairs_dir / expected_name

    if exact.exists():
        return exact

    # Fallback case-insensitive lookup.
    expected_lower = expected_name.lower()

    if pairs_dir.is_dir():
        for path in pairs_dir.glob("*.json"):
            if path.name.lower() == expected_lower:
                return path

    # Return canonical expected path if nothing exists yet.
    return exact


def run_validate_pair(
    row,
    url,
    index,
    total,
):
    repository = (
        row["Repository"]
    )

    smell = (
        row["SmellAlias"]
    )

    fqn = (
        row["Entity"]
    )

    c = (
        row["CommitWithSmell"]
    )

    cprime = (
        row["CommitWithoutSmell"]
    )

    result_file = pair_result_file(
        repository,
        c,
        cprime,
    )

    #
    # validate_pair.py currently names its result only by:
    #
    #   repository + C + C'
    #
    # Multiple smell entities can share the same historical pair.
    # Remove only this small result JSON before each execution so we
    # never accidentally read the result from a previous entity.
    #
    # Heavy caches produced by Designite and RefactoringMiner are NOT
    # removed and will therefore be reused.
    #
    if result_file.exists():
        result_file.unlink()

    print()
    print("=" * 78)

    print(
        f"[{index}/{total}] "
        f"{repository} | "
        f"{smell} | "
        f"{fqn}"
    )

    print(
        f"C:  {c}"
    )

    print(
        f"C': {cprime}"
    )

    print("=" * 78)

    command = [
        sys.executable,
        str(VALIDATE_PAIR),
        "--repo",
        url,
        "--c",
        c,
        "--cprime",
        cprime,
        "--smell",
        smell,
        "--fqn",
        fqn,
    ]

    completed = subprocess.run(
        command,
        check=False,
    )

    #
    # A rejected candidate normally returns exit code 1.
    # Therefore the JSON result, rather than the process return code,
    # is the authoritative outcome.
    #
    
    # pair_result_file() already performs a case-insensitive lookup.
    result_file = pair_result_file(
        repository,
        c,
        cprime,
    )

    if not result_file.is_file():

        raise RuntimeError(
            "validate_pair.py did not create "
            f"the expected result file:\n"
            f"{result_file}\n"
            f"Process exit code: "
            f"{completed.returncode}"
        )

    try:
        data = json.loads(
            result_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON produced by "
            f"validate_pair.py: "
            f"{result_file}"
        ) from exc

    status = (
        data.get("status")
        or ""
    ).strip().upper()

    if status not in {
        "PASS",
        "REJECTED",
    }:
        raise RuntimeError(
            f"Unexpected validation status "
            f"{status!r} in "
            f"{result_file}"
        )

    return data


# ----------------------------------------------------------------------
# Convert validate_pair result to results.csv
# ----------------------------------------------------------------------

def make_result_row(
    candidate,
    validation,
):

    valid = (
        (
            validation.get("status")
            or ""
        ).upper()
        == "PASS"
    )

    #
    # IMPORTANT:
    #
    # Output RefactoringCount represents only the number of
    # refactorings involving the target FQN.
    #
    relevant_refactoring_count = (
        validation.get(
            "relevant_refactoring_count"
        )
    )

    return {
        "Repository":
            candidate["Repository"],

        "SmellAlias":
            candidate["SmellAlias"],

        "Smell":
            candidate["Smell"],

        "Entity":
            candidate["Entity"],

        "Granularity":
            candidate["Granularity"],

        "CommitWithSmell":
            candidate["CommitWithSmell"],

        "CommitWithoutSmell":
            candidate[
                "CommitWithoutSmell"
            ],

        "DirectChild":
            bool_text(
                validation.get(
                    "direct_child"
                )
            ),

        "EntityExistsAfter":
            bool_text(
                validation.get(
                    "fqn_exists_in_cprime"
                )
            ),

        "SmellInC":
            bool_text(
                validation.get(
                    "smell_in_c"
                )
            ),

        "SmellInCPrime":
            bool_text(
                validation.get(
                    "smell_in_cprime"
                )
            ),

        "SmellRemoved":
            bool_text(
                validation.get(
                    "smell_removed"
                )
            ),

        "RefactoringCount":
            (
                ""
                if relevant_refactoring_count
                is None
                else str(
                    relevant_refactoring_count
                )
            ),

        "Valid":
            bool_text(valid),
    }


# ----------------------------------------------------------------------
# CSV writers
# ----------------------------------------------------------------------

def write_results(rows):

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    with RESULTS_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=RESULT_FIELDS,
        )

        writer.writeheader()
        writer.writerows(rows)


def write_commits(
    result_rows,
    repositories,
):
    """
    Write only C commits belonging to valid candidates.

    Multiple valid instances may share the same repository+commit.
    Those commits are written only once.
    """

    commits = {}

    for row in result_rows:

        if (
            row.get("Valid")
            != "true"
        ):
            continue

        repository = (
            row["Repository"]
        )

        commit = (
            row["CommitWithSmell"]
        )

        key = (
            repository,
            commit,
        )

        commits[key] = {
            "repository":
                repository,

            "url":
                repositories[
                    repository
                ],

            "commit":
                commit,
        }

    #
    # Deterministic output.
    #
    ordered = sorted(
        commits.values(),
        key=lambda row: (
            row["repository"].casefold(),
            row["commit"],
        ),
    )

    with COMMITS_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=COMMIT_FIELDS,
        )

        writer.writeheader()
        writer.writerows(
            ordered
        )


# ----------------------------------------------------------------------
# Resume support
# ----------------------------------------------------------------------

def load_existing_results():

    if not RESULTS_CSV.is_file():
        return []

    with RESULTS_CSV.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:

        reader = csv.DictReader(
            handle
        )

        if (
            reader.fieldnames
            != RESULT_FIELDS
        ):
            raise RuntimeError(
                "Existing results.csv uses a "
                "different schema. "
                "Run without --resume or move "
                "the old file first."
            )

        return list(reader)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Validate all historical smell-removal "
            "candidates using validate_pair.py and "
            "generate commits.csv for build "
            "reproduction."
        )
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Reuse rows already present in "
            "candidate_validation/results.csv."
        ),
    )

    args = parser.parse_args()

    repositories = (
        load_repositories()
    )

    candidates = (
        load_candidates()
    )

    #
    # Check repository mappings before spending any time running tools.
    #
    candidate_repositories = {
        row["Repository"]
        for row in candidates
    }

    missing_repositories = sorted(
        candidate_repositories
        - set(repositories)
    )

    if missing_repositories:

        raise RuntimeError(
            "The following repositories are "
            "missing from repositories.csv:\n  "
            + "\n  ".join(
                missing_repositories
            )
        )

    print(
        f"Candidates:   {len(candidates)}"
    )

    print(
        f"Repositories: "
        f"{len(candidate_repositories)}"
    )

    print(
        f"Input:        "
        f"{CANDIDATES_CSV}"
    )

    print(
        f"Results:      "
        f"{RESULTS_CSV}"
    )

    print(
        f"Commits:      "
        f"{COMMITS_CSV}"
    )

    #
    # Resume
    #
    result_rows = []
    processed = set()

    if args.resume:

        result_rows = (
            load_existing_results()
        )

        processed = {
            (
                row["Repository"],
                row["SmellAlias"],
                row["Entity"],
                row["CommitWithSmell"],
                row["CommitWithoutSmell"],
            )
            for row in result_rows
        }

        print(
            f"Resume:       "
            f"{len(processed)} "
            f"already processed"
        )

    total = len(candidates)

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        key = candidate_key(
            candidate
        )

        if key in processed:

            print(
                f"[{index}/{total}] "
                f"SKIP already processed: "
                f"{candidate['Repository']} | "
                f"{candidate['Entity']}"
            )

            continue

        repository = (
            candidate[
                "Repository"
            ]
        )

        url = (
            repositories[
                repository
            ]
        )

        validation = (
            run_validate_pair(
                candidate,
                url,
                index,
                total,
            )
        )

        output_row = (
            make_result_row(
                candidate,
                validation,
            )
        )

        result_rows.append(
            output_row
        )

        processed.add(
            key
        )

        #
        # Persist after every candidate.
        #
        # If the process is interrupted, --resume can continue later
        # without losing completed validations.
        #
        write_results(
            result_rows
        )

        write_commits(
            result_rows,
            repositories,
        )

        print()
        print(
            "Summary: "
            f"DirectChild="
            f"{output_row['DirectChild']} | "
            f"EntityExistsAfter="
            f"{output_row['EntityExistsAfter']} | "
            f"SmellRemoved="
            f"{output_row['SmellRemoved']} | "
            f"RefactoringCount="
            f"{output_row['RefactoringCount']} | "
            f"Valid="
            f"{output_row['Valid']}"
        )

    #
    # Final output, including the case where every row was restored
    # through --resume.
    #
    write_results(
        result_rows
    )

    write_commits(
        result_rows,
        repositories,
    )

    valid_candidates = sum(
        row["Valid"] == "true"
        for row in result_rows
    )

    unique_commits = {
        (
            row["Repository"],
            row["CommitWithSmell"],
        )
        for row in result_rows
        if row["Valid"] == "true"
    }

    print()
    print("=" * 78)
    print("VALIDATION FINISHED")
    print("=" * 78)

    print(
        f"Candidates processed: "
        f"{len(result_rows)}"
    )

    print(
        f"Valid candidates:      "
        f"{valid_candidates}"
    )

    print(
        f"Unique valid C commits:"
        f" {len(unique_commits)}"
    )

    print()
    print(
        f"Detailed results: "
        f"{RESULTS_CSV}"
    )

    print(
        f"Build input:      "
        f"{COMMITS_CSV}"
    )

    return 0


if __name__ == "__main__":

    try:
        raise SystemExit(
            main()
        )

    except (
        RuntimeError,
        ValueError,
        FileNotFoundError,
    ) as exc:

        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )

        raise SystemExit(2)