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

msg_filename="${1:-}"

if [[ -z "$msg_filename" ]]; then
  log "RIP 3 check failed: missing commit message filename."
  exit 1
fi

if [[ ! -f "$msg_filename" ]]; then
  log "RIP 3 check failed: commit message file '$msg_filename' was not found."
  exit 1
fi

exec gitlint --config .gitlint --msg-filename "$msg_filename"
