#!/usr/bin/env python3

import csv
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCHMARK = ROOT / "benchmark"
REPOSITORIES = BENCHMARK / "repositories"
OUTPUT = BENCHMARK / "results" / "results.csv"


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def get_status(manifest: Path) -> str:
    if not manifest.exists():
        return "INCOMPLETE"

    text = manifest.read_text(errors="replace")

    # There may be more than one validation result, e.g. after
    # a documented manual revalidation. The latest result is authoritative.
    results = []

    for line in text.splitlines():
        line = line.strip()

        if line.lower().startswith("offline reproduction result:"):
            value = line.split(":", 1)[1].strip().upper()

            if value.startswith("PASS"):
                results.append("PASS")
            elif value.startswith("FAIL"):
                results.append("FAIL")

    if results:
        return results[-1]

    return "INCOMPLETE"


def resolve_full_commit(repository_dir: Path, short_commit: str) -> str:
    """
    Resolve the commit directory name (normally a 12-character SHA)
    to the full Git commit SHA using the repository checkout.

    If the commit cannot be resolved, keep the directory name so that
    the existing environment is still included in the inventory.
    """
    repo = repository_dir / "repository"

    if not (repo / ".git").exists():
        return short_commit

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            f"{short_commit}^{{commit}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        full_commit = result.stdout.strip()

        if full_commit:
            return full_commit

    return short_commit


def collect_rows():
    rows = []

    if not REPOSITORIES.is_dir():
        return rows

    for repository_dir in sorted(
        REPOSITORIES.iterdir(),
        key=lambda path: path.name.casefold(),
    ):
        if not repository_dir.is_dir():
            continue

        commits_dir = repository_dir / "commits"

        if not commits_dir.is_dir():
            continue

        repository = repository_dir.name

        for env_dir in sorted(
            commits_dir.iterdir(),
            key=lambda path: path.name,
        ):
            if not env_dir.is_dir():
                continue

            short_commit = env_dir.name
            full_commit = resolve_full_commit(
                repository_dir,
                short_commit,
            )

            manifest = env_dir / "manifest.txt"
            validation_log = env_dir / "validation.log"
            codex_trace = env_dir / "codex_trace.log"
            reproduce = env_dir / "reproduce.sh"

            status = get_status(manifest)

            rows.append(
                {
                    "repository": repository,
                    "commit": full_commit,
                    "short_commit": short_commit,
                    "status": status,
                    "manifest": relative(manifest),
                    "validation_log": relative(validation_log),
                    "codex_trace": relative(codex_trace),
                    "reproduce": relative(reproduce),
                }
            )

    return rows


def main():
    rows = collect_rows()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "repository",
        "commit",
        "short_commit",
        "status",
        "manifest",
        "validation_log",
        "codex_trace",
        "reproduce",
    ]

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    pass_count = sum(row["status"] == "PASS" for row in rows)
    fail_count = sum(row["status"] == "FAIL" for row in rows)
    incomplete_count = sum(row["status"] == "INCOMPLETE" for row in rows)

    print(f"Environments found: {len(rows)}")
    print(f"PASS:               {pass_count}")
    print(f"FAIL:               {fail_count}")
    print(f"INCOMPLETE:         {incomplete_count}")
    print(f"Output:              {OUTPUT}")


if __name__ == "__main__":
    main()