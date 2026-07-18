#!/usr/bin/env bash

set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/routecollector}"
ROUTECOLLECTOR_REF="${ROUTECOLLECTOR_REF:-main}"
RUN_USER="${RUN_USER:-root}"

SERVICE_NAME="routecollector.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
GLOBAL_COMMAND="/usr/local/bin/routecollector"

OLD_COMMIT=""
SERVICE_WAS_ACTIVE="no"
SERVICE_BACKUP=""
DATABASE_BACKUP=""
UPGRADE_COMPLETED="no"

log() {
    printf '[routecollector] %s\n' "$*"
}

fail() {
    printf '[routecollector] ERROR: %s\n' "$*" >&2
    exit 1
}

checkout_ref() {
    local ref="$1"

    git -C "${INSTALL_DIR}" fetch --tags --prune origin

    if git -C "${INSTALL_DIR}" show-ref \
        --verify --quiet "refs/remotes/origin/${ref}"; then
        git -C "${INSTALL_DIR}" switch -C "${ref}" "origin/${ref}"
        return
    fi

    if git -C "${INSTALL_DIR}" show-ref \
        --verify --quiet "refs/tags/${ref}"; then
        git -C "${INSTALL_DIR}" checkout --detach "refs/tags/${ref}"
        return
    fi

    if git -C "${INSTALL_DIR}" rev-parse \
        --verify --quiet "${ref}^{commit}" >/dev/null; then
        git -C "${INSTALL_DIR}" checkout --detach "${ref}"
        return
    fi

    fail "Git reference not found: ${ref}"
}

write_global_command() {
    cat > "${GLOBAL_COMMAND}" <<EOF
#!/usr/bin/env bash
set -e

cd "${INSTALL_DIR}"
exec "${INSTALL_DIR}/.venv/bin/routecollector" "\$@"
EOF

    chmod 755 "${GLOBAL_COMMAND}"
}

write_systemd_unit() {
    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=RouteCollector BGP Route Intelligence Daemon
Documentation=https://github.com/bagaMann/routecollector
Wants=network-online.target
After=network-online.target bird.service
Requires=bird.service

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/routecollector daemon \\
    --interval 1800 \\
    --lock-file ${INSTALL_DIR}/state/routecollector.lock \\
    --min-confidence-ipv4 60 \\
    --min-confidence-ipv6 60 \\
    --max-age-days 30
Restart=on-failure
RestartSec=15
KillSignal=SIGTERM
TimeoutStopSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
}

restore_previous_version() {
    local exit_code="$1"

    [[ "${UPGRADE_COMPLETED}" == "yes" ]] && return

    printf '\n' >&2
    log "Upgrade failed; restoring the previous installation."

    if [[ -n "${OLD_COMMIT}" ]]; then
        git -C "${INSTALL_DIR}" reset --hard "${OLD_COMMIT}" \
            || true

        "${INSTALL_DIR}/.venv/bin/python" \
            -m pip install -e "${INSTALL_DIR}" \
            || true
    fi

    if [[ -n "${SERVICE_BACKUP}" && -f "${SERVICE_BACKUP}" ]]; then
        cp -a "${SERVICE_BACKUP}" "${SERVICE_FILE}" || true
    fi

    systemctl daemon-reload || true

    if [[ "${SERVICE_WAS_ACTIVE}" == "yes" ]]; then
        systemctl restart "${SERVICE_NAME}" || true
    fi

    if [[ -n "${DATABASE_BACKUP}" ]]; then
        log "Database backup retained at ${DATABASE_BACKUP}."
    fi

    exit "${exit_code}"
}

main() {
    [[ "${EUID}" -eq 0 ]] \
        || fail "Run this script as root."

    [[ -d "${INSTALL_DIR}/.git" ]] \
        || fail "Git checkout not found in ${INSTALL_DIR}."

    [[ -x "${INSTALL_DIR}/.venv/bin/python" ]] \
        || fail "Virtual environment not found."

    [[ -z "$(git -C "${INSTALL_DIR}" status --porcelain)" ]] \
        || fail "Working tree contains uncommitted changes."

    OLD_COMMIT="$(git -C "${INSTALL_DIR}" rev-parse HEAD)"

    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        SERVICE_WAS_ACTIVE="yes"
    fi

    mkdir -p "${INSTALL_DIR}/state/backups"

    if [[ -f "${INSTALL_DIR}/state/state.db" ]]; then
        DATABASE_BACKUP="${INSTALL_DIR}/state/backups/state-$(date +%Y%m%d-%H%M%S).db"
        cp -a \
            "${INSTALL_DIR}/state/state.db" \
            "${DATABASE_BACKUP}"
        log "Database backup created: ${DATABASE_BACKUP}"
    fi

    if [[ -f "${SERVICE_FILE}" ]]; then
        SERVICE_BACKUP="${INSTALL_DIR}/state/backups/routecollector.service-$(date +%Y%m%d-%H%M%S)"
        cp -a "${SERVICE_FILE}" "${SERVICE_BACKUP}"
    fi

    trap 'restore_previous_version $?' ERR INT TERM

    systemctl stop "${SERVICE_NAME}" || true

    checkout_ref "${ROUTECOLLECTOR_REF}"

    "${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
    "${INSTALL_DIR}/.venv/bin/python" -m pip install -e "${INSTALL_DIR}"

    write_global_command
    write_systemd_unit
    systemctl daemon-reload

    cd "${INSTALL_DIR}"

    "${INSTALL_DIR}/.venv/bin/routecollector" init

    if [[ -x "${INSTALL_DIR}/.venv/bin/ruff" ]]; then
        "${INSTALL_DIR}/.venv/bin/ruff" check .
    fi

    if [[ -x "${INSTALL_DIR}/.venv/bin/pytest" ]]; then
        "${INSTALL_DIR}/.venv/bin/pytest" -q
    fi

    "${INSTALL_DIR}/.venv/bin/routecollector" run-once \
        --min-confidence-ipv4 60 \
        --min-confidence-ipv6 60

    systemctl enable "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"

    systemctl is-active --quiet "${SERVICE_NAME}" \
        || fail "RouteCollector failed to start after upgrade."

    "${INSTALL_DIR}/.venv/bin/routecollector" doctor

    UPGRADE_COMPLETED="yes"
    trap - ERR INT TERM

    log "Upgrade completed successfully."
    "${INSTALL_DIR}/.venv/bin/routecollector" --quiet version
    log "Installed Git ref: ${ROUTECOLLECTOR_REF}"
}

main "$@"
