#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import sys

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

TOOLS = ROOT / "tools"

DESIGNITE = (
    TOOLS
    / "DesigniteJava.jar"
)

REFACTORING_MINER = (
    TOOLS
    / "RefactoringMiner-3.0.7"
    / "bin"
    / "RefactoringMiner"
)

BENCHMARK_ROOT = (
    ROOT
    / "benchmark"
)

REPOSITORIES_ROOT = (
    BENCHMARK_ROOT
    / "repositories"
)

VALIDATION_ROOT = (
    ROOT
    / "candidate_validation"
)

DESIGNITE_ROOT = (
    VALIDATION_ROOT
    / "designite"
)

REFACTORING_ROOT = (
    VALIDATION_ROOT
    / "refactorings"
)

PAIRS_ROOT = (
    VALIDATION_ROOT
    / "pairs"
)


# ----------------------------------------------------------------------
# Smells
# ----------------------------------------------------------------------

SMELLS = {
    "IM": {
        "name": "Insufficient Modularization",
        "file": "DesignSmells.csv",
        "granularity": "class",
    },
    "HM": {
        "name": "Hub-like Modularization",
        "file": "DesignSmells.csv",
        "granularity": "class",
    },
    "GC": {
        "name": "God Component",
        "file": "ArchitectureSmells.csv",
        "granularity": "package",
    },
    "UD": {
        "name": "Unstable Dependency",
        "file": "ArchitectureSmells.csv",
        "granularity": "package",
    },
}


# ----------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------

def run(
    cmd,
    *,
    cwd=None,
    check=True,
    stdout=None,
):
    print(
        "+",
        " ".join(
            str(x)
            for x in cmd
        ),
    )

    result = subprocess.run(
        [
            str(x)
            for x in cmd
        ],
        cwd=cwd,
        text=True,
        stdout=stdout,
        stderr=(
            subprocess.STDOUT
            if stdout
            else None
        ),
        check=False,
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code "
            f"{result.returncode}: "
            + " ".join(str(x) for x in cmd)
        )

    return result


def git(
    repo: Path,
    *args: str,
    check=True,
):
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            *args,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if (
        check
        and result.returncode != 0
    ):
        raise RuntimeError(
            result.stderr.strip()
        )

    return result


def repository_name(
    url: str,
) -> str:

    path = (
        urlparse(url)
        .path
        .rstrip("/")
    )

    name = Path(path).name

    if name.endswith(".git"):
        name = name[:-4]

    if not name:
        raise ValueError(
            f"Cannot determine repository "
            f"name from URL: {url}"
        )

    return name


# ----------------------------------------------------------------------
# Repository
# ----------------------------------------------------------------------

def ensure_repository(
    name: str,
    url: str,
) -> Path:

    repo_root = (
        REPOSITORIES_ROOT
        / name
    )

    repo = (
        repo_root
        / "repository"
    )

    if repo.is_dir():
        print(
            f"Repository already available: "
            f"{repo}"
        )
        return repo

    repo_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Repository not found. "
        f"Cloning {url}"
    )

    run(
        [
            "git",
            "clone",
            url,
            repo,
        ]
    )

    return repo


def commit_exists(
    repo: Path,
    commit: str,
) -> bool:

    result = git(
        repo,
        "cat-file",
        "-e",
        f"{commit}^{{commit}}",
        check=False,
    )

    return (
        result.returncode == 0
    )


def ensure_commits(
    repo: Path,
    commits: list[str],
):

    missing = [
        commit
        for commit in commits
        if not commit_exists(
            repo,
            commit,
        )
    ]

    if not missing:
        return

    print(
        "Some commits are missing. "
        "Fetching repository history."
    )

    run(
        [
            "git",
            "-C",
            repo,
            "fetch",
            "--all",
            "--tags",
            "--prune",
        ]
    )

    missing = [
        commit
        for commit in commits
        if not commit_exists(
            repo,
            commit,
        )
    ]

    if missing:
        raise RuntimeError(
            "Commits not found after fetch: "
            + ", ".join(missing)
        )


# ----------------------------------------------------------------------
# Git relationship
# ----------------------------------------------------------------------

def is_direct_child(
    repo: Path,
    parent: str,
    child: str,
) -> bool:

    result = git(
        repo,
        "rev-list",
        "--parents",
        "-n",
        "1",
        child,
    )

    parts = (
        result.stdout
        .strip()
        .split()
    )

    if len(parts) < 2:
        return False

    resolved_parent = (
        git(
            repo,
            "rev-parse",
            parent,
        )
        .stdout
        .strip()
    )

    immediate_parents = (
        parts[1:]
    )

    return (
        resolved_parent
        in immediate_parents
    )


# ----------------------------------------------------------------------
# FQN existence
# ----------------------------------------------------------------------

