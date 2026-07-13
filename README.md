# RouteCollector

**RouteCollector** is a DNS-driven route intelligence service for building and publishing dynamic network prefixes to **BIRD 2**.

It synchronizes domain lists for configured services, resolves them through multiple DNS servers, stores observations in SQLite, aggregates evidence into IPv4/IPv6 prefixes, calculates confidence and publication scores, generates a BIRD configuration, validates it, and reloads BIRD only when the published route set has changed.

Current stable release: **v1.1.1**

## Why RouteCollector

Selective routing by domain name is difficult because routers work with IP prefixes while modern services use changing CDN addresses. RouteCollector bridges that gap:

```text
service YAML
    -> domain sources
    -> DNS A/AAAA observations
    -> SQLite evidence
    -> /24 and /48 statistics
    -> confidence + source trust + publish score
    -> BIRD static routes
    -> BGP advertisement to routers
```

The project was originally created for selective routing of YouTube traffic and evolved into a generic engine that can handle any service described by a YAML file.

## Features

- Multiple services and multiple domain sources.
- Manual domain lists and Domain List Community integration.
- DNS resolution through multiple resolvers.
- Deduplicated domain queries with provenance preserved.
- Batch SQLite writes for fast first-run processing.
- IPv4 enabled by default; IPv6 available with `--enable-ipv6`.
- Prefix aggregation: IPv4 `/24`, IPv6 `/48` by default.
- Filtering of private, loopback, link-local, multicast, reserved, and other non-global addresses.
- Confidence scoring based on independent evidence and observation age.
- Source trust and bounded publication scoring.
- Configurable publication threshold, default `60`.
- Atomic BIRD configuration installation with backup and rollback.
- BIRD validation before reload.
- No reload when generated routes have not changed.
- Continuous daemon mode with a lock file and graceful shutdown.
- Debian installer, upgrade script, and uninstaller.
- Global `routecollector` command wrapper.
- Quiet mode for scripts and monitoring.
- Automated test suite covering core behavior.

## Supported services included

The repository currently includes service definitions for:

- YouTube
- Discord
- Telegram

Adding another service normally requires only one YAML file; no Python changes are required.

## Requirements

- Debian 12 or 13
- Python 3.11 or newer
- BIRD 2
- systemd
- SQLite 3
- Internet access for DNS resolution and external domain-list sources
- Root privileges for installation and BIRD integration

## Quick installation

```bash
git clone https://github.com/bagamann/routecollector.git
cd routecollector
sudo ./install/install.sh
```

The installer:

1. Installs BIRD 2, Python, Git, SQLite, and required packages.
2. Clones or updates RouteCollector in `/opt/routecollector`.
3. Creates `/opt/routecollector/.venv`.
4. Installs the Python package and dependencies.
5. Creates the global `/usr/local/bin/routecollector` wrapper.
6. Initializes SQLite.
7. Synchronizes services and domains.
8. Runs the first collection cycle.
9. Installs and validates `/etc/bird/routecollector.conf`.
10. Installs and starts the systemd daemon.
11. Prints a complete installation summary.

## Verify the installation

```bash
routecollector --quiet status
routecollector --quiet plan
systemctl status routecollector.service
sudo birdc configure check
sudo birdc show protocols
sudo birdc show route protocol routecollector_static
```

## Main commands

```text
routecollector version                 Show version and platform
routecollector status                  Check configuration, logger, and database
routecollector init                    Initialize or migrate SQLite
routecollector sync                    Synchronize service definitions
routecollector resolve [service]       Resolve all or one service
routecollector stats                   Rebuild prefix statistics
routecollector plan                    Show publishable routes
routecollector export                  Generate BIRD configuration
routecollector bird-check              Validate BIRD configuration
routecollector install-bird-config     Install generated BIRD config
routecollector bird-reload             Apply BIRD configuration
routecollector run-once [service]      Execute a complete cycle
routecollector daemon                  Run continuously
```

Use quiet mode before the command:

```bash
routecollector --quiet status
routecollector --quiet plan
```

## IPv6

IPv6 is implemented but disabled by default.

```bash
routecollector plan --enable-ipv6
routecollector resolve telegram --enable-ipv6
routecollector run-once --enable-ipv6
```

The systemd service does not enable IPv6 unless `--enable-ipv6` is added to `ExecStart`.

## Publication policy

A route is published only when:

- the address is globally routable;
- the prefix has a valid `last_seen` timestamp;
- the observation is not older than `--max-age-days`;
- IPv6 is enabled for an IPv6 route;
- its publication score meets the family threshold.

Default thresholds:

```text
IPv4 publish score: 60
IPv6 publish score: 60
Maximum route age:  30 days
```

The publication score is bounded to 100 and combines:

```text
publish_score = confidence + floor(source_trust / 5) + min(source_count * 3, 15)
```

## Add a new service

Create `config/services/example.yaml`:

```yaml
name: example
description: Example service
enabled: true

sources:
  - manual
  - domain-list-community

domain_list_community:
  lists:
    - example

domains:
  - example.com
  - cdn.example.com
  - api.example.com
```

Then run:

```bash
routecollector sync
routecollector resolve example
routecollector stats
routecollector plan
```

For a complete production cycle:

```bash
sudo routecollector run-once
```

## Configuration and paths

```text
/opt/routecollector/                     Installed project
/opt/routecollector/config/config.yaml   Main application config
/opt/routecollector/config/services/     Service YAML files
/opt/routecollector/state/state.db       SQLite database
/opt/routecollector/logs/                 Application logs
/opt/routecollector/bird/                 Generated BIRD config
/etc/bird/routecollector.conf             Installed BIRD config
/etc/systemd/system/routecollector.service
/usr/local/bin/routecollector             Global wrapper
```

## Daemon and logs

The default daemon interval is 1800 seconds.

```bash
systemctl status routecollector.service
sudo journalctl -u routecollector.service -f
sudo systemctl restart routecollector.service
```

A daemon cycle performs:

```text
sync -> resolve -> rebuild statistics -> plan -> export -> install -> check -> reload if changed
```

## Upgrade

```bash
sudo /opt/routecollector/install/upgrade.sh
```

The upgrade script stops the daemon, backs up the database, fast-forwards the Git checkout, reinstalls the package, restores the global wrapper, initializes migrations, runs checks when available, performs a safe collection cycle, and starts the daemon again.

## Uninstall

Remove systemd integration and the global command while keeping project data:

```bash
sudo /opt/routecollector/install/uninstall.sh
```

Remove everything, including the database and logs:

```bash
sudo DELETE_DATA=yes /opt/routecollector/install/uninstall.sh
```

## Development

```bash
git clone https://github.com/bagamann/routecollector.git
cd routecollector
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest -q
```

## Safety model

RouteCollector refuses to export an empty route plan. BIRD configuration is installed atomically, validated before reload, backed up when replaced, and rolled back if validation or reload fails. Runtime files, logs, databases, virtual environments, and Python caches are excluded from Git.

## Project layout

```text
routecollector/
├── config/
│   ├── config.yaml
│   └── services/
├── install/
│   ├── install.sh
│   ├── upgrade.sh
│   └── uninstall.sh
├── routecollector/
│   ├── core/
│   ├── exporter/
│   ├── parser/
│   ├── planner/
│   ├── policy/
│   ├── resolver/
│   ├── sources/
│   └── workflow/
├── scripts/
├── tests/
├── pyproject.toml
└── README.md
```

## License

See [LICENSE](LICENSE).
