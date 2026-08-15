FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NODE_ENV=development
ENV PNPM_HOME=/usr/local/share/pnpm

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf automake bash-completion build-essential ca-certificates curl dnsutils fping gcc git htop \
    iproute2 iputils-ping jq libffi-dev libpq-dev libtool locales netcat-openbsd pkg-config \
    postgresql-client procps python3 python3-dev python3-pip python3-venv shellcheck sudo traceroute vim wget \
    && locale-gen en_GB.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_GB.UTF-8
ENV LC_ALL=en_GB.UTF-8
ENV PATH="${PNPM_HOME}:/opt/venv/bin:${PATH}"

# Starship provides the consistent interactive prompt configured by post-create.sh.
RUN curl -fsSL https://starship.rs/install.sh | sh -s -- -y -b /usr/local/bin

# Reuse the standard shell tooling installers shared with Adam's other projects.
COPY tools/setup/install-shellcheck /tmp/install-shellcheck
COPY tools/setup/install-shfmt /tmp/install-shfmt
RUN chmod +x /tmp/install-shellcheck /tmp/install-shfmt \
    && /tmp/install-shellcheck \
    && /tmp/install-shfmt \
    && rm -f /tmp/install-shellcheck /tmp/install-shfmt

# Create the project virtualenv before Dev Container features are applied so
# /opt/venv exists for VS Code, post-create.sh and non-interactive shells.
RUN python3 -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv

WORKDIR /workspace
CMD ["sleep", "infinity"]
