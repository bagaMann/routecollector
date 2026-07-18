# Contributing to RouteCollector

Thank you for contributing to RouteCollector.

## Development setup

Clone the repository:

```bash
git clone https://github.com/bagaMann/routecollector.git
cd routecollector
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project:

```bash
pip install -e ".[dev]"
```

Initialize RouteCollector:

```bash
routecollector init
```

---

# Running checks

Before every commit run:

```bash
ruff check .

pytest -q

routecollector doctor

routecollector run-once --dry-run
```

All commands must complete successfully.

---

# Code style

RouteCollector follows a few simple rules.

- Python 3.11+
- Type hints everywhere
- Dataclasses where appropriate
- Small focused functions
- Avoid duplicated logic
- Keep modules cohesive
- Ruff must pass
- Tests are required for new functionality

---

# Commit messages

The project uses Conventional Commits.

Examples:

```text
feat(sync): collect per-source statistics

feat(cli): add doctor diagnostics command

fix(doctor): validate BIRD config

docs: update README

test: add plugin loader tests

refactor(sync): simplify source processing
```

---

# Pull requests

Before opening a Pull Request verify:

- Ruff passes
- All tests pass
- Doctor reports HEALTHY
- README updated if needed
- CHANGELOG updated if user-visible behavior changed

---

# Source plugins

New source plugins should normally live in independent repositories.

Expose plugins through Python entry points:

```toml
[project.entry-points."routecollector.sources"]
example = "package.module:ExampleSource"
```

Avoid modifying RouteCollector core unless the functionality benefits every plugin.

---

# Release checklist

Before publishing a release:

```bash
ruff check .

pytest -q

routecollector doctor

routecollector run-once --dry-run

git status
```

The working tree should be clean before creating a release tag.

---

Thank you for helping improve RouteCollector.
