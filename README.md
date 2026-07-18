# RouteCollector

**RouteCollector** is a DNS-driven route intelligence service that builds and publishes dynamic IP prefixes through **BIRD 2**.

It synchronizes domain names from pluggable sources, resolves them through DNS, stores observations in SQLite, calculates route statistics and publication scores, generates a BIRD configuration, validates it, and reloads BIRD only when the published route set changes.

Current release: **v1.2.0**

---

## Why RouteCollector

Routers make decisions using IP addresses and prefixes, while modern services are normally identified by domain names and frequently move between CDN nodes.

RouteCollector bridges that gap:

```text
Service YAML
    ↓
Domain source plugins
    ↓
DNS A / AAAA observations
    ↓
SQLite evidence
    ↓
Prefix statistics
    ↓
Confidence and publication policy
    ↓
BIRD static routes
    ↓
BGP advertisement
    ↓
Routers
```

The project was initially created for selective routing of YouTube traffic and evolved into a generic route collection platform for any service described by YAML configuration.

---

## Features

- Multiple independently configured services.
- Declarative YAML service configuration.
- Pluggable domain source architecture.
- Built-in `manual`, `http-text`, and `domain-list-community` sources.
- External Python plugins discovered through entry points.
- Source provenance retained when domains overlap.
- Automatic deactivation of stale domains and removed services.
- Multiple DNS resolvers.
- Batched SQLite observation writes.
- IPv4 enabled by default.
- Optional IPv6 resolution and publication.
- IPv4 `/24` and IPv6 `/48` prefix statistics by default.
- Filtering of non-global, private, loopback, multicast, link-local, reserved, and other unsuitable addresses.
- Confidence, source trust, and bounded publication scoring.
- Configurable publication thresholds and maximum observation age.
- Atomic BIRD configuration installation.
- BIRD syntax validation before publication.
- Automatic backup and rollback when BIRD reload fails.
- No BIRD reload when the route set is unchanged.
- Safe `--dry-run` mode.
- Route plan snapshots and route membership comparison.
- Successful cycle history stored in SQLite.
- Continuous systemd daemon mode with lock protection.
- Read-only `routecollector doctor` diagnostics.
- Debian installer, upgrade script, and uninstaller.
- Automated test suite.

---

## Included service configurations

The repository currently includes service definitions for:

- YouTube
- Discord
- Telegram

Adding another service normally requires only one YAML file. Core Python changes are not required.

---

## Requirements

- Debian 12 or Debian 13
- Python 3.11 or newer
- BIRD 2
- systemd
- SQLite 3
- Internet access for DNS resolution and remote domain sources
- Root privileges for installation and BIRD integration

---

## Installation

Clone the repository and run the installer:

```bash
git clone https://github.com/bagaMann/routecollector.git
cd routecollector
sudo ./install/install.sh
```

The installer:

1. Installs BIRD 2, Python, Git, SQLite, and required system packages.
2. Installs RouteCollector in `/opt/routecollector`.
3. Creates the Python virtual environment.
4. Installs RouteCollector and its dependencies.
5. Creates the global `/usr/local/bin/routecollector` command.
6. Initializes or migrates the SQLite database.
7. Synchronizes configured services.
8. Runs the first collection cycle.
9. Generates and installs the BIRD configuration.
10. Validates BIRD before applying changes.
11. Installs and starts `routecollector.service`.
12. Prints an installation and runtime summary.

Verify the installation:

```bash
routecollector version
routecollector status
routecollector doctor
systemctl status routecollector.service
birdc show protocols
```

---

## Upgrade

Upgrade an existing installation:

```bash
sudo /opt/routecollector/install/upgrade.sh
```

The upgrade process preserves runtime state, updates the Git checkout, reinstalls the package, initializes database migrations, performs validation, runs a safe collection cycle, and restarts the daemon.

---

## Uninstall

Remove systemd integration and the global command while retaining project data:

```bash
sudo /opt/routecollector/install/uninstall.sh
```

Remove the installation including runtime data:

```bash
sudo DELETE_DATA=yes /opt/routecollector/install/uninstall.sh
```

---

## Main commands

