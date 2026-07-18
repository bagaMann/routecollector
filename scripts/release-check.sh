#!/usr/bin/env bash

set -euo pipefail

echo
echo "========================================"
echo " RouteCollector Release Validation"
echo "========================================"

echo
echo "[1/6] Ruff"
ruff check .

echo
echo "[2/6] Tests"
pytest -q

echo
echo "[3/6] Doctor"
routecollector doctor

echo
echo "[4/6] Dry run"
routecollector run-once --dry-run

echo
echo "[5/6] Git status"
git status --short

echo
echo "[6/6] BIRD"
birdc show protocols

echo
echo "========================================"
echo " Release validation completed"
echo "========================================"
