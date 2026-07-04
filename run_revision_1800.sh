#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# R1 revision campaign for CAOR-D-26-01017 (Reviewer 1, Comment 1.6a).
# Runs the complete numerical campaign with a 1800-second time limit:
#   1. ITC 2019 full factorial (5 sources x 5 days x 3 formulations x 8 combos)
#   2. Lancaster 2023 full factorial (10 days x 3 formulations x 8 combos)
#   3. Root-relaxation factorial (all 35 instances x 8 combos)
# Each stage writes its own xlsx and its own log file. Stages run sequentially;
# a failed stage aborts the script (set -e), so completed xlsx files are kept.
#
# Usage:            ./run_revision_1800.sh
# Override limit:   TIME_LIMIT=3600 ./run_revision_1800.sh
# ---------------------------------------------------------------------------

TIME_LIMIT="${TIME_LIMIT:-1800}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="logs_revision_${TIME_LIMIT}s_${STAMP}"
mkdir -p "$LOG_DIR"

echo "Time limit: ${TIME_LIMIT}s | Logs: ${LOG_DIR}/"

echo "[1/3] ITC 2019 full factorial ..."
./run_full_factorial_all.sh   "$TIME_LIMIT" 2>&1 | tee "$LOG_DIR/itc_factorial.log"

echo "[2/3] Lancaster 2023 full factorial ..."
./run_full_factorial_lancs.sh "$TIME_LIMIT" 2>&1 | tee "$LOG_DIR/lancs_factorial.log"

echo "[3/3] Root relaxations ..."
./run_relaxations_factorial.sh "$TIME_LIMIT" 2>&1 | tee "$LOG_DIR/relaxations.log"

echo
echo "Revision campaign completed with time limit ${TIME_LIMIT}s."
echo "Outputs: full_factorial_${TIME_LIMIT}s.xlsx, lancs_yr23_full_factorial_${TIME_LIMIT}s.xlsx, relaxations_factorial_${TIME_LIMIT}s.xlsx"
echo "Logs:    ${LOG_DIR}/"
