from pathlib import Path
from urllib.parse import urlparse
import subprocess


class RepositoryError(Exception):
    pass


def run_git(args, cwd=None, check=True):
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )

    if check and result.returncode != 0:
        raise RepositoryError(
            f"Git command failed:\n"
            f"git {' '.join(args)}\n\n"
            f"{result.stderr.strip()}"
        )

    return result


def normalize_git_url(url: str) -> str:
    url = url.strip().rstrip("/")

    if url.endswith(".git"):
        url = url[:-4]

    return url.casefold()


def repository_name_from_url(url: str) -> str:
    parsed = urlparse(url)

    path = parsed.path.rstrip("/")

    if not path:
        raise RepositoryError(
            f"Could not determine repository name from URL: {url}"
        )

    name = path.split("/")[-1]

    if name.endswith(".git"):
        name = name[:-4]

    if not name:
        raise RepositoryError(
            f"Could not determine repository name from URL: {url}"
        )

    return name


def verify_origin(repo_path: Path, expected_url: str) -> None:
    result = run_git(
        ["remote", "get-url", "origin"],
        cwd=repo_path,
    )

    actual_url = result.stdout.strip()

    if normalize_git_url(actual_url) != normalize_git_url(
        expected_url
    ):
        raise RepositoryError(
            "Existing repository has a different origin.\n"
            f"Path:     {repo_path}\n"
            f"Expected: {expected_url}\n"
            f"Actual:   {actual_url}"
        )


def verify_branch(repo_path: Path, branch: str) -> None:
    result = run_git(
        [
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/remotes/origin/{branch}",
        ],
        cwd=repo_path,
        check=False,
    )

    if result.returncode == 0:
        return

    print(
        f"Branch '{branch}' not found locally. "
        "Fetching origin..."
    )

    run_git(
        ["fetch", "origin"],
        cwd=repo_path,
    )

    result = run_git(
        [
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/remotes/origin/{branch}",
        ],
        cwd=repo_path,
        check=False,
    )

    if result.returncode != 0:
        raise RepositoryError(
            f"Branch '{branch}' was not found in repository "
            f"{repo_path}"
        )


def prepare_repository(
    url: str,
    branch: str,
    repositories_root: str | Path,
) -> Path:
    repositories_root = Path(repositories_root)
    repositories_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    repository_name = repository_name_from_url(url)
    repo_path = repositories_root / repository_name

    if not repo_path.exists():
        print(f"Cloning repository: {url}")
        print(f"Destination: {repo_path}")

        run_git(
            [
                "clone",
                url,
                str(repo_path),
            ]
        )

    elif not (repo_path / ".git").exists():
        raise RepositoryError(
            f"Repository path exists but is not a Git repository: "
            f"{repo_path}"
        )

    else:
        print(f"Using existing repository: {repo_path}")

    verify_origin(
        repo_path,
        url,
    )

    verify_branch(
        repo_path,
        branch,
    )

    return repo_path