def java_files(
    repo: Path,
    commit: str,
) -> list[str]:

    result = git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        commit,
    )

    return [
        path.strip().replace("\\", "/")
        for path
        in result.stdout.splitlines()
        if path.strip().endswith(
            ".java"
        )
    ]


def fqn_exists(
    repo: Path,
    commit: str,
    smell_alias: str,
    fqn: str,
) -> bool:

    granularity = (
        SMELLS[
            smell_alias
        ][
            "granularity"
        ]
    )

    files = java_files(
        repo,
        commit,
    )

    # --------------------------------------------------------------
    # Package-level smells
    # GC and UD
    # --------------------------------------------------------------

    if granularity == "package":

        package_path = (
            fqn.replace(
                ".",
                "/",
            )
        )

        marker = (
            f"/{package_path}/"
        )

        for path in files:

            padded = (
                "/"
                + path.lstrip("/")
            )

            if (
                marker in padded
                or padded.startswith(
                    f"/{package_path}/"
                )
            ):
                return True

        return False

    # --------------------------------------------------------------
    # Class-level smells
    # IM and HM
    # --------------------------------------------------------------

    parts = fqn.rsplit(
        ".",
        1,
    )

    if len(parts) != 2:
        return False

    package = parts[0]
    class_name = parts[1]

    suffix = (
        package.replace(
            ".",
            "/",
        )
        + "/"
        + class_name
        + ".java"
    )

    return any(
        path.endswith(
            suffix
        )
        for path in files
    )


# ----------------------------------------------------------------------
# Designite
# ----------------------------------------------------------------------

def run_designite(
    repository: str,
    repo: Path,
    commit: str,
) -> Path:

    repository_root = (
        DESIGNITE_ROOT
        / repository
    )

    repository_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_dir = (
        repository_root
        / commit
    )

    marker = (
        output_dir
        / ".complete"
    )

    log_file = (
        repository_root
        / f"{commit}.log"
    )

    if marker.exists():

        print(
            f"Designite cache: "
            f"{repository} "
            f"{commit[:12]}"
        )

        return output_dir

    if output_dir.exists():
        shutil.rmtree(
            output_dir
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix=(
            f"designite-"
            f"{repository}-"
            f"{commit[:8]}-"
        )
    ) as temp:

        temp = Path(temp)

        source_dir = (
            temp
            / "source"
        )

        source_dir.mkdir()

        archive = (
            temp
            / "source.tar"
        )

        # Extract exact commit without changing shared repository HEAD.
        with archive.open(
            "wb"
        ) as archive_file:

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "archive",
                    commit,
                ],
                check=True,
                stdout=archive_file,
            )

        run(
            [
                "tar",
                "-xf",
                archive,
                "-C",
                source_dir,
            ]
        )

        # Designite requires an empty output directory.
        # Therefore the log stays outside output_dir.
        with log_file.open(
            "w"
        ) as log:

            result = run(
                [
                    "java",
                    "-jar",
                    DESIGNITE,
                    "-i",
                    source_dir,
                    "-o",
                    output_dir,
                ],
                check=False,
                stdout=log,
            )

        if result.returncode != 0:

            raise RuntimeError(
                "Designite failed. "
                f"See log: {log_file}"
            )

    marker.touch()

    return output_dir


def smell_exists(
    output_dir: Path,
    smell_alias: str,
    fqn: str,
) -> bool:

    definition = (
        SMELLS[
            smell_alias
        ]
    )

    smell_name = (
        definition[
            "name"
        ]
    )

    granularity = (
        definition[
            "granularity"
        ]
    )

    csv_file = (
        output_dir
        / definition[
            "file"
        ]
    )

    if not csv_file.is_file():
        raise RuntimeError(
            f"Missing Designite output: "
            f"{csv_file}"
        )

    with csv_file.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:

        reader = csv.DictReader(
            handle
        )

        if not reader.fieldnames:
            return False

        for row in reader:

            row_smell = (
                row.get(
                    "Smell",
                    "",
                )
                .strip()
            )

            if (
                row_smell.casefold()
                != smell_name.casefold()
            ):
                continue

            package = (
                row.get(
                    "Package",
                    "",
                )
                .strip()
            )

            # ------------------------------------------------------
            # Package smell
            # ------------------------------------------------------

            if (
                granularity
                == "package"
            ):

                entity = package

            # ------------------------------------------------------
            # Class smell
            # ------------------------------------------------------

            else:

                class_name = (
                    row.get(
                        "Class",
                        "",
                    )
                    .strip()
                )

                if (
                    package
                    and class_name
                ):
                    entity = (
                        f"{package}."
                        f"{class_name}"
                    )
                else:
                    entity = (
                        class_name
                        or package
                    )

            if entity == fqn:
                return True

    return False


