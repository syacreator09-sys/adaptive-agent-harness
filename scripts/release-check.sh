#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
PY="${AAH_PYTHON:-python3}"

fail() { echo "AAH RELEASE CHECK FAILED: $*" >&2; exit 1; }
step() { printf '\n== AAH release check: %s ==\n' "$*"; }

command -v "$PY" >/dev/null 2>&1 || fail "Python 3 is unavailable"

step "installer shell syntax"
bash -n install.sh

step "Python syntax"
"$PY" -m compileall -q factory tests

step "canonical Claude agent definitions"
"$PY" -m factory.agent_renderer .claude/agents --check

step "unit and integration regression suite"
"$PY" -m unittest discover -s tests -v

step "forbidden GitHub Actions check"
if [ -d .github/workflows ] && find .github/workflows -type f -print -quit | grep -q .; then
  fail "GitHub Actions workflow files exist"
fi

step "legacy/source-reference hygiene"
# Deliberately exclude this script because the forbidden words live in the
# pattern itself. Current product/docs/tests must be clean.
if grep -RniE 'santmun|santiago|repo de santi|harness de santi' README.md docs factory .claude tests 2>/dev/null; then
  fail "legacy external harness attribution/reference remains in current project files"
fi

step "fresh installation smoke test"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TARGET="$TMP/project"
mkdir -p "$TARGET"
cat > "$TARGET/package.json" <<'JSON'
{"scripts":{"test":"echo ok","build":"echo build"}}
JSON
cat > "$TARGET/.env.local" <<'ENV'
DATABASE_URL=postgres://release-check-secret
PUBLIC_URL=https://example.invalid
ENV
cat > "$TARGET/.mcp.json" <<'JSON'
{"mcpServers":{"docs":{"command":"docs-mcp","env":{"DOCS_TOKEN":"release-check-mcp-secret"}}}}
JSON
printf '# Existing project instructions\nKeep this line.\n' > "$TARGET/AGENTS.md"

AAH_NO_GIT_INIT=1 bash ./install.sh "$TARGET" >/dev/null
[ -x "$TARGET/.aah/bin/factory" ] || fail "factory wrapper missing"
[ -x "$TARGET/.aah/bin/guardian-hook" ] || fail "guardian hook missing"
[ -x "$TARGET/.aah/bin/tool-adapter" ] || fail "tool adapter wrapper missing"
[ -f "$TARGET/.claude/skills/aah/SKILL.md" ] || fail "native /aah skill missing"
[ -f "$TARGET/.claude/agents/aah-planner.md" ] || fail "planner agent missing"
[ -f "$TARGET/.claude/agents/aah-evaluator.md" ] || fail "evaluator agent missing"
[ -f "$TARGET/.claude/agents/aah-task-evaluator.md" ] || fail "task evaluator missing"
grep -q 'Keep this line.' "$TARGET/AGENTS.md" || fail "existing AGENTS.md content was lost"
grep -q 'Adaptive Agent Harness' "$TARGET/AGENTS.md" || fail "AAH AGENTS.md block missing"

step "installed runtime and helper CLIs"
"$TARGET/.aah/bin/factory" --help >/dev/null
"$TARGET/.aah/bin/factory" evidence-ingest --help >/dev/null
"$TARGET/.aah/bin/factory" prepare-tasks --help >/dev/null
"$TARGET/.aah/bin/factory" task-gate --help >/dev/null

step "safe manifest / no secret persistence"
MANIFEST="$TARGET/.aah/project.json"
CAPS="$TARGET/.aah/capabilities.json"
[ -f "$MANIFEST" ] && [ -f "$CAPS" ] || fail "safe capability manifests missing"
grep -q 'DATABASE_URL' "$MANIFEST" || fail "env variable name not detected"
grep -q 'docs' "$MANIFEST" || fail "MCP server name not detected"
if grep -R -Fq 'postgres://release-check-secret' "$MANIFEST" "$CAPS"; then
  fail "project secret value persisted"
fi
if grep -R -Fq 'release-check-mcp-secret' "$MANIFEST" "$CAPS"; then
  fail "MCP secret value persisted"
fi

step "installer idempotence"
AAH_NO_GIT_INIT=1 bash ./install.sh "$TARGET" >/dev/null
COUNT="$($PY - "$TARGET/.claude/settings.local.json" <<'PY'
import json,sys
p=sys.argv[1]
data=json.load(open(p,encoding='utf-8'))
entries=data.get('hooks',{}).get('PreToolUse',[])
print(sum(1 for e in entries if any(h.get('command')=='.aah/bin/guardian-hook' for h in e.get('hooks',[]) if isinstance(h,dict))))
PY
)"
[ "$COUNT" = "1" ] || fail "Guardian hook duplicated after reinstall"

step "no Actions in installed project"
if [ -d "$TARGET/.github/workflows" ] && find "$TARGET/.github/workflows" -type f -print -quit | grep -q .; then
  fail "installer created GitHub Actions"
fi

printf '\nAAH RELEASE CHECK: PASS\n'
