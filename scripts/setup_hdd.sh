#!/usr/bin/env bash
set -euo pipefail
storage_path="${1:-/mnt/vector-trading}"
case "$storage_path" in /|/home|/var) echo "Choose a dedicated subdirectory" >&2; exit 2;; esac
mkdir -p "$storage_path"/{postgres,redis,app/logs,app/models,app/knowledge,backups}
chmod 700 "$storage_path"
echo "HDD storage prepared at $storage_path"

