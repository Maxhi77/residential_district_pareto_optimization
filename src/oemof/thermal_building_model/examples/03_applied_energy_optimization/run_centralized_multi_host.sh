#!/usr/bin/env bash
set -euo pipefail

# Shared settings
REMOTE_EXAMPLE_DIR="${REMOTE_EXAMPLE_DIR:-/home/hill_mx/thermal_building_clone/src/oemof/thermal_building_model/examples/03_applied_energy_optimization}"
PY_SCRIPT="${PY_SCRIPT:-centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py}"

# Leave empty to use current env; set explicitly if needed.
CONDA_SH="${CONDA_SH:-}"
CONDA_ENV="${CONDA_ENV:-final_umgebung}"

REMOTE_LOG_DIR="${REMOTE_LOG_DIR:-/home/hill_mx}"

# Check/write results where the centralized script runs (03_applied_energy_optimization).
RESULT_STORAGE_ROOT="${RESULT_STORAGE_ROOT:-default}"

SCENARIO_MODE="${SCENARIO_MODE:-capex_min_only}"   # all | capex_min_only
SOLVER="${SOLVER:-gurobi}"
SOLVER_THREADS="${SOLVER_THREADS:-3}"
TEMPS="${TEMPS:-50,80}"
UEU_CASES="${UEU_CASES:-processed_bds_in_DENI03403000SEC5101:2723.29}"
CO2_FACTORS="${CO2_FACTORS:-1,0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.55,0.5,0.45,0.4,0.35,0.3,0.25,0.2,0.15,0.1,0.05,0.01,-0.01,-0.05,-0.1,-0.2}"

# Requested k values (use "reference", not "ref").
SFH_K="${SFH_K:-1,2,4,6,8,10,reference}"
MFH_K="${MFH_K:-1,2,3,4,6,10,reference}"

# Optional remote hosts. Empty => run locally only.
HOSTS_CSV="${HOSTS_CSV:-}"
if [[ -z "${HOSTS_CSV// }" ]]; then
  HOSTS=("local")
else
  IFS=',' read -r -a HOSTS <<< "$HOSTS_CSV"
fi

if [[ ${#HOSTS[@]} -eq 0 ]]; then
  echo "No hosts configured." >&2
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
echo "Solver: $SOLVER | solver_threads=$SOLVER_THREADS"
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

  out_log="${REMOTE_LOG_DIR}/cen_sec5101_${host}.out"
  err_log="${REMOTE_LOG_DIR}/cen_sec5101_${host}_error.log"

  remote_cmd=$(
    cat <<EOF
set -e
cd "$REMOTE_EXAMPLE_DIR"

if [[ -n "$CONDA_SH" && -f "$CONDA_SH" ]]; then
  source "$CONDA_SH"
  conda activate "$CONDA_ENV"
else
  echo "CONDA_SH not found, using current env: \${CONDA_DEFAULT_ENV:-unknown}"
fi

nohup python "$PY_SCRIPT" \
  --host-name "$host" \
  --job-start "$job_start" \
  --max-jobs "$max_jobs" \
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
echo Started PID: \$!
EOF
  )

  echo "Launching on $host: job_start=$job_start max_jobs=$max_jobs solver=$SOLVER solver_threads=$SOLVER_THREADS ueu=$UEU_CASES"
  if [[ "$host" == "local" ]]; then
    if bash -lc "$remote_cmd"; then
      successful_hosts+=("$host")
    else
      failed_hosts+=("$host")
      echo "Launch failed on $host (continuing)." >&2
    fi
  else
    if ssh "$host" "bash -lc '$remote_cmd'"; then
      successful_hosts+=("$host")
    else
      failed_hosts+=("$host")
      echo "Launch failed on $host (continuing)." >&2
    fi
  fi

  job_start=$((job_start + max_jobs))
done

echo "Submitted on ${#successful_hosts[@]} host(s): ${successful_hosts[*]:-none}"
if [[ ${#failed_hosts[@]} -gt 0 ]]; then
  echo "Failed on ${#failed_hosts[@]} host(s): ${failed_hosts[*]}" >&2
  exit 1
fi

echo "All remote runs submitted."
