#!/usr/bin/env bash
# Post-create script for the BifrostNMS devcontainer.
set -Eeuo pipefail

error_trap() {
	local code=$?
	echo "❌ post-create failed at line $LINENO: ${BASH_COMMAND} (exit $code)"
	exit "$code"
}
trap error_trap ERR

BASHRC="/root/.bashrc"
export SHELL="${SHELL:-/bin/bash}"
export PNPM_HOME="${PNPM_HOME:-/usr/local/share/pnpm}"
export PATH="$PNPM_HOME:$PATH"

echo "Setting up BifrostNMS development environment..."
cd /workspace

if [ ! -f .devcontainer/.env ]; then
	echo "Creating devcontainer environment file..."
	cp .devcontainer/.env.example .devcontainer/.env
	echo "Please update .devcontainer/.env if you need non-default credentials."
fi

###############################################################################
# Dependencies
###############################################################################
echo "Installing Python development dependencies..."
# shellcheck source=/dev/null
source /opt/venv/bin/activate
python -m pip install --upgrade pip pip-tools
if [ -f backend/requirements/dev.txt ]; then
	python -m pip install -r backend/requirements/dev.txt
else
	python -m pip install -r backend/requirements/dev.in
fi

echo "Installing Node dependencies..."
corepack enable
pnpm install

echo "Downloading Go modules..."
(cd agent && go mod download)

git config --global --add safe.directory /workspace

###############################################################################
# Bash prompt: keep /opt/venv active and visible in every interactive shell.
###############################################################################
PROMPT_BEGIN="# >>> bifrostnms: ensure (venv) prompt begin >>>"
PROMPT_END="# <<< bifrostnms: ensure (venv) prompt end <<<"

if grep -qF "$PROMPT_BEGIN" "$BASHRC" 2>/dev/null; then
	awk -v s="$PROMPT_BEGIN" -v e="$PROMPT_END" '
    $0==s {inblk=1; next}
    $0==e {inblk=0; next}
    !inblk {print}
  ' "$BASHRC" >"${BASHRC}.tmp" && mv "${BASHRC}.tmp" "$BASHRC"
fi

cat >>"$BASHRC" <<'EOF'
# >>> bifrostnms: ensure (venv) prompt begin >>>
if [ -n "$PS1" ]; then
  unset VIRTUAL_ENV_DISABLE_PROMPT
  export VIRTUAL_ENV_PROMPT="(venv) "
  if [ -f /opt/venv/bin/activate ]; then
    . /opt/venv/bin/activate
  fi
  if [ -n "${VIRTUAL_ENV:-}" ] && [[ "$PS1" != *"(venv)"* ]] && [[ "$PS1" != *"($(basename "$VIRTUAL_ENV"))"* ]]; then
    PS1="${VIRTUAL_ENV_PROMPT:-($(basename "$VIRTUAL_ENV")) }$PS1"
  fi
fi
# <<< bifrostnms: ensure (venv) prompt end <<<
EOF

###############################################################################
# Persistent Bash history shared live between terminals.
###############################################################################
HIST_DIR="/root/.history"
HIST_FILE="${HIST_DIR}/.bash_history"
HIST_BEGIN="# >>> bifrostnms: persistent bash history begin >>>"
HIST_END="# <<< bifrostnms: persistent bash history end <<<"

mkdir -p "$HIST_DIR"
touch "$HIST_FILE"
chmod 700 "$HIST_DIR"
chmod 600 "$HIST_FILE"
ln -sf "$HIST_FILE" /root/.bash_history

if grep -qF "$HIST_BEGIN" "$BASHRC" 2>/dev/null; then
	awk -v s="$HIST_BEGIN" -v e="$HIST_END" '
    $0==s {inblk=1; next}
    $0==e {inblk=0; next}
    !inblk {print}
  ' "$BASHRC" >"${BASHRC}.tmp" && mv "${BASHRC}.tmp" "$BASHRC"
fi

cat >>"$BASHRC" <<EOF
${HIST_BEGIN}
export HISTFILE="${HIST_FILE}"
export HISTSIZE=50000
export HISTFILESIZE=100000
export HISTCONTROL=ignoredups:erasedups
export HISTTIMEFORMAT='%F %T '
shopt -s histappend
PROMPT_COMMAND="history -a; history -n; \${PROMPT_COMMAND:-}"
${HIST_END}
EOF

