#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
OUTPUT_FILE="full_factorial_all.xlsx"

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
  local use_cut3="$2"
  local use_cardinality="$3"
  local preprocess_mode="$4"

  local -a cmd=(
    "$PYTHON_BIN"
    "lecture_hall_experiment.py"
    "--source" "itc2019"
    "--itc-instance" "$instance"
    "--output" "$OUTPUT_FILE"
    "--compatibility-preprocess" "$preprocess_mode"
    "--quiet"
  )

  local cut_label="default"
  if [[ "$use_cut3" == "1" ]]; then
    cmd+=("--cuts" "3")
    cut_label="cuts3"
  fi

  local cardinality_label="no-cardinality"
  if [[ "$use_cardinality" == "1" ]]; then
    cmd+=("--cardinality")
    cardinality_label="cardinality"
  fi

  echo "===================================================================="
  echo "Instance: $instance | $cut_label | $cardinality_label | preprocess=$preprocess_mode"
  echo "===================================================================="
  "${cmd[@]}"
}

for instance in "${INSTANCES[@]}"; do
  for use_cut3 in 0 1; do
    for use_cardinality in 0 1; do
      for preprocess_mode in none light; do
        run_case "$instance" "$use_cut3" "$use_cardinality" "$preprocess_mode"
      done
    done
  done
done

echo
echo "Full factorial experiment completed."
echo "Results written to: $OUTPUT_FILE"
