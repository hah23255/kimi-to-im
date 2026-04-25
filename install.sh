#!/usr/bin/env bash
# Install the kimi telegram bridge as a systemd --user service.
# Idempotent: safe to re-run.
set -euo pipefail

PLUGIN_DIR="${HOME}/.kimi/plugins/telegram-bridge"
RUNTIME_DIR="${HOME}/.kimi/bridge"
LOG_DIR="${RUNTIME_DIR}/logs"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_TEMPLATE="${PLUGIN_DIR}/systemd/kimi-telegram-bridge.service.template"
SERVICE_TARGET="${SYSTEMD_USER_DIR}/kimi-telegram-bridge.service"

if [[ "$(realpath "${PWD}")" != "$(realpath "${PLUGIN_DIR}")" ]]; then
    echo "Run this from ${PLUGIN_DIR}" >&2
    exit 2
fi

echo "==> Creating runtime directories"
mkdir -p "${LOG_DIR}" "${RUNTIME_DIR}/runtime" "${SYSTEMD_USER_DIR}"

echo "==> Building Python venv"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required (https://github.com/astral-sh/uv)" >&2
    exit 3
fi
if [[ ! -d .venv ]]; then
    uv venv .venv --python 3.11
fi
.venv/bin/pip install --quiet -e .

VENV_PYTHON="${PLUGIN_DIR}/.venv/bin/python"

echo "==> Rendering systemd unit -> ${SERVICE_TARGET}"
sed \
    -e "s|__HOME__|${HOME}|g" \
    -e "s|__VENV_PYTHON__|${VENV_PYTHON}|g" \
    "${SERVICE_TEMPLATE}" > "${SERVICE_TARGET}"

echo "==> Reloading systemd --user and enabling unit"
systemctl --user daemon-reload
systemctl --user enable kimi-telegram-bridge.service

if [[ ! -f "${PLUGIN_DIR}/config.json" ]]; then
    cat <<EOF

==> Next steps:
  1. Copy and edit the config:
       cp ${PLUGIN_DIR}/config.example.json ${PLUGIN_DIR}/config.json
       \$EDITOR ${PLUGIN_DIR}/config.json

  2. Start the bridge:
       systemctl --user start kimi-telegram-bridge.service

  3. Or, from inside Kimi:
       kimi -p "use the bridge tool to start"

EOF
else
    echo "==> Existing config.json detected. Start with:"
    echo "    systemctl --user start kimi-telegram-bridge.service"
fi