```text
routecollector version
    Show RouteCollector, Python, and platform versions.

routecollector status
    Check application configuration, logger, and database initialization.

routecollector doctor
    Run read-only diagnostics for the complete installation.

routecollector init
    Initialize or migrate the SQLite database.

routecollector sync
    Synchronize service YAML and domain source data.

routecollector sources
    Show available source plugins and configured usage.

routecollector plugin-info
    Show source origin, package, version, and entry-point metadata.

routecollector resolve [service]
    Resolve all configured domains or one service.

routecollector stats
    Rebuild and display prefix statistics.

routecollector plan
    Build and display the publishable route plan.

routecollector changes
    Compare the two latest successful route plan snapshots.

routecollector history
    Display successful collection cycle history.

routecollector export
    Generate the local BIRD configuration.

routecollector bird-check
    Validate the BIRD configuration.

routecollector install-bird-config
    Atomically install the generated BIRD configuration.

routecollector bird-reload
    Validate and apply the BIRD configuration.

routecollector run-once [service]
    Run one complete update cycle.

routecollector run-once --dry-run
    Preview the complete cycle without installing BIRD configuration,
    reloading BIRD, or modifying snapshots and cycle history.

routecollector daemon
    Run RouteCollector continuously.
```

Display all options:

```bash
routecollector --help
routecollector run-once --help
routecollector history --help
```

Suppress informational application log messages:

```bash
routecollector --quiet status
routecollector --quiet plan
```

---

## Complete collection cycle

A normal cycle performs:

```text
sync
  ↓
resolve
  ↓
store DNS observations
  ↓
rebuild route statistics
  ↓
build route plan
  ↓
generate BIRD configuration
  ↓
install only when changed
  ↓
validate BIRD
  ↓
reload only when required
  ↓
store route plan snapshot
  ↓
store successful cycle history
```

Run one cycle manually:

```bash
sudo routecollector run-once
```

Preview without publishing:

```bash
sudo routecollector run-once --dry-run
```

Dry-run does not install BIRD configuration, reload BIRD, create a route plan snapshot, or add a cycle history record. DNS observations and route statistics are still refreshed so the preview uses current data.

---

## Service configuration

Service definitions are stored in:

```text
config/services/*.yaml
```

Example:

```yaml
name: youtube
description: YouTube video platform
enabled: true

sources:
  - type: manual
    domains:
      - youtube.com
      - youtu.be
      - youtube-nocookie.com
      - googlevideo.com
      - ytimg.com
      - ggpht.com
      - youtubei.googleapis.com
      - youtube.googleapis.com

  - type: domain-list-community
    list: youtube
```

After adding or changing a service:

```bash
routecollector sync
routecollector run-once --dry-run
```

Publish after reviewing the result:

```bash
sudo routecollector run-once
```

When a service YAML file is removed, RouteCollector disables the corresponding database service and deactivates its domain rows. Historical data is retained.

---

## Built-in source plugins

### manual

Defines domains directly in service YAML:

```yaml
sources:
  - type: manual
    domains:
      - example.com
      - api.example.com
      - cdn.example.com
```

### domain-list-community

Loads a named list from v2fly Domain List Community:

```yaml
sources:
  - type: domain-list-community
    list: youtube
```

### http-text

Loads domains from an HTTP or HTTPS text file:

```yaml
sources:
  - type: http-text
    url: https://raw.githubusercontent.com/example/project/main/domains.txt
    timeout: 20
```

Supported input includes plain domain lists and common hosts-file formatting.

---

## External source plugins

RouteCollector discovers external source packages through the Python entry-point group:

```toml
[project.entry-points."routecollector.sources"]
example = "routecollector_source_example:ExampleSource"
```

Install an external plugin into the RouteCollector virtual environment:

```bash
/opt/routecollector/.venv/bin/python -m pip install \
  routecollector-source-example
```

For development:

```bash
/opt/routecollector/.venv/bin/python -m pip install -e \
  /path/to/routecollector-source-example
```

Use it in YAML:

```yaml
name: example-service
enabled: true

sources:
  - type: example
    domains:
      - example.com
      - cdn.example.com
```

Inspect available plugins:

```bash
routecollector sources
routecollector plugin-info
```

External plugins extend RouteCollector without modifying core code.

---

## DNS resolution and IPv6

Resolve all active configured domains:

```bash
routecollector resolve
```

Resolve one service:

```bash
routecollector resolve youtube
```

Enable AAAA resolution and IPv6 publication:

```bash
routecollector resolve --enable-ipv6
routecollector plan --enable-ipv6
routecollector run-once --enable-ipv6
```

IPv6 is disabled by default. To enable it in daemon mode, add `--enable-ipv6` to `ExecStart`.

Default aggregation:

```text
IPv4: /24
IPv6: /48
```

---

## Publication policy

A route is publishable only when:

- the address is globally routable;
- a valid `last_seen` value exists;
- the observation is not older than the configured maximum age;
- IPv6 publication is enabled for IPv6 routes;
- the publication score meets the selected family threshold.

Default values:

```text
IPv4 minimum publish score: 60
IPv6 minimum publish score: 60
Maximum route age:          30 days
```

Inspect the current route plan:

