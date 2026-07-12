#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="routecollector"
INSTALL_DIR="${INSTALL_DIR:-/opt/routecollector}"
REPO_URL="${REPO_URL:-https://github.com/bagamann/routecollector.git}"
SERVICE_FILE="/etc/systemd/system/routecollector.service"
BIRD_MAIN_CONFIG="/etc/bird/bird.conf"
RUN_USER="${RUN_USER:-root}"

log() { printf '[routecollector] %s\n' "$*"; }
fail() { printf '[routecollector] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run this installer as root."

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y bird2 git sqlite3 python3 python3-pip python3-venv ca-certificates

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    git -C "${INSTALL_DIR}" fetch --tags origin
    git -C "${INSTALL_DIR}" pull --ff-only
else
    mkdir -p "$(dirname "${INSTALL_DIR}")"
    git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -e "${INSTALL_DIR}"

cat > /usr/local/bin/routecollector <<EOF
#!/usr/bin/env bash
set -e

cd "${INSTALL_DIR}"
exec "${INSTALL_DIR}/.venv/bin/routecollector" "\$@"
EOF

chmod 755 /usr/local/bin/routecollector

mkdir -p "${INSTALL_DIR}/state" "${INSTALL_DIR}/logs" "${INSTALL_DIR}/cache" "${INSTALL_DIR}/bird"

include_line='include "/etc/bird/routecollector.conf";'
grep -Fqx "${include_line}" "${BIRD_MAIN_CONFIG}" || printf '\n%s\n' "${include_line}" >> "${BIRD_MAIN_CONFIG}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=RouteCollector BGP Route Intelligence Daemon
Documentation=https://github.com/bagamann/routecollector
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

systemctl daemon-reload
systemctl enable --now bird

cd "${INSTALL_DIR}"
"${INSTALL_DIR}/.venv/bin/routecollector" init
"${INSTALL_DIR}/.venv/bin/routecollector" sync
"${INSTALL_DIR}/.venv/bin/routecollector" run-once     --min-confidence-ipv4 60     --min-confidence-ipv6 60

systemctl enable --now routecollector.service

systemctl is-active --quiet bird || fail "BIRD is not active."
systemctl is-active --quiet routecollector.service || fail "RouteCollector is not active."

printf '\n============================================\n'
printf 'RouteCollector installation completed.\n'
printf 'Install directory : %s\n' "${INSTALL_DIR}"
printf 'BIRD service      : active\n'
printf 'RouteCollector    : active\n'
printf 'Logs              : journalctl -u routecollector.service -f\n'
printf '============================================\n'
