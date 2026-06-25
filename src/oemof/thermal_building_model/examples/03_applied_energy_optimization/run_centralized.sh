#!/usr/bin/env bash
set -euo pipefail

# Local centralized Gurobi run on the current host.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE_DIR="${EXAMPLE_DIR:-$SCRIPT_DIR}"
PY_SCRIPT="${PY_SCRIPT:-centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py}"

# Leave empty to use the currently active environment.
CONDA_SH="${CONDA_SH:-}"
CONDA_ENV="${CONDA_ENV:-final_umgebung}"

LOG_DIR="${LOG_DIR:-$EXAMPLE_DIR}"
RESULT_STORAGE_ROOT="${RESULT_STORAGE_ROOT:-default}"

SCENARIO_MODE="${SCENARIO_MODE:-capex_max_only}"   # all | capex_min_only | capex_max_only
SOLVER="${SOLVER:-gurobi}"
SOLVER_THREADS="${SOLVER_THREADS:-3}"
TEMPS="${TEMPS:-50,80}"
UEU_CASES="${UEU_CASES:-processed_bds_in_DENI03403000SEC5101:2723.29}"
CO2_FACTORS="${CO2_FACTORS:-1,0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.55,0.5,0.45,0.4,0.35,0.3,0.25,0.2,0.15,0.1,0.05,0.01,-0.01,-0.05,-0.1,-0.2}"

# Requested k values (use "reference", not "ref").
SFH_K="${SFH_K:-1,2,reference}"
MFH_K="${MFH_K:-1,2,3,4,6,10,14,18,reference}"

mkdir -p "$LOG_DIR"

out_log="${LOG_DIR}/centralized_local.out"
err_log="${LOG_DIR}/centralized_local_error.log"

cd "$EXAMPLE_DIR"

if [[ -n "$CONDA_SH" && -f "$CONDA_SH" ]]; then
  source "$CONDA_SH"
  conda activate "$CONDA_ENV"
else
  echo "CONDA_SH not found, using current env: ${CONDA_DEFAULT_ENV:-unknown}"
fi

echo "Launching local centralized run: solver=$SOLVER solver_threads=$SOLVER_THREADS"
echo "Workers and job count are NOT set here; Python auto-selects workers and runs all selected jobs."
echo "Logs:"
echo "  stdout: $out_log"
echo "  stderr: $err_log"

nohup python "$PY_SCRIPT" \
  --host-name "$(hostname)" \
  --solver "$SOLVER" \
  --solver-threads "$SOLVER_THREADS" \
  --scenario-mode "$SCENARIO_MODE" \
  --temps "$TEMPS" \
  --sfh-k "$SFH_K" \
  --mfh-k "$MFH_K" \
  --ueu-cases "$UEU_CASES" \
  --co2-factors "$CO2_FACTORS" \
  --result-storage-root "$RESULT_STORAGE_ROOT" \
  > "$out_log" 2> "$err_log" &

echo "Started PID: $!"
