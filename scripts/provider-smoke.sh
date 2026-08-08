#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROFILE="${1:-lite}"
case "$PROFILE" in lite|pro|factory) ;; *) echo "usage: bash scripts/provider-smoke.sh [lite|pro|factory]" >&2; exit 2;; esac
PY="${AAH_PYTHON:-python3}"
TMP="$(mktemp -d)"
trap 'if [ "${AAH_KEEP_SMOKE:-0}" = "1" ]; then echo "AAH smoke kept at: '$TMP'"; else rm -rf "'$TMP'"; fi' EXIT
TARGET="$TMP/project"
cp -R "$ROOT/fixtures/provider_smoke" "$TARGET"

cd "$TARGET"
git init -q
git config user.email "aah-smoke@example.invalid"
git config user.name "AAH Smoke"
git add .
git commit -qm "smoke: baseline intentionally broken fixture"

bash "$ROOT/install.sh" "$TARGET" >/dev/null
git add .gitignore AGENTS.md .claude 2>/dev/null || true
git commit -qm "smoke: install AAH harness" || true

STRATEGY="${AAH_SMOKE_PROVIDER:-auto}"
case "$STRATEGY" in auto|claude|codex|both) ;; *) echo "AAH_SMOKE_PROVIDER must be auto|claude|codex|both" >&2; exit 2;; esac
"$PY" - "$TARGET" "$STRATEGY" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); strategy=sys.argv[2]
p=root/'.aah'/'factory.local.yaml'
data=json.loads(p.read_text(encoding='utf-8'))
data.setdefault('providers',{})['strategy']=strategy
data.setdefault('billing',{})['mode']='subscription_only'
data['billing']['api_fallback']=False
p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY

unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN OPENAI_API_KEY || true
.aah/bin/factory doctor --json > "$TMP/doctor.json"

case "$PROFILE" in
  lite)
    REQUEST='Repair the two existing failing behaviors in src/math_service.py so the existing unittest suite passes. Preserve the public function signatures and add no dependencies.'
    ;;
  pro)
    REQUEST='Stabilize the math service: repair all existing test failures, preserve public signatures, add focused edge-case unittest coverage for negative integer addition and currency values requiring two decimal places, and add no dependencies.'
    ;;
  factory)
    REQUEST='Complete the math service as two independently verifiable workstreams: arithmetic correctness and currency formatting correctness. Preserve public signatures, add focused unittest coverage for each workstream, add no dependencies, integrate the accepted task outputs, and make the complete unittest suite pass.'
    ;;
esac

echo "AAH real-provider smoke: profile=$PROFILE provider_strategy=$STRATEGY"
set +e
.aah/bin/factory run "$REQUEST" --profile "$PROFILE" --guardian guarded --domain code > "$TMP/run.json"
RC=$?
set -e
cat "$TMP/run.json"
[ "$RC" -eq 0 ] || { echo "AAH provider smoke: harness run did not reach DONE" >&2; exit "$RC"; }

"$PY" -m unittest discover -s tests -v

"$PY" - "$TMP/run.json" <<'PY'
import json,sys
payload=json.load(open(sys.argv[1],encoding='utf-8'))
assert payload.get('done') is True, payload
assert payload.get('gate',{}).get('failures')==[], payload.get('gate')
print('AAH PROVIDER SMOKE: PASS')
print('run_id:', payload.get('run_id'))
print('profile:', payload.get('profile'))
PY

if [ "${AAH_KEEP_SMOKE:-0}" = "1" ]; then
  cp "$TMP/doctor.json" "$TARGET/doctor.json"
  cp "$TMP/run.json" "$TARGET/run.json"
fi
