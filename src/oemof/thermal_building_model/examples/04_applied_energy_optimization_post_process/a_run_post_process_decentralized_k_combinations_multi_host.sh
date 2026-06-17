#!/usr/bin/env bash
set -uo pipefail

# Shared settings
REMOTE_EXAMPLE_DIR="${REMOTE_EXAMPLE_DIR:-/home/mh/thermal_building_clone/src/oemof/thermal_building_model/examples/04_applied_energy_optimization_post_process}"
PY_SCRIPT="post_process_decentralized_k_combinations.py"
CONDA_SH="${CONDA_SH:-/opt/mambaforge/install_dir/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-district_opt}"
REMOTE_LOG_DIR="${REMOTE_LOG_DIR:-/home/mh}"
DATA_BASE_DIR="${DATA_BASE_DIR:-/jump/mh}"
CLUSTER_BASE_DIR="${CLUSTER_BASE_DIR:-/home/mh/thermal_building_clone/src/oemof/thermal_building_model/examples/03_applied_energy_optimization}"
CLUSTER_UEU_CASE="${CLUSTER_UEU_CASE:-processed_bds_in_DENI03403000SEC5658}"

UEU_CASE="${UEU_CASE:-processed_bds_in_DENI03403000SEC5658_yes_EV,processed_bds_in_DENI03403000SEC5658_yes_EV2,processed_bds_in_DENI03403000SEC5658_hydrogen_minus20,processed_bds_in_DENI03403000SEC5658_hydrogen_plus20}"
REFURBISHMENTS="${REFURBISHMENTS:-no_refurbishment,usual_refurbishment,advanced_refurbishment,GEG_standard}"
OPTIMIZATION_STRATEGIES="${OPTIMIZATION_STRATEGIES:-co2}"
OUTPUT_ROOT_NAME="${OUTPUT_ROOT_NAME:-}"
EXCLUDED_HOSTS="${EXCLUDED_HOSTS:-verleihnix,falbala}"

# Per-host settings (same length required)
HOSTS=(idefix obelix methusalix gutemine)
WORKERS_PER_HOST=(30 40 60 110)
SFH_K_PER_HOST=(
  "6"
  "6"
  "6"
  "6"
)
MFH_K_PER_HOST=(
  "1"
  "1"
  "1"
  "1"
)

if [[ ${#HOSTS[@]} -ne ${#WORKERS_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#SFH_K_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#MFH_K_PER_HOST[@]} ]]; then
  echo "HOSTS, WORKERS_PER_HOST, SFH_K_PER_HOST and MFH_K_PER_HOST must have equal length."
  exit 1
fi

IFS=',' read -r -a excluded_hosts_array <<< "$EXCLUDED_HOSTS"
IFS=',' read -r -a ueu_cases_array <<< "$UEU_CASE"

active_hosts=()
active_workers=()
active_sfh_k=()
active_mfh_k=()

is_excluded_host() {
  local candidate="$1"
  local blocked
  for blocked in "${excluded_hosts_array[@]}"; do
    blocked="${blocked// /}"
    [[ -z "$blocked" ]] && continue
    if [[ "$candidate" == "$blocked" ]]; then
      return 0
    fi
  done
  return 1
}

for idx in "${!HOSTS[@]}"; do
  host="${HOSTS[$idx]}"
  if is_excluded_host "$host"; then
    echo "Skipping excluded host: $host"
    continue
  fi
  active_hosts+=("$host")
  active_workers+=("${WORKERS_PER_HOST[$idx]}")
  active_sfh_k+=("${SFH_K_PER_HOST[$idx]}")
  active_mfh_k+=("${MFH_K_PER_HOST[$idx]}")
done

if [[ ${#active_hosts[@]} -eq 0 ]]; then
  echo "No active hosts left after applying EXCLUDED_HOSTS=$EXCLUDED_HOSTS."
  exit 1
fi

if [[ ${#ueu_cases_array[@]} -eq 0 ]]; then
  echo "UEU_CASE contains no values."
  exit 1
fi

successful_jobs=()
failed_jobs=()

for idx in "${!ueu_cases_array[@]}"; do
  ueu_case="${ueu_cases_array[$idx]}"
  ueu_case="${ueu_case// /}"
  [[ -z "$ueu_case" ]] && continue

  host_idx=$(( idx % ${#active_hosts[@]} ))
  host="${active_hosts[$host_idx]}"
  workers="${active_workers[$host_idx]}"
  sfh_k="${active_sfh_k[$host_idx]}"
  mfh_k="${active_mfh_k[$host_idx]}"
  case_tag="${ueu_case//[^a-zA-Z0-9_-]/_}"
  out_log="${REMOTE_LOG_DIR}/post_dec_combo_${host}_${case_tag}.out"
  err_log="${REMOTE_LOG_DIR}/post_dec_combo_${host}_${case_tag}_error.log"

  remote_cmd=$(
    cat <<EOF
set -e
cd "$REMOTE_EXAMPLE_DIR"
source "$CONDA_SH"
conda activate "$CONDA_ENV"
cmd=(python "$PY_SCRIPT"
  --host-name "$host"
  --workers "$workers"
  --sfh-k "$sfh_k"
  --mfh-k "$mfh_k"
  --ueu-case "$ueu_case"
  --base-dir "$DATA_BASE_DIR"
  --cluster-base-dir "$CLUSTER_BASE_DIR"
  --cluster-ueu-case "$CLUSTER_UEU_CASE"
  --refurbishments "$REFURBISHMENTS"
  --optimization-strategies "$OPTIMIZATION_STRATEGIES"
)
if [ -n "$OUTPUT_ROOT_NAME" ]; then
  cmd+=(--output-root-name "$OUTPUT_ROOT_NAME")
fi
nohup "\${cmd[@]}" > "$out_log" 2> "$err_log" &
echo Started PID: \$!
EOF
  )

  echo "Launching on $host: workers=$workers sfh_k=$sfh_k mfh_k=$mfh_k ueu_case=$ueu_case base_dir=$DATA_BASE_DIR cluster_base_dir=$CLUSTER_BASE_DIR cluster_ueu_case=$CLUSTER_UEU_CASE"
  if ssh "$host" "bash -lc '$remote_cmd'"; then
    successful_jobs+=("${host}:${ueu_case}")
  else
    failed_jobs+=("${host}:${ueu_case}")
    echo "Launch failed on $host for ueu_case=$ueu_case (continuing with remaining cases)." >&2
  fi
done

echo "Submitted ${#successful_jobs[@]} job(s): ${successful_jobs[*]:-none}"
if [[ ${#failed_jobs[@]} -gt 0 ]]; then
  echo "Failed ${#failed_jobs[@]} job(s): ${failed_jobs[*]}" >&2
  exit 1
fi

echo "All remote runs submitted."
