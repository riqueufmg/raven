#!/usr/bin/env bash

set -uo pipefail

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CSV="$SCRIPT_DIR/repositories.csv"
RESULTS_DIR="$SCRIPT_DIR/results"
REPOS_DIR="$SCRIPT_DIR/repositories"
LOG_DIR="$SCRIPT_DIR/log"
QUEUE="$SCRIPT_DIR/repos_to_run_sorted.tsv"

DESIGNITE_JAR="$ROOT/tools/DesigniteJava.jar"

# ------------------------------------------------------------
# Arguments
# ------------------------------------------------------------

MAX_REPOS="${1:-20}"
PARALLEL="${2:-2}"
DRY_RUN=false

if [ "${3:-}" = "--dry-run" ]; then
    DRY_RUN=true
elif [ -n "${3:-}" ]; then
    echo "ERROR: unknown argument: $3" >&2
    echo "Usage: $0 [max_repos] [parallel] [--dry-run]" >&2
    exit 2
fi

mkdir -p "$RESULTS_DIR" "$REPOS_DIR" "$LOG_DIR"

if ! [[ "$MAX_REPOS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: max_repos must be a positive integer." >&2
    exit 2
fi

if ! [[ "$PARALLEL" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: parallel must be a positive integer." >&2
    exit 2
fi

if [ ! -f "$CSV" ]; then
    echo "ERROR: repositories CSV not found: $CSV" >&2
    exit 2
fi

if [ ! -f "$DESIGNITE_JAR" ]; then
    echo "ERROR: DesigniteJava.jar not found: $DESIGNITE_JAR" >&2
    exit 2
fi

cd "$ROOT" || exit 2

echo "============================================================"
echo "Designite batch"
echo "============================================================"
echo "RAVen root:       $ROOT"
echo "CSV:              $CSV"
echo "Designite:        $DESIGNITE_JAR"
echo "Max repositories: $MAX_REPOS"
echo "Parallel workers: $PARALLEL"
echo "Dry run:          $DRY_RUN"
echo

echo "============================================================"
echo "Repositories already present in mining/results"
echo "============================================================"

mapfile -t EXISTING_RESULTS < <(
    find "$RESULTS_DIR" \
        -maxdepth 1 \
        -mindepth 1 \
        -type d \
        -printf '%f\n' \
        | sort
)

if [ "${#EXISTING_RESULTS[@]}" -eq 0 ]; then
    echo "  (none)"
else
    for repo in "${EXISTING_RESULTS[@]}"; do
        echo "  $repo"
    done
fi

echo
echo "Already present: ${#EXISTING_RESULTS[@]}"
echo

# ------------------------------------------------------------
# Build execution queue
# ------------------------------------------------------------

python - "$CSV" "$RESULTS_DIR" "$QUEUE" "$MAX_REPOS" <<'PY'
import csv
import json
import sys
from collections import Counter
from pathlib import Path

csv_path = Path(sys.argv[1])
results_dir = Path(sys.argv[2])
queue_path = Path(sys.argv[3])
max_repos = int(sys.argv[4])


def as_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


existing = {
    path.name
    for path in results_dir.iterdir()
    if path.is_dir()
}

with csv_path.open(
    "r",
    encoding="utf-8-sig",
    errors="replace",
    newline="",
) as handle:
    reader = csv.DictReader(handle)

    required = {
        "name",
        "commits",
        "defaultBranch",
        "metrics",
    }

    missing = required.difference(reader.fieldnames or [])
    if missing:
        raise SystemExit(
            f"ERROR: repositories.csv missing columns: {sorted(missing)}"
        )

    rows = list(reader)


basenames = [
    (row.get("name") or "").strip().rsplit("/", 1)[-1]
    for row in rows
]

basename_counts = Counter(basenames)

candidates = []
skipped_existing = 0
invalid = []
collisions = []

for row in rows:
    full_name = (row.get("name") or "").strip()
    branch = (row.get("defaultBranch") or "").strip()
    commits = as_int(row.get("commits"))

    if not full_name or "/" not in full_name:
        invalid.append((full_name or "<empty>", "invalid name"))
        continue

    owner, basename = full_name.split("/", 1)

    if basename_counts[basename] > 1:
        directory = f"{owner}__{basename}"
        collisions.append((full_name, directory))
    else:
        directory = basename

    if directory in existing:
        skipped_existing += 1
        continue

    # Backward compatibility with results generated before
    # repository-name collision handling was introduced.
    if basename_counts[basename] > 1 and basename in existing:
        skipped_existing += 1
        continue

    if not branch:
        invalid.append((full_name, "missing defaultBranch"))
        continue

    try:
        metrics = json.loads(
            (row.get("metrics") or "").strip()
        )
    except json.JSONDecodeError:
        invalid.append((full_name, "invalid metrics JSON"))
        continue

    java_loc = 0

    if isinstance(metrics, list):
        for metric in metrics:
            if (
                isinstance(metric, dict)
                and str(
                    metric.get("language", "")
                ).strip().casefold() == "java"
            ):
                java_loc = as_int(
                    metric.get("codeLines")
                )
                break

    if java_loc <= 0:
        invalid.append(
            (full_name, "Java codeLines not found")
        )
        continue

    cost = commits * java_loc

    candidates.append(
        {
            "directory": directory,
            "full_name": full_name,
            "url": f"https://github.com/{full_name}.git",
            "branch": branch,
            "commits": commits,
            "java_loc": java_loc,
            "cost": cost,
        }
    )


candidates.sort(
    key=lambda row: (
        row["cost"],
        row["commits"],
        row["java_loc"],
        row["full_name"].casefold(),
    )
)

selected = candidates[:max_repos]

with queue_path.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    for row in selected:
        handle.write(
            "\t".join(
                [
                    row["directory"],
                    row["full_name"],
                    row["url"],
                    row["branch"],
                    str(row["commits"]),
                    str(row["java_loc"]),
                    str(row["cost"]),
                ]
            )
            + "\n"
        )


print(
    f"Eligible repositories in CSV: {len(rows)}"
)
print(
    f"Skipped because results exist: {skipped_existing}"
)
print(
    f"Pending after filtering:        {len(candidates)}"
)
print(
    f"Selected for this batch:        {len(selected)}"
)

if collisions:
    print()
    print("Repository-name collisions detected:")
    for full_name, directory in sorted(
        set(collisions)
    ):
        print(f"  {full_name} -> {directory}")

if invalid:
    print()
    print(
        "Repositories excluded because required "
        f"data is missing: {len(invalid)}"
    )

    for name, reason in invalid:
        print(f"  {name}: {reason}")
PY

# ------------------------------------------------------------
# Show execution queue
# ------------------------------------------------------------

echo
echo "============================================================"
echo "Execution queue"
echo "Ordered by commits x Java_LOC"
echo "============================================================"

printf "%-4s %-32s %12s %12s %18s\n" \
    "#" "repository" "commits" "java_loc" "cost"

i=0

while IFS=$'\t' read -r \
    directory full_name url branch commits java_loc cost
do
    [ -n "${directory:-}" ] || continue

    i=$((i + 1))

    printf "%-4d %-32s %12d %12d %18d\n" \
        "$i" \
        "$full_name" \
        "$commits" \
        "$java_loc" \
        "$cost"

done < "$QUEUE"

echo
echo "Queue file: $QUEUE"
echo

if [ "$i" -eq 0 ]; then
    echo "Nothing to run."
    exit 0
fi

# ------------------------------------------------------------
# Dry run
# ------------------------------------------------------------

if [ "$DRY_RUN" = true ]; then
    echo "============================================================"
    echo "Dry run complete."
    echo "No repositories were cloned or analyzed."
    echo "============================================================"
    exit 0
fi

# ------------------------------------------------------------
# Execute one repository
# ------------------------------------------------------------

run_repo() {
    directory="$1"
    full_name="$2"
    url="$3"
    branch="$4"

    repo_path="$REPOS_DIR/$directory"
    result_path="$RESULTS_DIR/$directory"
    log_file="$LOG_DIR/$directory.log"

    if [ -d "$result_path" ]; then
        echo "[SKIP] $full_name: results already exist"
        return 0
    fi

    echo
    echo "============================================================"
    echo "[START] $full_name"
    echo "Directory: $directory"
    echo "Branch:    $branch"
    echo "Started:   $(date)"
    echo "Log:       $log_file"
    echo "============================================================"

    if [ ! -d "$repo_path/.git" ]; then
        echo "[CLONE] $full_name"

        if ! git clone \
            "$url" \
            "$repo_path" \
            >>"$log_file" 2>&1
        then
            echo "[FAIL] $full_name: clone failed"
            return 1
        fi
    else
        echo "[REPO] using existing clone: $repo_path"
    fi

    python -m mining.search_candidates \
        --repo "$repo_path" \
        --date 07-31-2021 \
        --smell "Insufficient Modularization" \
        --designite-jar "$DESIGNITE_JAR" \
        --output "$result_path" \
        --branch "refs/heads/$branch" \
        --regular \
        --overwrite \
        >>"$log_file" 2>&1

    rc=$?

    if [ "$rc" -eq 0 ]; then
        echo "[DONE] $full_name - $(date)"
    else
        echo "[FAIL] $full_name - exit=$rc - $(date)"
    fi

    return "$rc"
}


export -f run_repo

export ROOT
export RESULTS_DIR
export REPOS_DIR
export LOG_DIR
export DESIGNITE_JAR

# ------------------------------------------------------------
# Parallel execution
# ------------------------------------------------------------

echo "Starting batch with $PARALLEL parallel worker(s)..."
echo

set +e

cut -f1-4 "$QUEUE" \
    | xargs -r \
        -P "$PARALLEL" \
        -n 4 \
        bash -c \
        'run_repo "$1" "$2" "$3" "$4"' _

xargs_rc=$?

set -e

echo
echo "============================================================"
echo "Batch finished: $(date)"
echo "xargs exit code: $xargs_rc"
echo "============================================================"

# xargs returns 123 when at least one child command exits 1-125.
# Individual repository failures are already reported and should not
# invalidate successful repositories from the same batch.
if [ "$xargs_rc" -eq 0 ] || [ "$xargs_rc" -eq 123 ]; then
    exit 0
fi

exit "$xargs_rc"