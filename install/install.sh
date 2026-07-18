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

detect_local_repository() {
    local script_path script_dir repository_root

    script_path="${BASH_SOURCE[0]}"
    [[ -f "${script_path}" ]] || return 1

    script_dir="$(
        cd "$(dirname "${script_path}")"
        pwd
    )"

    repository_root="$(
        git -C "${script_dir}" rev-parse             --show-toplevel 2>/dev/null || true
    )"

    [[ -n "${repository_root}" ]] || return 1
    printf '%s\n' "${repository_root}"
}

checkout_ref() {
    local repository="$1"
    local ref="$2"

    git -C "${repository}" fetch --tags --prune origin

    if git -C "${repository}" show-ref         --verify --quiet "refs/remotes/origin/${ref}"; then
        git -C "${repository}" switch -C             "${ref}"             "origin/${ref}"
        return
    fi

    if git -C "${repository}" show-ref         --verify --quiet "refs/tags/${ref}"; then
        git -C "${repository}" checkout             --detach             "refs/tags/${ref}"
        return
    fi

    if git -C "${repository}" rev-parse         --verify --quiet "${ref}^{commit}" >/dev/null; then
        git -C "${repository}" checkout             --detach             "${ref}"
        return
    fi

    fail "Git reference not found: ${ref}"
}

prepare_repository() {
    local local_repository

    local_repository="$(
        detect_local_repository || true
    )"

    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        log "Using existing installation repository: ${INSTALL_DIR}"

        [[ -z "$(
            git -C "${INSTALL_DIR}" status --porcelain
        )" ]] || fail             "Existing checkout contains uncommitted changes."

        checkout_ref             "${INSTALL_DIR}"             "${ROUTECOLLECTOR_REF}"

        return
    fi

    if [[ -e "${INSTALL_DIR}" ]]; then
        [[ -d "${INSTALL_DIR}" ]] || fail             "Installation path exists and is not a directory: ${INSTALL_DIR}"

        [[ -z "$(find "${INSTALL_DIR}" -mindepth 1 -print -quit)" ]]             || fail                 "Installation directory exists and is not empty: ${INSTALL_DIR}"
    else
        mkdir -p "$(dirname "${INSTALL_DIR}")"
    fi

    if [[ -n "${local_repository}" ]]; then
        log "Installing from local Git repository: ${local_repository}"

        [[ -z "$(
            git -C "${local_repository}" status --porcelain
        )" ]] || fail             "Local repository contains uncommitted changes."

        git clone             --no-local             "${local_repository}"             "${INSTALL_DIR}"

        if git -C "${local_repository}" remote get-url origin             >/dev/null 2>&1; then
            git -C "${INSTALL_DIR}" remote set-url origin                 "$(
                    git -C "${local_repository}" remote get-url origin
                )"
        fi
    else
        log "Cloning RouteCollector from ${REPO_URL}"

        git clone             "${REPO_URL}"             "${INSTALL_DIR}"
    fi

    checkout_ref         "${INSTALL_DIR}"         "${ROUTECOLLECTOR_REF}"
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
ExecStart=${INSTALL_DIR}/.venv/bin/routecollector daemon \
    --interval 1800 \
    --lock-file ${INSTALL_DIR}/state/routecollector.lock \
    --min-confidence-ipv4 60 \
    --min-confidence-ipv6 60 \
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
    local include_line

    include_line='include "/etc/bird/routecollector.conf";'

    [[ -f "${BIRD_MAIN_CONFIG}" ]] || fail         "BIRD configuration not found: ${BIRD_MAIN_CONFIG}"

    if ! grep -Fqx "${include_line}" "${BIRD_MAIN_CONFIG}"; then
        printf '\n%s\n' "${include_line}"             >> "${BIRD_MAIN_CONFIG}"
    fi
}

create_runtime_directories() {
    mkdir -p         "${INSTALL_DIR}/state"         "${INSTALL_DIR}/state/plans"         "${INSTALL_DIR}/state/backups"         "${INSTALL_DIR}/logs"         "${INSTALL_DIR}/cache"         "${INSTALL_DIR}/bird"
}

install_python_package() {
    log "Creating Python virtual environment."

    python3 -m venv "${INSTALL_DIR}/.venv"

    "${INSTALL_DIR}/.venv/bin/python"         -m pip install --upgrade pip

    "${INSTALL_DIR}/.venv/bin/python"         -m pip install -e "${INSTALL_DIR}"
}

initialize_routecollector() {
    cd "${INSTALL_DIR}"

    "${INSTALL_DIR}/.venv/bin/routecollector" init
    "${INSTALL_DIR}/.venv/bin/routecollector" sync

    "${INSTALL_DIR}/.venv/bin/routecollector" run-once         --min-confidence-ipv4 60         --min-confidence-ipv6 60
}

verify_installation() {
    systemctl is-active --quiet bird || fail         "BIRD is not active."

    systemctl is-active --quiet "${SERVICE_NAME}" || fail         "RouteCollector is not active."

    cd "${INSTALL_DIR}"
    "${INSTALL_DIR}/.venv/bin/routecollector" doctor
}

print_summary() {
    local installed_commit

    installed_commit="$(
        git -C "${INSTALL_DIR}" rev-parse --short HEAD
    )"

    printf '\n'
    printf '%s\n' '============================================'
    printf '%s\n' 'RouteCollector installation completed'
    printf '%s\n' '============================================'
    printf '\n'

    cd "${INSTALL_DIR}"
    "${INSTALL_DIR}/.venv/bin/routecollector" --quiet version

    printf '\n'
    printf 'Installed Git ref     : %s\n' "${ROUTECOLLECTOR_REF}"
    printf 'Installed Git commit  : %s\n' "${installed_commit}"
    printf 'Installation directory: %s\n' "${INSTALL_DIR}"
    printf 'Database              : %s\n'         "${INSTALL_DIR}/state/state.db"
    printf 'BIRD configuration    : %s\n' "${BIRD_INCLUDE_CONFIG}"
    printf 'Global command        : %s\n' "${GLOBAL_COMMAND}"

    printf '\n'
    printf '%s\n' 'Useful commands'
    printf '%s\n' '---------------'
    printf '%s\n' 'routecollector status'
    printf '%s\n' 'routecollector doctor'
    printf '%s\n' 'routecollector run-once --dry-run'
    printf '%s\n' 'routecollector history --limit 5'
    printf '%s\n' 'systemctl status routecollector.service'
    printf '%s\n' 'journalctl -u routecollector.service -f'
    printf '%s\n' 'birdc show protocols'

    printf '\n'
    printf '%s\n' 'RouteCollector is ready for operation.'
}

main() {
    require_root

    export DEBIAN_FRONTEND=noninteractive

    log "Installing required system packages."

    apt-get update

    apt-get install -y         bird2         ca-certificates         curl         git         python3         python3-pip         python3-venv         sqlite3

    prepare_repository
    create_runtime_directories
    install_python_package
    write_global_command
    ensure_bird_include
    write_systemd_unit

    systemctl daemon-reload
    systemctl enable --now bird

    initialize_routecollector

    systemctl enable "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"

    verify_installation
    print_summary
}

main "$@"
