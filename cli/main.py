from pathlib import Path

import typer

from cli.commands.analyze import (
    AnalysisError,
    run_analysis,
)
from cli.commands.discover import (
    DiscoveryError,
    run_discovery,
)
from cli.commands.mine import (
    MiningError,
    run_mining,
)
from cli.commands.reproduce import (
    ReproductionError,
    run_reproduction,
)
from cli.commands.status import (
    run_status,
)
from cli.commands.validate import (
    ValidationError,
    run_validation,
)
from cli.config import ConfigError
from cli.repository import (
    RepositoryError,
)


app = typer.Typer(
    name="raven",
    help=(
        "RAVen - Real-world Automated "
        "Validation of Refactorings"
    ),
    no_args_is_help=True,
)


@app.callback()
def main():
    """
    RAVen - Real-world Automated
    Validation of Refactorings.
    """
    pass


@app.command()
def mine(
    config: Path = typer.Option(
        Path("config/raven.yml"),
        "--config",
        "-c",
        help=(
            "Path to the RAVen "
            "configuration file."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Show the mining command "
            "without executing it."
        ),
    ),
):
    """
    Run historical static analysis using DesigniteJava.
    """

    try:
        run_mining(
            config_path=config,
            dry_run=dry_run,
        )

    except (
        ConfigError,
        RepositoryError,
        MiningError,
    ) as error:
        typer.echo(
            f"ERROR: {error}",
            err=True,
        )

        raise typer.Exit(
            code=1
        )


@app.command()
def analyze(
    config: Path = typer.Option(
        Path("config/raven.yml"),
        "--config",
        "-c",
        help=(
            "Path to the RAVen "
            "configuration file."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Show the analysis command "
            "without executing it."
        ),
    ),
):
    """
    Identify candidate smell-removal transitions.
    """

    try:
        run_analysis(
            config_path=config,
            dry_run=dry_run,
        )

    except (
        ConfigError,
        RepositoryError,
        AnalysisError,
    ) as error:
        typer.echo(
            f"ERROR: {error}",
            err=True,
        )

        raise typer.Exit(
            code=1
        )


@app.command()
def validate(
    config: Path = typer.Option(
        Path("config/raven.yml"),
        "--config",
        "-c",
        help=(
            "Path to the RAVen "
            "configuration file."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Show validation commands "
            "without executing them."
        ),
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help=(
            "Reuse previously completed "
            "validation results."
        ),
    ),
):
    """
    Validate candidate smell-removal transitions.
    """

    try:
        run_validation(
            config_path=config,
            dry_run=dry_run,
            resume=resume,
        )

    except (
        ConfigError,
        RepositoryError,
        ValidationError,
    ) as error:
        typer.echo(
            f"ERROR: {error}",
            err=True,
        )

        raise typer.Exit(
            code=1
        )


@app.command()
def discover(
    config: Path = typer.Option(
        Path("config/raven.yml"),
        "--config",
        "-c",
        help=(
            "Path to the RAVen "
            "configuration file."
        ),
    ),
    restart: bool = typer.Option(
        False,
        "--restart",
        help=(
            "Restart discovery from the "
            "beginning instead of reusing "
            "existing results."
        ),
    ),
):
    """
    Run mining, analysis, and validation in the background.
    """

    try:
        job = run_discovery(
            config_path=config,
            restart=restart,
        )

    except (
        ConfigError,
        RepositoryError,
        DiscoveryError,
    ) as error:
        typer.echo(
            f"ERROR: {error}",
            err=True,
        )

        raise typer.Exit(
            code=1
        )

    typer.echo()
    typer.echo(
        "Discovery job started."
    )
    typer.echo()
    typer.echo(
        f"Repository: {job['repository']}"
    )
    typer.echo(
        f"Job:        {job['id']}"
    )
    typer.echo(
        f"Status:     {job['status']}"
    )
    typer.echo(
        f"Log:        {job['log']}"
    )


@app.command()
def reproduce(
    config: Path = typer.Option(
        Path("config/raven.yml"),
        "--config",
        "-c",
        help=(
            "Path to the RAVen "
            "configuration file."
        ),
    ),
    commit: str | None = typer.Option(
        None,
        "--commit",
        help=(
            "Validated historical commit to reproduce. "
            "A unique commit prefix is also accepted. "
            "If omitted, RAVen shows an interactive list."
        ),
    ),
):
    """
    Reproduce one validated historical commit in the background.
    """

    try:
        job = run_reproduction(
            config_path=config,
            commit=commit,
        )

    except (
        ConfigError,
        RepositoryError,
        ReproductionError,
    ) as error:
        typer.echo(
            f"ERROR: {error}",
            err=True,
        )

        raise typer.Exit(
            code=1
        )

    typer.echo()
    typer.echo(
        "Reproduction job started."
    )
    typer.echo()
    typer.echo(
        f"Repository: {job['repository']}"
    )
    typer.echo(
        f"Commit:     {job['target']}"
    )
    typer.echo(
        f"Job:        {job['id']}"
    )
    typer.echo(
        f"Status:     {job['status']}"
    )
    typer.echo(
        f"Log:        {job['log']}"
    )


@app.command()
def status(
    jobs_root: Path = typer.Option(
        Path("jobs"),
        "--jobs-root",
        help=(
            "Directory containing RAVen "
            "job metadata."
        ),
    ),
):
    """
    Show the status of background RAVen jobs.
    """

    run_status(
        jobs_root=jobs_root,
    )


if __name__ == "__main__":
    app()