```bash
routecollector plan
```

Override policy values:

```bash
routecollector plan \
  --min-confidence-ipv4 70 \
  --max-age-days 14
```

---

## Route snapshots and changes

Every successful non-dry-run cycle stores a JSON route plan snapshot in:

```text
state/plans/
```

Compare the two latest snapshots:

```bash
routecollector changes
```

Snapshot retention is enforced automatically.

---

## Cycle history

Successful cycles are stored in SQLite table `cycle_history`.

```bash
routecollector history
routecollector history --limit 5
```

History includes completion time, duration, selected service, synchronized domains, DNS observations, route statistics, planned routes, route changes, and BIRD reload state.

Dry-run cycles are not written to history.

---

## Doctor diagnostics

Run complete read-only diagnostics:

```bash
routecollector doctor
```

The command checks:

- Python and RouteCollector versions;
- main configuration;
- required directories and permissions;
- SQLite accessibility and schema;
- database table counts;
- service YAML validity;
- configured source definitions;
- built-in and external plugin availability;
- configured source type coverage;
- BIRD and `birdc` binaries;
- main, generated, and installed BIRD configuration files;
- BIRD configuration parsing;
- systemd service enablement and active state;
- route plan snapshots;
- successful cycle history.

Exit codes:

```text
0  HEALTHY
1  WARNING
2  FAILED
```

The command is read-only. It does not synchronize sources, resolve domains, write to SQLite, install configuration, or reload BIRD.

---

## BIRD integration

Generated configuration:

```text
bird/routecollector.conf
```

Installed configuration:

```text
/etc/bird/routecollector.conf
```

Useful commands:

```bash
bird -p -c /etc/bird/bird.conf
birdc show protocols
birdc show route protocol routecollector_static
```

RouteCollector installs configuration atomically and reloads BIRD only when the effective route set changes.

---

## Daemon and logs

The default daemon interval is 1800 seconds.

```bash
systemctl status routecollector.service
sudo systemctl restart routecollector.service
journalctl -u routecollector.service -f
journalctl -u routecollector.service -n 100 --no-pager
```

The daemon uses a lock file to prevent overlapping instances and supports graceful shutdown.

---

## Important paths

```text
/opt/routecollector/                     Installed project
/opt/routecollector/config/config.yaml  Main configuration
/opt/routecollector/config/services/    Service YAML files
/opt/routecollector/state/state.db      SQLite database
/opt/routecollector/state/plans/         Route plan snapshots
/opt/routecollector/logs/                Application logs
/opt/routecollector/cache/               Runtime cache
/opt/routecollector/bird/routecollector.conf
                                        Generated BIRD configuration
/etc/bird/routecollector.conf            Installed BIRD configuration
/etc/systemd/system/routecollector.service
                                        systemd unit
/usr/local/bin/routecollector            Global command wrapper
```

---

## Safety model

RouteCollector is designed to fail safely:

- empty route plans are rejected;
- dry-run does not publish configuration;
- generated configuration is installed atomically;
- the previous BIRD configuration is backed up before replacement;
- BIRD configuration is validated before reload;
- failed publication triggers rollback;
- unchanged route sets do not trigger reload;
- failed source loading does not deactivate the last valid domain set;
- removed services are disabled instead of silently deleted;
- snapshots and history are written only after successful publication;
- doctor diagnostics are read-only.

---

## Development

```bash
git clone https://github.com/bagaMann/routecollector.git
cd routecollector

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'

ruff check .
pytest -q
```

Useful focused tests:

```bash
pytest -v tests/test_run_once.py
pytest -v tests/test_doctor_cli.py
pytest -v tests/test_service_source_sync.py
```

---

## Project layout

```text
routecollector/
├── bird/
├── cache/
├── config/
│   ├── config.yaml
│   └── services/
├── docs/
├── install/
│   ├── install.sh
│   ├── upgrade.sh
│   └── uninstall.sh
├── logs/
├── routecollector/
│   ├── core/
│   ├── doctor/
│   ├── exporter/
│   ├── history/
│   ├── parser/
│   ├── planner/
│   ├── policy/
│   ├── resolver/
│   ├── sources/
│   └── workflow/
├── scripts/
├── state/
│   └── plans/
├── tests/
├── pyproject.toml
└── README.md
```

---

## Roadmap

Possible future directions:

- parallel DNS resolution;
- structured JSON output;
- JSON, CSV, Git, and API source plugins;
- HTTP caching with ETag and `If-Modified-Since`;
- Prometheus metrics;
- lightweight monitoring API;
- optional Web dashboard;
- additional publication and aggregation policies.

---

## License

See [LICENSE](LICENSE).
