#!/usr/bin/env bash
set -Eeuo pipefail

cd /workspace

###############################################################################
# Persistent shell history
###############################################################################
mkdir -p /root/.history
touch /root/.history/.bash_history

cat >> /root/.bashrc <<'EOF'
export HISTFILE=/root/.history/.bash_history
export HISTSIZE=100000
export HISTFILESIZE=200000
export HISTCONTROL=ignoredups:erasedups
shopt -s histappend
PROMPT_COMMAND="history -a; history -n${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
EOF

###############################################################################
# Git
###############################################################################
git config --global --add safe.directory /workspace

###############################################################################
# Environment
###############################################################################
if [ ! -f .devcontainer/.env ]; then
	cp .devcontainer/.env.example .devcontainer/.env
	echo "Please update .devcontainer/.env if you need non-default credentials."
fi

###############################################################################
# Python dependencies
###############################################################################
echo "Installing Python development dependencies..."
# shellcheck source=/dev/null
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
echo "Installing Node dependencies..."
corepack enable
pnpm install --no-frozen-lockfile

###############################################################################
# Go dependencies
###############################################################################
echo "Downloading Go modules..."
(cd agent && go mod download)

###############################################################################
# Shell completions
###############################################################################
mkdir -p /root/.local/share/bash-completion/completions

if command -v gh >/dev/null 2>&1; then
	gh completion -s bash > /root/.local/share/bash-completion/completions/gh
fi

if command -v npm >/dev/null 2>&1; then
	npm completion > /root/.local/share/bash-completion/completions/npm 2>/dev/null || true
fi

if command -v pnpm >/dev/null 2>&1; then
	pnpm completion bash > /root/.local/share/bash-completion/completions/pnpm 2>/dev/null || true
fi

if command -v pip >/dev/null 2>&1; then
	_PIP_COMPLETE=bash_source pip > /root/.local/share/bash-completion/completions/pip 2>/dev/null || true
fi

if command -v kubectl >/dev/null 2>&1; then
	kubectl completion bash > /root/.local/share/bash-completion/completions/kubectl
fi

if command -v terraform >/dev/null 2>&1; then
	terraform -install-autocomplete 2>/dev/null || true
fi

cat >> /root/.bashrc <<'EOF'
if [ -f /usr/share/bash-completion/bash_completion ]; then
  . /usr/share/bash-completion/bash_completion
fi

bind 'set completion-ignore-case on'
bind 'set show-all-if-ambiguous on'
bind 'set menu-complete-display-prefix on'
EOF

###############################################################################
# Python virtualenv activation
###############################################################################
cat >> /root/.bashrc <<'EOF'
if [ -f /opt/venv/bin/activate ]; then
  source /opt/venv/bin/activate
fi
EOF

###############################################################################
# Starship prompt
###############################################################################
mkdir -p /root/.config
cat > /root/.config/starship.toml <<'EOF'
add_newline = false

[python]
format = 'via [${symbol}${pyenv_prefix}(${version} )(\($virtualenv\) )]($style)'

[golang]
format = 'via [$symbol($version )]($style)'

[nodejs]
format = 'via [$symbol($version )]($style)'
EOF

cat >> /root/.bashrc <<'EOF'
if command -v starship >/dev/null 2>&1; then
  eval "$(starship init bash)"
fi
EOF

###############################################################################
# Git hooks
###############################################################################
if [ -x tools/setup-git-hooks ]; then
	tools/setup-git-hooks
fi

echo "BifrostNMS development environment is ready."
