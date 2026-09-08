#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/copy_to_dev_pc.sh [--port PORT] [SSH_TARGET [DESTINATION]]

Copy G1 Dancer to the development PC over SSH without deleting remote files.

Arguments:
  SSH_TARGET   SSH host (default: unitree@10.42.0.1)
  DESTINATION  Remote directory (default: ~/g1-dancer)

Options:
  --port PORT  SSH port (default: 22)
  -h, --help   Show this help

Examples:
  scripts/copy_to_dev_pc.sh
  scripts/copy_to_dev_pc.sh unitree@10.42.0.1
  scripts/copy_to_dev_pc.sh --port 2222 unitree@g1-dev.local /home/unitree/g1-dancer
EOF
}

ssh_port=22
while (($#)); do
  case "$1" in
    --port)
      if (($# < 2)); then
        echo "error: --port requires a value" >&2
        exit 2
      fi
      ssh_port=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if (($# > 2)); then
  usage >&2
  exit 2
fi

ssh_target=${1:-'unitree@10.42.0.1'}
destination=${2:-'~/g1-dancer'}

if [[ ! $ssh_port =~ ^[0-9]+$ ]] || ((ssh_port < 1 || ssh_port > 65535)); then
  echo "error: SSH port must be between 1 and 65535" >&2
  exit 2
fi
if [[ -z $ssh_target || $ssh_target == -* || $ssh_target == *$'\n'* ]]; then
  echo "error: invalid SSH target" >&2
  exit 2
fi
if [[ -z $destination || $destination == *$'\n'* ]]; then
  echo "error: invalid destination" >&2
  exit 2
fi
if ! command -v ssh >/dev/null 2>&1; then
  echo "error: ssh is required" >&2
  exit 1
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "error: rsync is required" >&2
  exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(dirname -- "$script_dir")

echo "Checking SSH connection to $ssh_target ..."
ssh -p "$ssh_port" "$ssh_target" true

echo "Copying $project_dir to $ssh_target:$destination ..."
rsync -az --human-readable --progress \
  -e "ssh -p $ssh_port" \
  --exclude='.git/' \
  --exclude='mobile_app/' \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.py[cod]' \
  --exclude='*.egg-info/' \
  --exclude='build/' \
  --exclude='dist/' \
  "$project_dir/" "$ssh_target:$destination/"

echo "Copy complete. On the development PC run:"
printf '  cd %q && python3 -m pip install --user .\n' "$destination"
