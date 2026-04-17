#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# Usage: ./run_relaxations_factorial.sh <time_limit_seconds>
# Runs ROOT model for all 6 instances:
# - 5 ITC2019 instances
# - 1 Lancaster bridge instance (across all 5 weekdays)
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
OUTPUT_FILE="relaxations_factorial_${TIME_LIMIT}s.xlsx"
LANCS_INSTANCE_PATH="${LANCS_INSTANCE_PATH:-ITC2019/lancs-yr23.xml}"

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
  local source_type="$1"
  local instance="$2"
  local day_opt="$3"
  local use_cut3="$4"
  local use_cardinality="$5"
  local preprocess_mode="$6"
  local model_type="$7"

  local -a cmd=(
    "$PYTHON_BIN"
    "lecture_hall_experiment.py"
    "--source" "$source_type"
    "--itc-instance" "$instance"
    "--output" "$OUTPUT_FILE"
    "--compatibility-preprocess" "$preprocess_mode"
    "--model" "$model_type"
    "--time-limit" "$TIME_LIMIT"
  )

  if [[ -n "$day_opt" ]]; then
    cmd+=("--itc-day" "$day_opt")
  fi

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
  echo "Instance: $instance | day=${day_opt:-auto} | Model: $model_type | $cut_label | $cardinality_label | preprocess=$preprocess_mode | time_limit=${TIME_LIMIT}s"
  echo "===================================================================="
  "${cmd[@]}"
}

# The 5 ITC2019 instances
ITC_INSTANCES=(
  "pu-proj-fal19"
  "agh-fal17"
  "muni-pdfx-fal17"
  "pu-d9-fal19"
  "muni-pdf-spr16c"
)

for model_type in ROOT; do
  for use_cut3 in 0 1; do
    for use_cardinality in 0 1; do
      for preprocess_mode in none light; do

        # 1-5: ITC2019 instances
        for instance in "${ITC_INSTANCES[@]}"; do
          run_case "itc2019" "$instance" "" "$use_cut3" "$use_cardinality" "$preprocess_mode" "$model_type"
        done

        # 6: Lancaster instance (over 5 weekdays)
        for day_index in 0 1 2 3 4; do
          run_case "lancs_yr23" "$LANCS_INSTANCE_PATH" "$day_index" "$use_cut3" "$use_cardinality" "$preprocess_mode" "$model_type"
        done

      done
    done
  done
done

echo
echo "Relaxations full factorial experiment completed for all six instances."
echo "Results written to: $OUTPUT_FILE"
