#!/usr/bin/env bash

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
CSV="$ROOT/commits.csv"

BENCHMARK="$ROOT/benchmark"
REPOSITORIES="$BENCHMARK/repositories"
LOG_DIR="$ROOT/log"

mkdir -p "$LOG_DIR"

BATCH_LOG="$LOG_DIR/overnight_$(date +%Y%m%d_%H%M%S).log"

echo "Batch started: $(date)" | tee -a "$BATCH_LOG"
echo | tee -a "$BATCH_LOG"

while IFS=',' read -r repository url commit <&3 \
      || [ -n "${repository:-}${url:-}${commit:-}" ]; do

    # Remove CR from CSV files created/edited on Windows.
    repository="${repository//$'\r'/}"
    url="${url//$'\r'/}"
    commit="${commit//$'\r'/}"

    # Ignore empty lines.
    [ -z "$repository" ] && continue
    [ -z "$url" ] && continue
    [ -z "$commit" ] && continue

    short_commit="${commit:0:12}"

    env_dir="$REPOSITORIES/$repository/commits/$short_commit"
    manifest="$env_dir/manifest.txt"

    echo "============================================================" | tee -a "$BATCH_LOG"
    echo "Repository: $repository" | tee -a "$BATCH_LOG"
    echo "Commit:     $commit" | tee -a "$BATCH_LOG"
    echo "Started:    $(date)" | tee -a "$BATCH_LOG"

    #
    # Already successfully processed.
    #
    if [ -f "$manifest" ] &&
       grep -q "offline reproduction result: PASS" "$manifest"; then

        echo "Status: SKIP - already PASS" | tee -a "$BATCH_LOG"
        echo | tee -a "$BATCH_LOG"
        continue
    fi

    #
    # Preserve an existing incomplete/failed environment.
    #
    if [ -d "$env_dir" ] &&
       [ "$(ls -A "$env_dir" 2>/dev/null)" ]; then

        echo "Status: SKIP - existing non-PASS environment" | tee -a "$BATCH_LOG"
        echo "Path:   $env_dir" | tee -a "$BATCH_LOG"
        echo | tee -a "$BATCH_LOG"
        continue
    fi

    case_log="$LOG_DIR/${repository}_${short_commit}.log"

    echo "Log:        $case_log" | tee -a "$BATCH_LOG"

    #
    # Maximum 90 minutes per commit.
    #
    # stdin is disconnected so repro.py/Codex cannot consume the CSV.
    #
    timeout --kill-after=5m 90m \
        python "$ROOT/repro.py" \
        --repo "$url" \
        --commit "$commit" \
        >"$case_log" 2>&1 \
        </dev/null

    rc=$?

    trace="$env_dir/codex_trace.log"

    if [ -f "$trace" ] &&
    grep -qi "hit your usage limit" "$trace"; then

        echo "Status:    CODEX_USAGE_LIMIT" | tee -a "$BATCH_LOG"
        echo "Exit code: $rc" | tee -a "$BATCH_LOG"
        echo "Finished:  $(date)" | tee -a "$BATCH_LOG"
        echo "Stopping batch because Codex usage limit was reached." \
            | tee -a "$BATCH_LOG"

        break
    fi

    if [ "$rc" -eq 0 ]; then
        status="PASS"

    elif [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
        status="TIMEOUT"

    else
        status="FAIL"
    fi

    echo "Status:    $status" | tee -a "$BATCH_LOG"
    echo "Exit code: $rc" | tee -a "$BATCH_LOG"
    echo "Finished:  $(date)" | tee -a "$BATCH_LOG"
    echo | tee -a "$BATCH_LOG"

done 3< <(tail -n +2 "$CSV")

echo "Batch finished: $(date)" | tee -a "$BATCH_LOG"