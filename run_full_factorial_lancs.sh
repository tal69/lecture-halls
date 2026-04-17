#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# Usage: ./run_full_factorial_lancs.sh <time_limit_seconds>
# Runs all weekdays (0..4) of the Lancaster 2023 derived instances.
# For each selected day, lecture_hall_experiment.py loads that day from:
# - the most loaded week of term 1, and
# - the most loaded week of term 2.
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <time_limit_seconds>" >&2
  exit 1
fi

TIME_LIMIT="$1"
if ! [[ "$TIME_LIMIT" =~ ^[1-9][0-9]*$ ]]; then
  echo "Error: time_limit_seconds must be a positive integer, got '$TIME_LIMIT'." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python}"
OUTPUT_FILE="lancs_yr23_full_factorial_${TIME_LIMIT}s.xlsx"
INSTANCE_PATH="${INSTANCE_PATH:-ITC2019/lancs-yr23.xml}"

# Weekdays only. The Lancaster data-preparation path auto-selects the most
# loaded week of each term; this loop selects the source day within those weeks.
DAYS=(0 1 2 3 4)

if [[ -f "$OUTPUT_FILE" ]]; then
  if [[ "${OVERWRITE:-0}" == "1" ]]; then
    rm -f "$OUTPUT_FILE"
  else
    echo "Output file '$OUTPUT_FILE' already exists."
    echo "Remove it first, or rerun with OVERWRITE=1."
    exit 1
  fi
fi

run_case() {
  local day_index="$1"
  local use_biclique="$2"
  local use_cardinality="$3"
  local preprocess_mode="$4"

  local -a cmd=(
    "$PYTHON_BIN"
    "lecture_hall_experiment.py"
    "--source" "lancs_yr23"
    "--itc-instance" "$INSTANCE_PATH"
    "--itc-day" "$day_index"
    "--output" "$OUTPUT_FILE"
    "--compatibility-preprocess" "$preprocess_mode"
    "--time-limit" "$TIME_LIMIT"
  )

  local biclique_label="no-biclique"
  if [[ "$use_biclique" == "1" ]]; then
    cmd+=("--biclique")
    biclique_label="biclique"
  fi

  local cardinality_label="no-cardinality"
  if [[ "$use_cardinality" == "1" ]]; then
    cmd+=("--cardinality")
    cardinality_label="cardinality"
  fi

  echo "===================================================================="
  echo "Lancaster day=$day_index | $biclique_label | $cardinality_label | preprocess=$preprocess_mode | time_limit=${TIME_LIMIT}s"
  echo "Source: $INSTANCE_PATH"
  echo "===================================================================="
  "${cmd[@]}"
}

for day_index in "${DAYS[@]}"; do
  for use_biclique in 0 1; do
    for use_cardinality in 0 1; do
      for preprocess_mode in none light; do
        run_case "$day_index" "$use_biclique" "$use_cardinality" "$preprocess_mode"
      done
    done
  done
done

echo
echo "Lancaster full factorial experiment completed."
echo "Results written to: $OUTPUT_FILE"
