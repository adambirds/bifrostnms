#!/usr/bin/env bash
set -euo pipefail

if [[ -f /host-home/.gitconfig ]]; then
  git config --global include.path /host-home/.gitconfig
fi
