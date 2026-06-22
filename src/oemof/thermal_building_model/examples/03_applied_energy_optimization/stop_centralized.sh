#!/usr/bin/env bash
set -uo pipefail

# Stop distributed centralized runs started by run_centralized.sh.
# The matcher is intentionally narrow: only Python commands containing PY_SCRIPT are stopped.
PY_SCRIPT="${PY_SCRIPT:-centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py}"
HOSTS=(idefix obelix verleihnix methusalix gutemine falbala)
DRY_RUN=false
FORCE=false

usage() {
  cat <<EOF
Usage: $0 [--dry-run] [--force] [--hosts host1,host2]

Options:
  --dry-run          Show matching processes without stopping them.
  --force           Send SIGKILL to processes still alive after SIGTERM.
  --hosts LIST      Comma-separated host list. Defaults to: ${HOSTS[*]}
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --hosts)
      if [[ $# -lt 2 ]]; then
        echo "--hosts requires a comma-separated value." >&2
        exit 2
      fi
      IFS=',' read -r -a HOSTS <<< "$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

successful_hosts=()
failed_hosts=()

for host in "${HOSTS[@]}"; do
  remote_cmd=$(
    cat <<EOF
set -uo pipefail
PY_SCRIPT="$PY_SCRIPT"
DRY_RUN="$DRY_RUN"
FORCE="$FORCE"

pids=()
while read -r pid comm cmd; do
  if [[ -z "\${pid:-}" || -z "\${comm:-}" || -z "\${cmd:-}" ]]; then
    continue
  fi
  if [[ "\$comm" == python* && "\$cmd" == *"\$PY_SCRIPT"* ]]; then
    pids+=("\$pid")
  fi
done < <(ps -u "\$USER" -o pid= -o comm= -o args=)

if [[ \${#pids[@]} -eq 0 ]]; then
  echo "No matching centralized Python runs found."
  exit 0
fi

echo "Matching centralized Python runs:"
ps -o pid,etimes,cmd -p "\$(IFS=,; echo "\${pids[*]}")"

if [[ "\$DRY_RUN" == "true" ]]; then
  echo "Dry-run only. No processes stopped."
  exit 0
fi

kill -TERM "\${pids[@]}"
sleep 2

remaining=()
for pid in "\${pids[@]}"; do
  if kill -0 "\$pid" 2>/dev/null; then
    remaining+=("\$pid")
  fi
done

if [[ \${#remaining[@]} -gt 0 && "\$FORCE" == "true" ]]; then
  echo "Force-stopping remaining PIDs: \${remaining[*]}"
  kill -KILL "\${remaining[@]}"
elif [[ \${#remaining[@]} -gt 0 ]]; then
  echo "Still running after SIGTERM: \${remaining[*]} (rerun with --force if needed)"
fi
EOF
  )

  echo "Stopping on $host: script=$PY_SCRIPT dry_run=$DRY_RUN force=$FORCE"
  if ssh "$host" "bash -lc '$remote_cmd'"; then
    successful_hosts+=("$host")
  else
    failed_hosts+=("$host")
    echo "Stop failed on $host (continuing with remaining hosts)." >&2
  fi
done

echo "Checked ${#successful_hosts[@]} host(s): ${successful_hosts[*]:-none}"
if [[ ${#failed_hosts[@]} -gt 0 ]]; then
  echo "Failed on ${#failed_hosts[@]} host(s): ${failed_hosts[*]}" >&2
  exit 1
fi

echo "Stop command finished."
