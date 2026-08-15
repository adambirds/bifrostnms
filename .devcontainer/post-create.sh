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
WORKSPACE="/workspace"
HIST_DIR="/root/.history"
HIST_FILE="${HIST_DIR}/.bash_history"
COMP_DIR="/etc/bash_completion.d"

export SHELL="${SHELL:-/bin/bash}"
export PNPM_HOME="${PNPM_HOME:-/usr/local/share/pnpm}"
export PATH="$PNPM_HOME:/opt/venv/bin:$PATH"

echo "Setting up BifrostNMS development environment..."
cd "$WORKSPACE"

###############################################################################
# Devcontainer environment
###############################################################################
if [ ! -f .devcontainer/.env ] && [ -f .devcontainer/.env.example ]; then
	echo "Creating devcontainer environment file..."
	cp .devcontainer/.env.example .devcontainer/.env
	echo "Please update .devcontainer/.env if you need non-default credentials."
fi

###############################################################################
# Python dependencies
###############################################################################
echo "Installing Python development dependencies..."
source /opt/venv/bin/activate
python -m pip install --upgrade pip pip-tools
if [ -f backend/requirements/dev.txt ]; then
	python -m pip install -r backend/requirements/dev.txt
elif [ -f backend/requirements/dev.in ]; then
	python -m pip install -r backend/requirements/dev.in
fi

###############################################################################
# Node / pnpm dependencies
###############################################################################
echo "Installing frontend dependencies..."
corepack enable
if [ -f package.json ]; then
	pnpm install
fi
if [ -f frontend/package.json ]; then
	(
		cd frontend
		pnpm install
	)
fi

###############################################################################
# Go dependencies
###############################################################################
if [ -f agent/go.mod ]; then
	echo "Downloading Go modules..."
	(
		cd agent
		go mod download
	)
fi

###############################################################################
# Wait for PostgreSQL and Redis
###############################################################################
echo "Waiting for PostgreSQL..."
until pg_isready -h postgres -p 5432 -U bifrostnms -d bifrostnms >/dev/null 2>&1; do
	sleep 1
done
echo "PostgreSQL is available."

echo "Waiting for Redis..."
until nc -z redis 6379 >/dev/null 2>&1; do
	sleep 1
done
echo "Redis is available."

###############################################################################
# Git repository setup / hooks
###############################################################################
git config --global --add safe.directory "$WORKSPACE"

if [ -x tools/setup-git-repo ]; then
	echo "Installing repository git hooks..."
	tools/setup-git-repo
elif [ -d tools/hooks ]; then
	git config --global core.hooksPath tools/hooks
fi

# Keep shared tooling executable after bind mounts / platform changes.
find tools -maxdepth 1 -type f -exec chmod +x {} + 2>/dev/null || true
find tools/setup -maxdepth 1 -type f -exec chmod +x {} + 2>/dev/null || true
find .devcontainer/scripts -maxdepth 1 -type f -name '*.sh' -exec chmod +x {} + 2>/dev/null || true

###############################################################################
# Bash prompt: ensure the Python venv is active and visible
###############################################################################
MARK_BEGIN="# >>> bifrostnms: ensure (venv) prompt begin >>>"
MARK_END="# <<< bifrostnms: ensure (venv) prompt end <<<"

if grep -qF "$MARK_BEGIN" "$BASHRC" 2>/dev/null; then
	awk -v s="$MARK_BEGIN" -v e="$MARK_END" '
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
fi
# <<< bifrostnms: ensure (venv) prompt end <<<
EOF

###############################################################################
# Persistent Bash history
###############################################################################
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
# Bash completion and interactive shell QoL
###############################################################################
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
	npm completion >"${COMP_DIR}/npm" || true
	cp -f "${COMP_DIR}/npm" "${COMP_DIR}/npx" 2>/dev/null || true
fi

if command -v pnpm >/dev/null 2>&1; then
	pnpm completion bash >"${COMP_DIR}/pnpm" || true
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
# Starship prompt
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

[python]
format = "via [$symbol$pyenv_prefix($version )(\\($virtualenv\\) )]($style)"

[golang]
format = "via [$symbol($version )]($style)"

[nodejs]
format = "via [$symbol($version )]($style)"

[cmd_duration]
min_time = 1000

[character]
success_symbol = "\\$ "
error_symbol = "! "
EOF

###############################################################################
# Summary
###############################################################################
echo "Development environment setup complete!"
echo ""
echo "Quick start commands:"
echo "  Backend:   cd /workspace && uvicorn backend.bifrostnms.main:app --host 0.0.0.0 --port 8000 --reload"
echo "  Frontend:  cd /workspace/frontend && pnpm dev"
echo "  Agent:     cd /workspace/agent && go run ./cmd/bifrost-agent"
echo "  Lint:      cd /workspace && tools/lint"
echo "  Tests:     cd /workspace && tools/test-all"
echo ""
echo "Local services:"
echo "  API:        http://localhost:8000/"
echo "  Frontend:   http://localhost:5173/"
echo "  PostgreSQL: localhost:5432"
echo "  Redis:      localhost:6379"
