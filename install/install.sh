#!/usr/bin/env bash

set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/routecollector}"
REPO_URL="${REPO_URL:-https://github.com/bagaMann/routecollector.git}"
ROUTECOLLECTOR_REF="${ROUTECOLLECTOR_REF:-main}"
RUN_USER="${RUN_USER:-root}"

SERVICE_NAME="routecollector.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
BIRD_MAIN_CONFIG="/etc/bird/bird.conf"
BIRD_INCLUDE_CONFIG="/etc/bird/routecollector.conf"
GLOBAL_COMMAND="/usr/local/bin/routecollector"

log() {
    printf '[routecollector] %s\n' "$*"
}

fail() {
    printf '[routecollector] ERROR: %s\n' "$*" >&2
    exit 1
}

require_root() {
    [[ "${EUID}" -eq 0 ]] || fail "Run this installer as root."
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

ensure_bird_include() {
    local include_line='include "/etc/bird/routecollector.conf";'

    [[ -f "${BIRD_MAIN_CONFIG}" ]] \
        || fail "BIRD configuration not found: ${BIRD_MAIN_CONFIG}"

    grep -Fqx "${include_line}" "${BIRD_MAIN_CONFIG}" \
        || printf '\n%s\n' "${include_line}" >> "${BIRD_MAIN_CONFIG}"
}

print_summary() {
    printf '\n'
    printf '%s\n' '============================================'
    printf '%s\n' 'RouteCollector installation completed'
    printf '%s\n' '============================================'
    printf '\n'

    cd "${INSTALL_DIR}"

    "${INSTALL_DIR}/.venv/bin/routecollector" --quiet version

    printf '\n'
    printf '%s\n' 'Installation status'
    printf '%s\n' '-------------------'
    "${INSTALL_DIR}/.venv/bin/routecollector" --quiet status

    printf '\n'
    printf '%s\n' 'Doctor'
    printf '%s\n' '------'
    "${INSTALL_DIR}/.venv/bin/routecollector" doctor

    printf '\n'
    printf '%s\n' 'System services'
    printf '%s\n' '---------------'
    printf 'BIRD               : %s\n' "$(systemctl is-active bird)"
    printf 'RouteCollector     : %s\n' \
        "$(systemctl is-active "${SERVICE_NAME}")"

    printf '\n'
    printf '%s\n' 'Paths'
    printf '%s\n' '-----'
    printf 'Installation       : %s\n' "${INSTALL_DIR}"
    printf 'Configuration      : %s\n' "${INSTALL_DIR}/config"
    printf 'Database           : %s\n' "${INSTALL_DIR}/state/state.db"
    printf 'BIRD configuration : %s\n' "${BIRD_INCLUDE_CONFIG}"
    printf 'Global command     : %s\n' "${GLOBAL_COMMAND}"

    printf '\n'
    printf '%s\n' 'Useful commands'
    printf '%s\n' '---------------'
    printf 'routecollector status\n'
    printf 'routecollector doctor\n'
    printf 'routecollector run-once --dry-run\n'
    printf 'routecollector history --limit 5\n'
    printf 'systemctl status routecollector.service\n'
    printf 'journalctl -u routecollector.service -f\n'
    printf 'birdc show protocols\n'

    printf '\n'
    printf 'Installed Git ref  : %s\n' "${ROUTECOLLECTOR_REF}"
    printf '%s\n' '============================================'
    printf '%s\n' 'RouteCollector is ready for operation.'
    printf '%s\n' '============================================'
}

main() {
    require_root

    export DEBIAN_FRONTEND=noninteractive

    log "Installing system packages."
    apt-get update
    apt-get install -y \
        bird2 \
        git \
        sqlite3 \
        python3 \
        python3-pip \
        python3-venv \
        ca-certificates

    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        [[ -z "$(git -C "${INSTALL_DIR}" status --porcelain)" ]] \
            || fail "Existing checkout has uncommitted changes."
        checkout_ref "${ROUTECOLLECTOR_REF}"
    else
        mkdir -p "$(dirname "${INSTALL_DIR}")"
        git clone "${REPO_URL}" "${INSTALL_DIR}"
        checkout_ref "${ROUTECOLLECTOR_REF}"
    fi

    log "Creating Python virtual environment."
    python3 -m venv "${INSTALL_DIR}/.venv"
    "${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
    "${INSTALL_DIR}/.venv/bin/python" -m pip install -e "${INSTALL_DIR}"

    write_global_command

    mkdir -p \
        "${INSTALL_DIR}/state" \
        "${INSTALL_DIR}/state/plans" \
        "${INSTALL_DIR}/state/backups" \
        "${INSTALL_DIR}/logs" \
        "${INSTALL_DIR}/cache" \
        "${INSTALL_DIR}/bird"

    ensure_bird_include
    write_systemd_unit

    systemctl daemon-reload
    systemctl enable --now bird

    cd "${INSTALL_DIR}"

    "${INSTALL_DIR}/.venv/bin/routecollector" init
    "${INSTALL_DIR}/.venv/bin/routecollector" sync
    "${INSTALL_DIR}/.venv/bin/routecollector" run-once \
        --min-confidence-ipv4 60 \
        --min-confidence-ipv6 60

    systemctl enable --now "${SERVICE_NAME}"

    systemctl is-active --quiet bird \
        || fail "BIRD is not active."

    systemctl is-active --quiet "${SERVICE_NAME}" \
        || fail "RouteCollector is not active."

    print_summary
}

main "$@"
