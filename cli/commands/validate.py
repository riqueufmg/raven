import subprocess
import sys
from pathlib import Path

from cli.config import load_config
from cli.repository import prepare_repository


class ValidationError(Exception):
    pass


def run_validation(
    config_path: str | Path,
    dry_run: bool = False,
    resume: bool = False,
) -> None:
    config = load_config(config_path)

    repository = config["repository"]
    analysis = config["analysis"]
    paths = config["paths"]

    repo_path = prepare_repository(
        url=repository["url"],
        branch=repository["branch"],
        repositories_root=paths["repositories"],
    )

    repo_name = repo_path.name
    smells = analysis["smells"]

    mining_results = Path(paths["mining_results"])
    validation_base = Path(paths["candidate_validation"])
    validation_root = validation_base / repo_name

    candidates_csv = validation_root / "candidates.csv"
    results_csv = validation_root / "results.csv"
    commits_csv = validation_root / "commits.csv"

    repositories_csv = Path("repositories.csv")

    if not repositories_csv.is_file():
        raise ValidationError(
            f"Repository mapping file not found: "
            f"{repositories_csv}"
        )

    collect_command = [
        sys.executable,
        "mining/collect_smell_candidates.py",
        "--results-root",
        str(mining_results),
        "--repositories",
        repo_name,
        "--smells",
        *smells,
        "--output",
        str(candidates_csv),
    ]

    validate_command = [
        sys.executable,
        "validate_candidates.py",
        "--candidates",
        str(candidates_csv),
        "--repositories-file",
        str(repositories_csv),
        "--validation-root",
        str(validation_root),
        "--results",
        str(results_csv),
        "--commits",
        str(commits_csv),
    ]

    if resume:
        validate_command.append("--resume")

    print()
    print("RAVen candidate validation")
    print("=" * 60)
    print(f"Repository:       {repository['url']}")
    print(f"Local path:       {repo_path}")
    print(f"Smells:           {', '.join(smells)}")
    print(f"Mining results:   {mining_results / repo_name}")
    print(f"Validation root:  {validation_root}")
    print(f"Candidates:       {candidates_csv}")
    print(f"Results:          {results_csv}")
    print(f"Commits:          {commits_csv}")
    print("=" * 60)
    print()

    print("Candidate collection command:")
    print(
        " ".join(
            str(part)
            for part in collect_command
        )
    )
    print()

    print("Validation command:")
    print(
        " ".join(
            str(part)
            for part in validate_command
        )
    )
    print()

    if dry_run:
        print(
            "Dry run completed. "
            "Candidate validation was not executed."
        )
        return

    validation_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    collect_result = subprocess.run(
        collect_command,
        check=False,
    )

    if collect_result.returncode != 0:
        raise ValidationError(
            "Candidate collection failed with "
            f"exit code {collect_result.returncode}."
        )

    validate_result = subprocess.run(
        validate_command,
        check=False,
    )

    if validate_result.returncode != 0:
        raise ValidationError(
            "Candidate validation failed with "
            f"exit code {validate_result.returncode}."
        )

    print()
    print("Candidate validation completed successfully.")
    print(f"Results: {results_csv}")
    print(f"Build input: {commits_csv}")