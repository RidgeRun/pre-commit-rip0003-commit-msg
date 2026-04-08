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

normalize_branch(){
  local ref="${1:-}"

  case "$ref" in
    refs/heads/*)
      printf "%s\n" "${ref#refs/heads/}"
      ;;
    refs/remotes/*/*)
      printf "%s\n" "${ref#refs/remotes/*/}"
      ;;
    *)
      printf "%s\n" "$ref"
      ;;
  esac
}

is_mainline_branch(){
  case "${1:-}" in
    main|master|develop)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_commit_list(){
  local zero_ref="0000000000000000000000000000000000000000"

  if [[ -n "${PRE_COMMIT_FROM_REF:-}" && -n "${PRE_COMMIT_TO_REF:-}" &&
        "${PRE_COMMIT_FROM_REF}" != "$zero_ref" &&
        "${PRE_COMMIT_TO_REF}" != "$zero_ref" ]]; then
    git rev-list --reverse "${PRE_COMMIT_FROM_REF}..${PRE_COMMIT_TO_REF}"
    return
  fi

  if [[ -n "${PRE_COMMIT_TO_REF:-}" && "${PRE_COMMIT_TO_REF}" != "$zero_ref" ]]; then
    git rev-list --reverse "${PRE_COMMIT_TO_REF}"
    return
  fi

  if [[ -n "${PRE_COMMIT_LOCAL_BRANCH:-}" ]]; then
    git rev-list --reverse "${PRE_COMMIT_LOCAL_BRANCH}"
    return
  fi

  git rev-list --reverse HEAD
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
config_path="$repo_root/.gitlint"
extra_path="$repo_root/gitlint"

if [[ ! -f "$config_path" ]]; then
  log "RIP 3 check failed: gitlint config '$config_path' was not found."
  exit 1
fi

if [[ ! -d "$extra_path" ]]; then
  log "RIP 3 check failed: gitlint rules directory '$extra_path' was not found."
  exit 1
fi

target_branch="$(normalize_branch "${PRE_COMMIT_REMOTE_BRANCH:-${PRE_COMMIT_LOCAL_BRANCH:-}}")"

if ! is_mainline_branch "$target_branch"; then
  exit 0
fi

commit_list="$(resolve_commit_list)"

if [[ -z "$commit_list" ]]; then
  exit 0
fi

while IFS= read -r commit_sha; do
  [[ -n "$commit_sha" ]] || continue

  if ! RIP0003_BRANCH="$target_branch" gitlint \
    --config "$config_path" \
    --extra-path "$extra_path" \
    --ignore-stdin \
    --commit "$commit_sha"; then
    log "RIP 3 pre-push check failed for commit '$commit_sha' on branch '$target_branch'."
    exit 1
  fi
done <<< "$commit_list"
