FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates curl dnsutils fping iproute2 iputils-ping jq \
    libpq-dev netcat-openbsd postgresql-client shellcheck traceroute vim wget \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv || true
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /workspace
