#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
from pathlib import Path


PROMPT_FILE = "CODEX_PROMPT.md"


def run(cmd, cwd=None):
    print("+", " ".join(str(x) for x in cmd), flush=True)
    subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        check=True,
    )


def capture(cmd, cwd=None):
    result = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def normalize_git_url(url):
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def repository_has_changes(repository_dir):
    result = subprocess.run(
        ["git", "-C", str(repository_dir), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def tracked_repository_is_clean(repository_dir):
    unstaged = subprocess.run(
        ["git", "-C", str(repository_dir), "diff", "--quiet"],
        check=False,
    )
    staged = subprocess.run(
        ["git", "-C", str(repository_dir), "diff", "--cached", "--quiet"],
        check=False,
    )
    return unstaged.returncode == 0 and staged.returncode == 0


def commit_exists(repository_dir, commit):
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_dir),
            "cat-file",
            "-e",
            f"{commit}^{{commit}}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def append_final_validation(manifest_path, *, passed, log_path):
    with manifest_path.open("a", encoding="utf-8") as manifest:
        manifest.write("\n")
        manifest.write("=== EXTERNAL FINAL VALIDATION ===\n")
        manifest.write(
            f"offline reproduction result: {'PASS' if passed else 'FAIL'}\n"
        )
        manifest.write(f"validation log: {log_path.name}\n")
        manifest.write("validation performed outside Codex sandbox: yes\n")


def prepare_repository(repository_dir, repo_url, requested_commit):
    """Create or reuse the shared repository checkout without discarding changes."""
    if not repository_dir.exists():
        repository_dir.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", repo_url, repository_dir])

    elif not (repository_dir / ".git").exists():
        raise RuntimeError(
            "Repository directory exists but is not a Git repository:\n"
            f"{repository_dir}"
        )

    origin_url = capture(
        ["git", "-C", repository_dir, "remote", "get-url", "origin"]
    )

    if normalize_git_url(origin_url) != normalize_git_url(repo_url):
        raise RuntimeError(
            "Existing shared repository has a different origin.\n"
            f"Expected: {repo_url}\n"
            f"Actual:   {origin_url}"
        )

    if repository_has_changes(repository_dir):
        raise RuntimeError(
            "The shared repository contains working-tree changes.\n\n"
            "repro.py will not change commits while modifications exist.\n\n"
            f"Repository:\n{repository_dir}"
        )

    if not commit_exists(repository_dir, requested_commit):
        print("\nTarget commit is not available locally. Fetching origin.\n")
        run(["git", "-C", repository_dir, "fetch", "origin"])

    if not commit_exists(repository_dir, requested_commit):
        raise RuntimeError(
            "Target commit was not found after fetching the repository:\n"
            f"{requested_commit}"
        )

    full_commit = capture(
        [
            "git",
            "-C",
            repository_dir,
            "rev-parse",
            f"{requested_commit}^{{commit}}",
        ]
    )

    run(
        [
            "git",
            "-C",
            repository_dir,
            "checkout",
            "--detach",
            full_commit,
        ]
    )

    actual_commit = capture(
        ["git", "-C", repository_dir, "rev-parse", "HEAD"]
    )

    if actual_commit != full_commit:
        raise RuntimeError(
            "Checked-out commit does not match target.\n"
            f"Expected: {full_commit}\n"
            f"Actual:   {actual_commit}"
        )

    return full_commit


def render_prompt(template_path, *, full_commit, short_commit):
    text = template_path.read_text(encoding="utf-8")
    return (
        text.replace("{{FULL_COMMIT}}", full_commit)
        .replace("{{SHORT_COMMIT}}", short_commit)
    )


def clean_validation_environment():
    """Remove ambient Java/Maven settings from authoritative validation."""
    env = os.environ.copy()

    for name in (
        "JAVA_HOME",
        "MAVEN_HOME",
        "M2_HOME",
        "MAVEN_OPTS",
        "MAVEN_ARGS",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
    ):
        env.pop(name, None)

    return env


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create an offline reproducible Maven environment "
            "for one historical Java commit."
        )
    )

    parser.add_argument("--repo", required=True, help="Git repository URL")
    parser.add_argument(
        "--commit",
        required=True,
        help="Historical Git commit",
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    prompt_source = project_root / PROMPT_FILE
    agents_source = project_root / "AGENTS.md"

    if not prompt_source.is_file():
        raise RuntimeError(f"{PROMPT_FILE} not found:\n{prompt_source}")

    if not agents_source.is_file():
        raise RuntimeError(f"AGENTS.md not found:\n{agents_source}")

    benchmark_dir = project_root / "benchmark"
    toolchains_dir = benchmark_dir / "toolchains"
    java_toolchains_dir = toolchains_dir / "java"
    maven_toolchains_dir = toolchains_dir / "maven"
    repositories_dir = benchmark_dir / "repositories"

    java_toolchains_dir.mkdir(parents=True, exist_ok=True)
    maven_toolchains_dir.mkdir(parents=True, exist_ok=True)
    repositories_dir.mkdir(parents=True, exist_ok=True)

    repo_name = Path(args.repo.rstrip("/")).stem

    repository_environment_dir = repositories_dir / repo_name
    repository_dir = repository_environment_dir / "repository"
    commits_dir = repository_environment_dir / "commits"

    repository_environment_dir.mkdir(parents=True, exist_ok=True)
    commits_dir.mkdir(parents=True, exist_ok=True)

    full_commit = prepare_repository(
        repository_dir,
        args.repo,
        args.commit,
    )

    short_commit = full_commit[:12]
    commit_dir = commits_dir / short_commit

    if commit_dir.exists() and any(commit_dir.iterdir()):
        raise RuntimeError(
            "Commit environment already exists and is not empty:\n"
            f"{commit_dir}\n\n"
            "Move or remove it before recreating this environment."
        )

    m2_dir = commit_dir / "m2"
    trace_path = commit_dir / "codex_trace.log"
    validation_log = commit_dir / "validation.log"
    manifest_path = commit_dir / "manifest.txt"
    reproduce_path = commit_dir / "reproduce.sh"
    settings_path = commit_dir / "settings.xml"

    commit_dir.mkdir(parents=True, exist_ok=True)
    m2_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(agents_source, commit_dir / "AGENTS.md")

    prompt = render_prompt(
        prompt_source,
        full_commit=full_commit,
        short_commit=short_commit,
    )

    print()
    print("Starting Codex investigation.")
    print(f"Trace: {trace_path}")
    print()

    with trace_path.open(
        "w",
        encoding="utf-8",
        errors="replace",
    ) as trace:
        codex_result = subprocess.run(
            [
                "codex",
                "exec",
                "--approve-for-me",
                prompt,
            ],
            cwd=str(repository_environment_dir),
            stdout=trace,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    if codex_result.returncode != 0:
        raise RuntimeError(
            "Codex investigation failed with "
            f"exit code {codex_result.returncode}.\n"
            f"See trace:\n{trace_path}"
        )

    expected = [
        repository_dir,
        m2_dir,
        manifest_path,
        reproduce_path,
        settings_path,
        trace_path,
    ]

    missing = [path for path in expected if not path.exists()]

    if missing:
        print("\nCodex finished, but the reproduction environment is incomplete.")
        print("Missing:")
        for path in missing:
            print(f"  - {path}")
        print(f"\nSee trace: {trace_path}")
        raise SystemExit(1)

    if not tracked_repository_is_clean(repository_dir):
        raise RuntimeError(
            "Codex modified tracked files in the historical repository.\n"
            "The reproduction environment is invalid.\n"
            f"Repository:\n{repository_dir}"
        )

    reproduce_path.chmod(reproduce_path.stat().st_mode | 0o111)

    print()
    print("Running final offline validation outside Codex sandbox.")
    print(f"Command: {reproduce_path}")
    print(f"Log:     {validation_log}")
    print()

    validation_env = clean_validation_environment()

    with validation_log.open(
        "w",
        encoding="utf-8",
        errors="replace",
    ) as validation:
        validation_result = subprocess.run(
            [str(reproduce_path)],
            cwd=str(commit_dir),
            stdout=validation,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            env=validation_env,
        )

    final_pass = validation_result.returncode == 0

    if not tracked_repository_is_clean(repository_dir):
        raise RuntimeError(
            "Tracked project files changed during final validation.\n"
            "The reproduction environment is invalid.\n"
            f"See log:\n{validation_log}"
        )

    append_final_validation(
        manifest_path,
        passed=final_pass,
        log_path=validation_log,
    )

    print()

    if not final_pass:
        print("Reproduction environment FAILED final validation.")
        print()
        print("Environment preserved for diagnosis:")
        print(commit_dir)
        print()
        print("Validation log:")
        print(validation_log)
        print()
        print("Codex trace:")
        print(trace_path)
        raise SystemExit(1)

    print("Reproduction environment PASSED final validation.")
    print()
    print(f"Repository:  {repository_dir}")
    print(f"Environment: {commit_dir}")
    print(f"Manifest:    {manifest_path}")
    print(f"Trace:       {trace_path}")
    print(f"Validation:  {validation_log}")


if __name__ == "__main__":
    try:
        main()
    except (
        FileNotFoundError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        print()
        print(f"ERROR: {exc}")
        raise SystemExit(1)
