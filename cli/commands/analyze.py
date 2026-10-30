import subprocess
import sys
from pathlib import Path

from cli.config import load_config
from cli.repository import prepare_repository


class AnalysisError(Exception):
    pass


def run_analysis(
    config_path: str | Path,
    dry_run: bool = False,
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

    results_root = Path(paths["mining_results"])
    repo_results = results_root / repo_path.name

    if not repo_results.is_dir():
        raise AnalysisError(
            f"Mining results not found: {repo_results}"
        )

    smells = analysis["smells"]

    if not smells:
        raise AnalysisError(
            "No smells were selected in analysis.smells."
        )

    command = [
        sys.executable,
        "-m",
        "mining.analyze_results",
        "--repo",
        str(repo_path),
        "--results-root",
        str(results_root),
        "--branch",
        f"refs/heads/{repository['branch']}",
        "--smells",
        *smells,
    ]

    print()
    print("RAVen candidate analysis")
    print("=" * 60)
    print(f"Repository:  {repository['url']}")
    print(f"Local path:  {repo_path}")
    print(f"Branch:      {repository['branch']}")
    print(f"Results:     {repo_results}")
    print(f"Smells:      {', '.join(smells)}")
    print("=" * 60)
    print()

    print("Command:")
    print(" ".join(str(part) for part in command))
    print()

    if dry_run:
        print("Dry run completed. Analysis was not executed.")
        return

    result = subprocess.run(
        command,
        check=False,
    )

    if result.returncode != 0:
        raise AnalysisError(
            f"Candidate analysis failed with exit code "
            f"{result.returncode}."
        )

    print()
    print("Candidate analysis completed successfully.")
    print(
        f"Results: {repo_results / 'candidates'}"
    )