# ----------------------------------------------------------------------
# RefactoringMiner
# ----------------------------------------------------------------------

def run_refactoring_miner(
    repository: str,
    repo: Path,
    c: str,
    cprime: str,
) -> Path:

    output_root = (
        REFACTORING_ROOT
        / repository
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    pair_name = (
        f"{c[:12]}_"
        f"{cprime[:12]}"
    )

    output_json = (
        output_root
        / f"{pair_name}.json"
    )

    log_file = (
        output_root
        / f"{pair_name}.log"
    )

    if output_json.exists():

        print(
            f"RefactoringMiner cache: "
            f"{repository} "
            f"{cprime[:12]}"
        )

        return output_json

    # Analyze the refactorings introduced by C'.
    # Since we already confirmed that C is an immediate parent,
    # this corresponds to the transition C -> C'.
    with log_file.open(
        "w"
    ) as log:

        result = run(
            [
                REFACTORING_MINER,
                "-c",
                repo,
                cprime,
                "-json",
                output_json,
            ],
            check=False,
            stdout=log,
        )

    if result.returncode != 0:

        raise RuntimeError(
            "RefactoringMiner failed. "
            f"See log: {log_file}"
        )

    return output_json


def read_refactorings(
    json_file: Path,
) -> list[dict]:

    if not json_file.is_file():
        return []

    data = json.loads(
        json_file.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    result = []

    for commit in data.get(
        "commits",
        [],
    ):

        result.extend(
            commit.get(
                "refactorings",
                [],
            )
        )

    return result


def relevant_refactorings(
    refactorings: list[dict],
    fqn: str,
) -> list[dict]:

    matches = []

    for refactoring in refactorings:

        description = (
            refactoring.get(
                "description",
                "",
            )
            or ""
        )

        if (
            fqn
            in description
        ):
            matches.append(
                refactoring
            )

    return matches


# ----------------------------------------------------------------------
# Result persistence
# ----------------------------------------------------------------------

def result_file(
    repository: str,
    c: str,
    cprime: str,
) -> Path:

    PAIRS_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        PAIRS_ROOT
        / (
            f"{repository}_"
            f"{c[:12]}_"
            f"{cprime[:12]}.json"
        )
    )


def write_result(
    repository: str,
    c: str,
    cprime: str,
    data: dict,
):

    file = result_file(
        repository,
        c,
        cprime,
    )

    file.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"Result written to: "
        f"{file}"
    )


