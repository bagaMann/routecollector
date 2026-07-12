#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/routecollector}"
SERVICE_NAME="routecollector.service"

log() { printf '[routecollector] %s\n' "$*"; }
fail() { printf '[routecollector] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run this script as root."
[[ -d "${INSTALL_DIR}/.git" ]] || fail "Git checkout not found in ${INSTALL_DIR}."
[[ -x "${INSTALL_DIR}/.venv/bin/python" ]] || fail "Virtual environment not found."

systemctl stop "${SERVICE_NAME}"

mkdir -p "${INSTALL_DIR}/state/backups"
if [[ -f "${INSTALL_DIR}/state/state.db" ]]; then
    cp -a "${INSTALL_DIR}/state/state.db"         "${INSTALL_DIR}/state/backups/state-$(date +%Y%m%d-%H%M%S).db"
fi

git -C "${INSTALL_DIR}" fetch --tags origin
git -C "${INSTALL_DIR}" pull --ff-only

"${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -e "${INSTALL_DIR}"

ln -sf \
    "${INSTALL_DIR}/.venv/bin/routecollector" \
    /usr/local/bin/routecollector

cd "${INSTALL_DIR}"
"${INSTALL_DIR}/.venv/bin/routecollector" init

if [[ -x "${INSTALL_DIR}/.venv/bin/ruff" ]]; then
    "${INSTALL_DIR}/.venv/bin/ruff" check .
fi

if [[ -x "${INSTALL_DIR}/.venv/bin/pytest" ]]; then
    "${INSTALL_DIR}/.venv/bin/pytest" -q
fi

"${INSTALL_DIR}/.venv/bin/routecollector" run-once     --min-confidence-ipv4 60     --min-confidence-ipv6 60

systemctl daemon-reload
systemctl restart "${SERVICE_NAME}"
systemctl is-active --quiet "${SERVICE_NAME}"     || fail "RouteCollector failed to start after upgrade."

log "Upgrade completed successfully."
