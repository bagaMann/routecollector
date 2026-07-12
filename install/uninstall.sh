#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/routecollector}"
SERVICE_FILE="/etc/systemd/system/routecollector.service"
BIRD_MAIN_CONFIG="/etc/bird/bird.conf"
BIRD_INCLUDE_CONFIG="/etc/bird/routecollector.conf"
DELETE_DATA="${DELETE_DATA:-no}"

log() { printf '[routecollector] %s\n' "$*"; }
fail() { printf '[routecollector] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run this script as root."

systemctl disable --now routecollector.service 2>/dev/null || true
rm -f "${SERVICE_FILE}"
rm -f /usr/local/bin/routecollector
systemctl daemon-reload
systemctl reset-failed

if [[ -f "${BIRD_MAIN_CONFIG}" ]]; then
    sed -i '\|^include "/etc/bird/routecollector.conf";$|d' "${BIRD_MAIN_CONFIG}"
fi

rm -f "${BIRD_INCLUDE_CONFIG}"
systemctl reload bird 2>/dev/null || true

if [[ "${DELETE_DATA}" == "yes" ]]; then
    rm -rf "${INSTALL_DIR}"
else
    log "Project files and runtime data kept in ${INSTALL_DIR}."
    log "To remove everything: DELETE_DATA=yes ./install/uninstall.sh"
fi

log "RouteCollector service removed."
