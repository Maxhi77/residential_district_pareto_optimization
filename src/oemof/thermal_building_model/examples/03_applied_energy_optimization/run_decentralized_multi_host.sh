#!/usr/bin/env bash
set -uo pipefail

# Shared settings for distributed decentralized publication runs.
REMOTE_EXAMPLE_DIR="${REMOTE_EXAMPLE_DIR:-/home/mh/thermal_building_clone/src/oemof/thermal_building_model/examples/03_applied_energy_optimization}"
PY_SCRIPT="${PY_SCRIPT:-decentralized_supply_single_building_multiple_heat_carrier_levels.py}"
CONDA_SH="${CONDA_SH:-/opt/mambaforge/install_dir/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-district_opt}"
REMOTE_LOG_DIR="${REMOTE_LOG_DIR:-/home/mh}"
EV_MODE="${EV_MODE:-no_EV}"
PRICE_SCENARIOS="${PRICE_SCENARIOS:-ref}"
RESULT_STORAGE_ROOT="${RESULT_STORAGE_ROOT:-/jump/mh}"
RESULT_CHECK_ROOT="${RESULT_CHECK_ROOT:-$RESULT_STORAGE_ROOT}"
COMBINED_OPTIMIZATION="${COMBINED_OPTIMIZATION:-false}"

if [[ "$COMBINED_OPTIMIZATION" == "true" ]]; then
  combined_flag="--combined-optimization"
else
  combined_flag=""
fi

SOLVER_THREADS=1
UEU_CASES="processed_bds_in_DENI03403000SEC5658"
REFURBISHMENTS="no_refurbishment,usual_refurbishment,advanced_refurbishment,GEG_standard"

# Per-host settings (same length required)
HOSTS=(idefix obelix verleihnix methusalix gutemine falbala)
WORKERS_PER_HOST=(30 40 16 60 110 140)
EV_MODE_PER_HOST=(
  ""
  ""
  ""
  ""
  ""
  ""
)
# Per-host values: "", "no_EV", "yes_EV", "yes_EV2".
PRICE_SCENARIOS_PER_HOST=(
  ""
  ""
  ""
  ""
  ""
  ""
)
# Multiple scenarios per host are supported as comma-separated values,
# e.g. "ref,electricity_plus20,gas_minus20".
# Standard rerun set from failed_pickle_loads.csv, without combined optimization:
# SFH k={1,2,4,6,8,10,14,18,reference}, MFH k={1,2,3,4,5,6,reference}.
# The values are split across hosts so each SFH/MFH cluster is started once.
SFH_K_PER_HOST=(
  "1,2"
  "4,6"
  "8,10"
  "14"
  "18"
  "reference"
)
MFH_K_PER_HOST=(
  "1"
  "2"
  "3"
  "4"
  "5"
  "6,reference"
)

if [[ ${#HOSTS[@]} -ne ${#WORKERS_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#SFH_K_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#MFH_K_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#PRICE_SCENARIOS_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#EV_MODE_PER_HOST[@]} ]]; then
  echo "HOSTS, WORKERS_PER_HOST, SFH_K_PER_HOST, MFH_K_PER_HOST, PRICE_SCENARIOS_PER_HOST and EV_MODE_PER_HOST must have equal length."
  exit 1
fi

successful_hosts=()
failed_hosts=()

for idx in "${!HOSTS[@]}"; do
  host="${HOSTS[$idx]}"
  workers="${WORKERS_PER_HOST[$idx]}"
  sfh_k="${SFH_K_PER_HOST[$idx]}"
  mfh_k="${MFH_K_PER_HOST[$idx]}"
  ev_mode="${EV_MODE_PER_HOST[$idx]}"
  if [[ -z "${ev_mode// }" ]]; then
    ev_mode="$EV_MODE"
  fi
  price_scenarios="${PRICE_SCENARIOS_PER_HOST[$idx]}"
  if [[ -z "${price_scenarios// }" ]]; then
    if [[ "$ev_mode" == "yes_EV" || "$ev_mode" == "yes_EV2" ]]; then
      price_scenarios="$ev_mode"
    else
      price_scenarios="$PRICE_SCENARIOS"
    fi
  fi
  out_log="${REMOTE_LOG_DIR}/decentralized_${host}.out"
  err_log="${REMOTE_LOG_DIR}/decentralized_${host}_error.log"

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
  --sfh-k "$sfh_k" \
  --mfh-k "$mfh_k" \
  --ev "$ev_mode" \
  --price-scenarios "$price_scenarios" \
  --ueu-cases "$UEU_CASES" \
  --refurbishments "$REFURBISHMENTS" \
  --result-check-root "$RESULT_CHECK_ROOT" \
  --result-storage-root "$RESULT_STORAGE_ROOT" \
  $combined_flag > "$out_log" 2> "$err_log" &
echo Started PID: \$!
EOF
  )

  echo "Launching on $host: workers=$workers sfh_k=$sfh_k mfh_k=$mfh_k price_scenarios=$price_scenarios ev=$ev_mode combined=$COMBINED_OPTIMIZATION result_storage_root=$RESULT_STORAGE_ROOT result_check_root=$RESULT_CHECK_ROOT"
  if ssh "$host" "bash -lc '$remote_cmd'"; then
    successful_hosts+=("$host")
  else
    failed_hosts+=("$host")
    echo "Launch failed on $host (continuing with remaining hosts)." >&2
  fi
done

echo "Submitted on ${#successful_hosts[@]} host(s): ${successful_hosts[*]:-none}"
if [[ ${#failed_hosts[@]} -gt 0 ]]; then
  echo "Failed on ${#failed_hosts[@]} host(s): ${failed_hosts[*]}" >&2
  exit 1
fi

echo "All remote runs submitted."
