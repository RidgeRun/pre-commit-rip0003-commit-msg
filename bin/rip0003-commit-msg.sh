#!/usr/bin/env bash
# Copyright (C) 2026 RidgeRun, LLC (http://www.ridgerun.com)
# All Rights Reserved.
#
# The contents of this software are proprietary and confidential to
# RidgeRun, LLC. No part of this program may be photocopied,
# reproduced or translated into another programming language without
# prior written consent of RidgeRun, LLC. The user is free to modify
# the source code after obtaining a software license from RidgeRun.
# All source code changes must be provided back to RidgeRun without
# any encumbrance.

set -euo pipefail

log(){ printf "%s\n" "$*" >&2; }

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
config_path="$repo_root/.gitlint"
extra_path="$repo_root/gitlint"

msg_filename="${1:-}"

if [[ -z "$msg_filename" ]]; then
  log "RIP 3 check failed: missing commit message filename."
  exit 1
fi

if [[ ! -f "$msg_filename" ]]; then
  log "RIP 3 check failed: commit message file '$msg_filename' was not found."
  exit 1
fi

if [[ ! -f "$config_path" ]]; then
  log "RIP 3 check failed: gitlint config '$config_path' was not found."
  exit 1
fi

if [[ ! -d "$extra_path" ]]; then
  log "RIP 3 check failed: gitlint rules directory '$extra_path' was not found."
  exit 1
fi

exec gitlint \
  --config "$config_path" \
  --extra-path "$extra_path" \
  --msg-filename "$msg_filename"
