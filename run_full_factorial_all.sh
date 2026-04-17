#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# Usage: ./run_full_factorial_all.sh <time_limit_seconds>
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
OUTPUT_FILE="full_factorial_${TIME_LIMIT}s.xlsx"

# Five largest ITC2019 instances that satisfy:
# 1. non-trivial room-distance matrix
# 2. student enrolment data present
INSTANCES=(
  "pu-proj-fal19"
  "agh-fal17"
  "muni-pdfx-fal17"
  "pu-d9-fal19"
  "muni-pdf-spr16c"
)

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
  local instance="$1"
  local use_biclique="$2"
  local use_cardinality="$3"
  local preprocess_mode="$4"

  local -a cmd=(
    "$PYTHON_BIN"
    "lecture_hall_experiment.py"
    "--source" "itc2019"
    "--itc-instance" "$instance"
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
  echo "Instance: $instance | $biclique_label | $cardinality_label | preprocess=$preprocess_mode | time_limit=${TIME_LIMIT}s"
  echo "===================================================================="
  "${cmd[@]}"
}

for instance in "${INSTANCES[@]}"; do
  for use_biclique in 0 1; do
    for use_cardinality in 0 1; do
      for preprocess_mode in none light; do
        run_case "$instance" "$use_biclique" "$use_cardinality" "$preprocess_mode"
      done
    done
  done
done

echo
echo "Full factorial experiment completed."
echo "Results written to: $OUTPUT_FILE"
