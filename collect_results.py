#!/usr/bin/env python3

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMITS_CSV = ROOT / "commits.csv"
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


def main():
    rows = []

    with COMMITS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for entry in reader:
            repository = entry["repository"].strip()
            full_commit = entry["commit"].strip()
            short_commit = full_commit[:12]

            env_dir = (
                REPOSITORIES
                / repository
                / "commits"
                / short_commit
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

    print(f"Wrote {len(rows)} rows to: {OUTPUT}")


if __name__ == "__main__":
    main()