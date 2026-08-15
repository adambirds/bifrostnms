#!/usr/bin/env bash
set -euo pipefail

mkdir -p /root/.history
export HISTFILE=/root/.history/.bash_history

git config --global core.hooksPath tools/hooks

python -m pip install --upgrade pip pip-tools
if [[ -f backend/requirements/dev.txt ]]; then
  python -m pip install -r backend/requirements/dev.txt
elif [[ -f backend/requirements/dev.in ]]; then
  python -m pip install -r backend/requirements/dev.in
fi

corepack enable
if [[ -f package.json ]]; then pnpm install; fi
if [[ -f agent/go.mod ]]; then (cd agent && go mod download); fi

chmod +x tools/* .devcontainer/scripts/*.sh 2>/dev/null || true
printf '\nBifrostNMS development container is ready.\n'