def reject(
    result: dict,
    reason: str,
):

    result[
        "status"
    ] = "REJECTED"

    result[
        "reason"
    ] = reason

    print()
    print(
        f"REJECTED: {reason}"
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():

    global VALIDATION_ROOT
    global DESIGNITE_ROOT
    global REFACTORING_ROOT
    global PAIRS_ROOT

    parser = argparse.ArgumentParser(
        description=(
            "Validate one historical smell-removal "
            "candidate pair C -> C'."
        )
    )

    parser.add_argument(
        "--repo",
        required=True,
        help=(
            "Git repository URL."
        ),
    )

    parser.add_argument(
        "--repository-name",
        default="",
        help=(
            "Canonical repository name used by the caller. "
            "If omitted, the name is derived from --repo."
        ),
    )

    parser.add_argument(
        "--c",
        required=True,
        help=(
            "Commit containing the smell."
        ),
    )

    parser.add_argument(
        "--cprime",
        required=True,
        help=(
            "Candidate direct child commit "
            "where the smell should be removed."
        ),
    )

    parser.add_argument(
        "--smell",
        required=True,
        choices=SMELLS.keys(),
        help=(
            "Smell alias: IM, HM, GC, or UD."
        ),
    )

    parser.add_argument(
        "--fqn",
        required=True,
        help=(
            "Fully qualified target entity."
        ),
    )

    parser.add_argument(
        "--validation-root",
        type=Path,
        default=VALIDATION_ROOT,
        help=(
            "Directory used for validation caches and pair results. "
            "Default: candidate_validation."
        ),
    )

    args = parser.parse_args()

    VALIDATION_ROOT = (
        args.validation_root
        .expanduser()
        .resolve()
    )

    DESIGNITE_ROOT = (
        VALIDATION_ROOT
        / "designite"
    )

    REFACTORING_ROOT = (
        VALIDATION_ROOT
        / "refactorings"
    )

    PAIRS_ROOT = (
        VALIDATION_ROOT
        / "pairs"
    )

    repository = (
        args.repository_name.strip()
        or repository_name(args.repo)
    )

    c = (
        args.c
        .strip()
    )

    cprime = (
        args.cprime
        .strip()
    )

    smell = (
        args.smell
        .strip()
        .upper()
    )

    fqn = (
        args.fqn
        .strip()
    )

    result = {
        "repository":
            repository,

        "url":
            args.repo,

        "smell":
            smell,

        "fqn":
            fqn,

        "c":
            c,

        "cprime":
            cprime,
    }

    print("=" * 70)

    print(
        f"Repository: {repository}"
    )

    print(
        f"Smell:      {smell}"
    )

    print(
        f"FQN:        {fqn}"
    )

    print(
        f"C:          {c}"
    )

    print(
        f"C':         {cprime}"
    )

    print("=" * 70)

    # --------------------------------------------------------------
    # Repository
    # --------------------------------------------------------------

    repo = ensure_repository(
        repository,
        args.repo,
    )

    ensure_commits(
        repo,
        [
            c,
            cprime,
        ],
    )

    # --------------------------------------------------------------
    # 1. Direct-child relationship
    # --------------------------------------------------------------

    print()
    print(
        "[1/4] Checking direct "
        "parent-child relationship..."
    )

    direct_child = (
        is_direct_child(
            repo,
            c,
            cprime,
        )
    )

    result[
        "direct_child"
    ] = direct_child

    if not direct_child:

        reject(
            result,
            "CPRIME_NOT_DIRECT_CHILD_OF_C",
        )

        write_result(
            repository,
            c,
            cprime,
            result,
        )

        return 1

    print("PASS")

    # --------------------------------------------------------------
    # 2. FQN still exists in C'
    # --------------------------------------------------------------

    print()
    print(
        "[2/4] Checking FQN "
        "existence in C'..."
    )

    exists_after = (
        fqn_exists(
            repo,
            cprime,
            smell,
            fqn,
        )
    )

    result[
        "fqn_exists_in_cprime"
    ] = exists_after

    if not exists_after:

        reject(
            result,
            "FQN_MISSING_IN_CPRIME",
        )

        write_result(
            repository,
            c,
            cprime,
            result,
        )

        return 1

    print("PASS")

    # --------------------------------------------------------------
    # 3. Smell transition
    # --------------------------------------------------------------

    print()
    print(
        "[3/4] Checking smell "
        "transition C -> C'..."
    )

    c_output = (
        run_designite(
            repository,
            repo,
            c,
        )
    )

    smell_in_c = (
        smell_exists(
            c_output,
            smell,
            fqn,
        )
    )

    result[
        "smell_in_c"
    ] = smell_in_c

    if not smell_in_c:

        reject(
            result,
            "SMELL_NOT_FOUND_IN_C",
        )

        write_result(
            repository,
            c,
            cprime,
            result,
        )

        return 1

    cprime_output = (
        run_designite(
            repository,
            repo,
            cprime,
        )
    )

    smell_in_cprime = (
        smell_exists(
            cprime_output,
            smell,
            fqn,
        )
    )

    result[
        "smell_in_cprime"
    ] = smell_in_cprime

    result[
        "smell_removed"
    ] = (
        smell_in_c
        and not smell_in_cprime
    )

    if smell_in_cprime:

        reject(
            result,
            "SMELL_NOT_REMOVED",
        )

        write_result(
            repository,
            c,
            cprime,
            result,
        )

        return 1

    print("PASS")

    # --------------------------------------------------------------
    # 4. Relevant refactoring
    # --------------------------------------------------------------

    print()
    print(
        "[4/4] Checking "
        "refactorings in C'..."
    )

    rm_json = (
        run_refactoring_miner(
            repository,
            repo,
            c,
            cprime,
        )
    )

    all_refs = (
        read_refactorings(
            rm_json
        )
    )

    relevant = (
        relevant_refactorings(
            all_refs,
            fqn,
        )
    )

    result[
        "refactoring_count"
    ] = len(
        all_refs
    )

    result[
        "relevant_refactoring_count"
    ] = len(
        relevant
    )

    result[
        "relevant_refactorings"
    ] = [
        (
            ref.get(
                "description"
            )
            or ref.get(
                "type"
            )
            or ""
        )
        for ref in relevant
    ]

    result[
        "refactoring_json"
    ] = str(
        rm_json.relative_to(
            ROOT
        )
    )

    if not relevant:

        reject(
            result,
            "NO_REFACTORING_INVOLVING_FQN",
        )

        write_result(
            repository,
            c,
            cprime,
            result,
        )

        return 1

    print(
        f"PASS "
        f"({len(relevant)} relevant "
        f"refactoring(s))"
    )

    # --------------------------------------------------------------
    # Final result
    # --------------------------------------------------------------

    result[
        "status"
    ] = "PASS"

    result[
        "reason"
    ] = (
        "VALID_HISTORICAL_REFACTORING_CANDIDATE"
    )

    write_result(
        repository,
        c,
        cprime,
        result,
    )

    print()
    print("=" * 70)
    print(
        "VALID CANDIDATE"
    )
    print(
        "Next step: run repro.py "
        "for commit C."
    )
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )