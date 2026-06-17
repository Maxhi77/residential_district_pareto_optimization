#!/usr/bin/env bash
set -euo pipefail

# Shared settings
REMOTE_EXAMPLE_DIR="${REMOTE_EXAMPLE_DIR:-/home/mh/thermal_building_clone/src/oemof/thermal_building_model/examples/11_further_examples}"
PY_SCRIPT="18_centralized_supply_multiple_buildings_multiple_heat_carrier_levels_linux.py"
CONDA_SH="${CONDA_SH:-/opt/mambaforge/install_dir/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-district_opt}"
REMOTE_LOG_DIR="${REMOTE_LOG_DIR:-/home/mh}"

SCENARIO_MODE="capex_min_only"   # all | capex_min_only
SOLVER_THREADS=3
TEMPS="50,80"
UEU_CASES="processed_bds_in_DENI03403000SEC5658:1146.15"

# Per-host settings (same length required)
HOSTS=(idefix obelix verleihnix methusalix gutemine falbala)
WORKERS_PER_HOST=(30 40 16 60 110 140)

# Set k-lists per host (adjust as needed; defaults are directly runnable)
SFH_K_PER_HOST=(
  "1,2,4"
  "6,8,10"
  "reference,10,14,18"
  "reference,1,2,4,6,8,10,14,18"
  "reference,1,2,4,6,8,10,14,18"
  "reference,1,2,4,6,8,10,14,18"
)
MFH_K_PER_HOST=(
  "1,2"
  "1,2"
  "1,2"
  "3"
  "4,5"
  "6,reference"
)

if [[ ${#HOSTS[@]} -ne ${#WORKERS_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#SFH_K_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#MFH_K_PER_HOST[@]} ]]; then
  echo "HOSTS, WORKERS_PER_HOST, SFH_K_PER_HOST and MFH_K_PER_HOST must have equal length."
  exit 1
fi

for idx in "${!HOSTS[@]}"; do
  host="${HOSTS[$idx]}"
  workers="${WORKERS_PER_HOST[$idx]}"
  sfh_k="${SFH_K_PER_HOST[$idx]}"
  mfh_k="${MFH_K_PER_HOST[$idx]}"
  out_log="${REMOTE_LOG_DIR}/cen18_${host}.out"
  err_log="${REMOTE_LOG_DIR}/cen18_${host}_error.log"

  remote_cmd=$(
    cat <<EOF
set -e
cd "$REMOTE_EXAMPLE_DIR"
source "$CONDA_SH"
conda activate "$CONDA_ENV"
nohup python "$PY_SCRIPT" \
  --host-name "$host" \
  --workers "$workers" \
  --solver-threads "$SOLVER_THREADS" \
  --scenario-mode "$SCENARIO_MODE" \
  --temps "$TEMPS" \
  --sfh-k "$sfh_k" \
  --mfh-k "$mfh_k" \
  --ueu-cases "$UEU_CASES" \
  > "$out_log" 2> "$err_log" &
echo Started PID: \$!
EOF
  )

  echo "Launching on $host: workers=$workers sfh_k=$sfh_k mfh_k=$mfh_k"
  ssh "$host" "bash -lc '$remote_cmd'"
done

echo "All remote runs submitted."
