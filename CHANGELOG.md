# Changelog

All notable changes to RouteCollector are documented in this file.

The format is based on **Keep a Changelog** and the project follows **Semantic Versioning**.

---

## [1.2.0] - 2026-07-18

### Added

- Plugin-based domain source architecture.
- Built-in `manual` source plugin.
- Built-in `http-text` source plugin.
- Built-in `domain-list-community` source plugin.
- External source plugin discovery through Python entry points.
- Source plugin registry.
- Source plugin diagnostics (`routecollector sources`).
- Source plugin metadata (`routecollector plugin-info`).
- HTTP text domain source.
- Domain source provenance tracking.
- Service synchronization statistics.
- Detailed synchronization report.
- Structured `run-once` report.
- Dry-run execution mode.
- Route plan snapshots.
- Route plan comparison (`routecollector changes`).
- Successful cycle history.
- Route history viewer.
- SQLite observation batching.
- Snapshot retention.
- Automatic BIRD configuration installation.
- Automatic BIRD rollback on failed reload.
- Atomic configuration replacement.
- RouteCollector Doctor diagnostic subsystem.
- Environment diagnostics.
- Directory diagnostics.
- SQLite diagnostics.
- Service configuration diagnostics.
- Source plugin diagnostics.
- BIRD diagnostics.
- Runtime diagnostics.
- Systemd service diagnostics.
- Snapshot diagnostics.
- History diagnostics.
- Debian installation script.
- Debian upgrade script.
- Debian uninstall script.
- Example external source plugin project.

### Changed

- Complete redesign of service synchronization.
- Source loading moved to plugin architecture.
- Synchronization now preserves source provenance.
- Synchronization now disables removed services.
- Stale domains are deactivated instead of deleted.
- CLI synchronization output redesigned.
- `run-once` output reorganized into logical sections.
- Route publication workflow simplified.
- Improved BIRD publication workflow.
- Improved configuration validation.
- Improved service reporting.
- Improved plugin reporting.
- Improved runtime diagnostics.
- README completely rewritten.
- Release documentation updated.

### Fixed

- Fixed stale domain handling.
- Fixed removed service handling.
- Fixed duplicate source accounting.
- Fixed dry-run reporting.
- Fixed history updates during dry-run.
- Fixed snapshot creation during dry-run.
- Fixed BIRD configuration validation.
- Fixed BIRD parse mode invocation.
- Fixed source synchronization edge cases.
- Fixed plugin discovery error handling.
- Fixed synchronization deactivation logic.
- Fixed CLI reporting inconsistencies.
- Fixed multiple workflow corner cases.
- Numerous stability improvements and test coverage extensions.

### Tests

- More than 200 automated tests.
- Extended repository tests.
- Extended synchronization tests.
- Added plugin loader tests.
- Added HTTP source tests.
- Added doctor subsystem tests.
- Added runtime tests.
- Added CLI tests.

---

## [1.1.0]

Initial public RouteCollector release.

### Added

- SQLite storage.
- DNS resolver.
- Route planner.
- BIRD exporter.
- Route statistics.
- Initial CLI.
- Initial systemd daemon.
