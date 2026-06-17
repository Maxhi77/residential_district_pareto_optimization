#!/usr/bin/env bash
set -euo pipefail

# Shared settings
REMOTE_EXAMPLE_DIR="${REMOTE_EXAMPLE_DIR:-/home/hill_mx/thermal_building_clone/src/oemof/thermal_building_model/examples/11_further_examples}"
PY_SCRIPT="18_centralized_supply_multiple_buildings_multiple_heat_carrier_levels_linux.py"
CONDA_SH="${CONDA_SH:-/opt/mambaforge/install_dir/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-district_opt}"
REMOTE_LOG_DIR="${REMOTE_LOG_DIR:-/home/hill_mx}"

# Write results where the script runs (Python side interprets "default")
RESULT_STORAGE_ROOT="${RESULT_STORAGE_ROOT:-default}"

SCENARIO_MODE="${SCENARIO_MODE:-capex_min_only}"   # all | capex_min_only
SOLVER_THREADS="${SOLVER_THREADS:-3}"
TEMPS="${TEMPS:-50,80}"
UEU_CASES="${UEU_CASES:-processed_bds_in_DENI03403000SEC5101:1146.15}"

# Requested k values (use "reference", not "ref")
SFH_K="${SFH_K:-1,2,reference}"
MFH_K="${MFH_K:-1,2,3,4,6,10,14,18,reference}"

# Hosts that should share the workload
HOSTS_CSV="${HOSTS_CSV:-idefix,obelix,verleihnix,methusalix,gutemine,falbala}"
IFS=',' read -r -a HOSTS <<< "$HOSTS_CSV"

if [[ ${#HOSTS[@]} -eq 0 ]]; then
  echo "No hosts configured (HOSTS_CSV is empty)." >&2
  exit 1
fi

count_csv_items() {
  local raw="$1"
  local IFS=','
  read -r -a items <<< "$raw"
  echo "${#items[@]}"
}

n_temps="$(count_csv_items "$TEMPS")"
n_ueu="$(count_csv_items "$UEU_CASES")"
n_sfh="$(count_csv_items "$SFH_K")"
n_mfh="$(count_csv_items "$MFH_K")"
total_jobs=$((n_temps * n_ueu * n_sfh * n_mfh))

n_hosts="${#HOSTS[@]}"
base_jobs=$((total_jobs / n_hosts))
extra_jobs=$((total_jobs % n_hosts))

echo "Total jobs: $total_jobs (temps=$n_temps, ueu=$n_ueu, sfh=$n_sfh, mfh=$n_mfh)"
echo "Hosts: $n_hosts | base jobs/host: $base_jobs | extra jobs: $extra_jobs"
echo "Workers are NOT set here; Python auto-selects workers."

successful_hosts=()
failed_hosts=()

job_start=0
for idx in "${!HOSTS[@]}"; do
  host="${HOSTS[$idx]}"
  max_jobs="$base_jobs"
  if [[ "$idx" -lt "$extra_jobs" ]]; then
    max_jobs=$((max_jobs + 1))
  fi

  if [[ "$max_jobs" -le 0 ]]; then
    echo "Skipping $host (no jobs assigned)."
    continue
  fi

  out_log="${REMOTE_LOG_DIR}/cen18_sec5101_${host}.out"
  err_log="${REMOTE_LOG_DIR}/cen18_sec5101_${host}_error.log"

  remote_cmd=$(
    cat <<EOF
set -e
cd "$REMOTE_EXAMPLE_DIR"
source "$CONDA_SH"
conda activate "$CONDA_ENV"
nohup python "$PY_SCRIPT" \
  --host-name "$host" \
  --job-start "$job_start" \
  --max-jobs "$max_jobs" \
  --solver-threads "$SOLVER_THREADS" \
  --scenario-mode "$SCENARIO_MODE" \
  --temps "$TEMPS" \
  --sfh-k "$SFH_K" \
  --mfh-k "$MFH_K" \
  --ueu-cases "$UEU_CASES" \
  --result-storage-root "$RESULT_STORAGE_ROOT" \
  > "$out_log" 2> "$err_log" &
echo Started PID: \$!
EOF
  )

  echo "Launching on $host: job_start=$job_start max_jobs=$max_jobs"
  if ssh "$host" "bash -lc '$remote_cmd'"; then
    successful_hosts+=("$host")
  else
    failed_hosts+=("$host")
    echo "Launch failed on $host (continuing)." >&2
  fi

  job_start=$((job_start + max_jobs))
done

echo "Submitted on ${#successful_hosts[@]} host(s): ${successful_hosts[*]:-none}"
if [[ ${#failed_hosts[@]} -gt 0 ]]; then
  echo "Failed on ${#failed_hosts[@]} host(s): ${failed_hosts[*]}" >&2
  exit 1
fi

echo "All remote runs submitted."