###############################################################################
# Bash completion and common CLI completions.
###############################################################################
COMP_DIR="/etc/bash_completion.d"
COMP_BEGIN="# >>> bifrostnms: bash-completion begin >>>"
COMP_END="# <<< bifrostnms: bash-completion end <<<"
mkdir -p "$COMP_DIR"

if grep -qF "$COMP_BEGIN" "$BASHRC" 2>/dev/null; then
	awk -v s="$COMP_BEGIN" -v e="$COMP_END" '
    $0==s {inblk=1; next}
    $0==e {inblk=0; next}
    !inblk {print}
  ' "$BASHRC" >"${BASHRC}.tmp" && mv "${BASHRC}.tmp" "$BASHRC"
fi

cat >>"$BASHRC" <<'EOF'
# >>> bifrostnms: bash-completion begin >>>
if [ -n "$PS1" ]; then
  if [ -r /etc/profile.d/bash_completion.sh ]; then
    . /etc/profile.d/bash_completion.sh
  elif [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  fi
fi
bind "set completion-ignore-case on"
bind "set show-all-if-ambiguous on"
bind "set menu-complete-display-prefix on"
# <<< bifrostnms: bash-completion end <<<
EOF

if command -v gh >/dev/null 2>&1; then
	gh completion -s bash >"${COMP_DIR}/gh"
fi
if command -v npm >/dev/null 2>&1; then
	npm completion >"${COMP_DIR}/npm"
	cp -f "${COMP_DIR}/npm" "${COMP_DIR}/npx"
fi
if command -v pnpm >/dev/null 2>&1; then
	pnpm completion bash >"${COMP_DIR}/pnpm"
fi
if command -v python >/dev/null 2>&1; then
	python -m pip completion --bash >"${COMP_DIR}/pip" 2>/dev/null || true
fi
if command -v kubectl >/dev/null 2>&1; then
	kubectl completion bash >"${COMP_DIR}/kubectl"
fi
if command -v terraform >/dev/null 2>&1; then
	terraform -install-autocomplete >/dev/null 2>&1 || true
fi

###############################################################################
# Starship prompt.
###############################################################################
STARSHIP_BEGIN="# >>> bifrostnms: starship init begin >>>"
STARSHIP_END="# <<< bifrostnms: starship init end <<<"
if grep -qF "$STARSHIP_BEGIN" "$BASHRC" 2>/dev/null; then
	awk -v s="$STARSHIP_BEGIN" -v e="$STARSHIP_END" '
    $0==s {inblk=1; next}
    $0==e {inblk=0; next}
    !inblk {print}
  ' "$BASHRC" >"${BASHRC}.tmp" && mv "${BASHRC}.tmp" "$BASHRC"
fi

cat >>"$BASHRC" <<'EOF'
# >>> bifrostnms: starship init begin >>>
if command -v starship >/dev/null 2>&1; then
  eval "$(starship init bash)"
fi
# <<< bifrostnms: starship init end <<<
EOF

mkdir -p /root/.config
cat >/root/.config/starship.toml <<'EOF'
add_newline = false
format = "$directory$git_branch$git_status$python$golang$nodejs$cmd_duration$character"

[directory]
truncation_length = 3
truncate_to_repo = true

[git_status]
disabled = true

[cmd_duration]
min_time = 1000

[character]
success_symbol = "\\$ "
error_symbol = "! "
EOF

if [ -x tools/setup-git-hooks ]; then
	tools/setup-git-hooks
fi

echo "Development environment setup complete!"
echo ""
echo "Quick start commands:"
echo "  API:             PYTHONPATH=backend uvicorn bifrostnms.main:app --reload --host 0.0.0.0 --port 8000"
echo "  Dashboard:       pnpm --dir frontend dev"
echo "  Auth Frontend:   pnpm --dir auth-frontend dev"
echo "  Celery Worker:   PYTHONPATH=backend celery -A bifrostnms.celery_app:celery_app worker --loglevel=INFO --queues=default,email,notifications"
echo "  Agent:           cd agent && go run ./cmd/bifrost-agent"
