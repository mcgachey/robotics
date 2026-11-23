#!/usr/bin/env bash
# Routine update: fetch the branch, then deps build deploy check. Unit tests are skipped here
# (run them on a dev machine with `make test`); `make check` runs the acceptance test on the deployed system.
# Config time only. Usage: sudo bin/update_rp.sh [branch]   (default: main)
# Assumes bin/init_rp.sh already ran (on any branch); this switches the checkout to <branch>.
set -euo pipefail

# Everything is inside a function so bash has parsed it all before
# `git reset --hard` replaces this very file.
main() {
  local branch=${1:-main}
  local repo; repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
  local init=/etc/robotics/init.env

  [ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root (sudo bin/update_rp.sh [branch])" >&2; exit 1; }

  # 1. init must have run (any branch; update switches to the requested one)
  [ -f "$init" ] || { echo "ERROR: $init missing: run bin/init_rp.sh $branch (or re-image)" >&2; exit 1; }

  # 2. Discard local changes; match the remote branch exactly
  git config --global --add safe.directory "$repo"
  cd "$repo"
  git fetch origin "$branch"
  git checkout -f -B "$branch" "origin/$branch"
  git reset --hard "origin/$branch"

  # Record the branch now deployed
  sed -i "s/^BRANCH=.*/BRANCH=$branch/" "$init"

  # 3. Pipelines (Node on PATH for make only; the Makefile also sets it)
  make deps build deploy check
}

main "$@"
exit
