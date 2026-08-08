#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
PY="${AAH_PYTHON:-python3}"
"$PY" -m factory.agent_renderer .claude/agents
"$PY" -m factory.agent_renderer .claude/agents --check
echo "AAH Claude agents synchronized."
