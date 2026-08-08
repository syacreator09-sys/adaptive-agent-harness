#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET_RAW="${1:-$PWD}"
[ -e "$TARGET_RAW" ] || mkdir -p "$TARGET_RAW"
TARGET="$(cd "$TARGET_RAW" 2>/dev/null && pwd -P || true)"
[ -n "$TARGET" ] && [ -d "$TARGET" ] || { echo "AAH: target path is not a directory" >&2; exit 2; }

PY="${AAH_PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "AAH: Python 3.11+ is required" >&2; exit 3; }
"$PY" - <<'PY' >/dev/null 2>&1 || { echo "AAH: Python 3.11+ is required" >&2; exit 3; }
import sys
raise SystemExit(0 if sys.version_info >= (3,11) else 1)
PY

AAH="$TARGET/.aah"; RUNTIME="$AAH/runtime"; BIN="$AAH/bin"
mkdir -p "$AAH" "$BIN"
rm -rf "$RUNTIME.new"; mkdir -p "$RUNTIME.new"
cp -R "$ROOT/factory" "$RUNTIME.new/factory"
rm -rf "$RUNTIME"; mv "$RUNTIME.new" "$RUNTIME"

cat > "$BIN/factory" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$RUNTIME:\${PYTHONPATH:-}"
case "\${1:-}" in
  evidence-ingest) shift; exec "$PY" -m factory.evidence_ingest_cli "\$@" ;;
  prepare-tasks)   shift; exec "$PY" -m factory.task_prepare_cli "\$@" ;;
  task-gate)       shift; exec "$PY" -m factory.task_gate_cli "\$@" ;;
  *) exec "$PY" -m factory.cli "\$@" ;;
esac
WRAP
chmod +x "$BIN/factory"; ln -sf factory "$BIN/aah"

cat > "$BIN/guardian-hook" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$RUNTIME:\${PYTHONPATH:-}"
export AAH_TARGET_ROOT="$TARGET"
exec "$PY" -m factory.hook_guardian
WRAP
chmod +x "$BIN/guardian-hook"

cat > "$BIN/tool-adapter" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$RUNTIME:\${PYTHONPATH:-}"
exec "$PY" -m factory.tool_adapter_cli "\$@"
WRAP
chmod +x "$BIN/tool-adapter"

if command -v git >/dev/null 2>&1 && [ "${AAH_NO_GIT_INIT:-0}" != "1" ]; then
  git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1 || git -C "$TARGET" init -q || true
fi

mkdir -p "$TARGET/.claude/skills/aah" "$TARGET/.claude/agents"
cp "$ROOT/.claude/skills/aah/SKILL.md" "$TARGET/.claude/skills/aah/SKILL.md"
PYTHONPATH="$RUNTIME" "$PY" -m factory.agent_renderer "$TARGET/.claude/agents"

"$PY" - "$TARGET" <<'PY'
from pathlib import Path
import json, sys
root=Path(sys.argv[1]); p=root/'.claude'/'settings.local.json'; p.parent.mkdir(parents=True,exist_ok=True)
try: data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
except Exception:
    print(f"AAH warning: preserving unparseable {p}; native Guardian hook was not installed",file=sys.stderr); raise SystemExit(0)
hooks=data.setdefault('hooks',{}).setdefault('PreToolUse',[])
entry={'matcher':'Bash|Read|Write|Edit|NotebookEdit|Grep|Glob','hooks':[{'type':'command','command':'.aah/bin/guardian-hook','timeout':10,'statusMessage':'AAH Guardian'}]}
def ours(x): return any(isinstance(h,dict) and h.get('command')=='.aah/bin/guardian-hook' for h in (x.get('hooks') or [])) if isinstance(x,dict) else False
hooks[:]=[x for x in hooks if not ours(x)]+[entry]
p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
PY

"$PY" - "$TARGET" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])/'AGENTS.md'; start='<!-- AAH:START -->'; end='<!-- AAH:END -->'
block='''<!-- AAH:START -->
## Adaptive Agent Harness
For AAH work use fresh independent producer/evaluator brains, sealed SPEC/RUBRIC contracts, persistent findings/evidence, and deterministic gates. External runs: `.aah/bin/factory run "<goal>" --profile auto`; native Claude Code: `/aah`. Never expose `.env` values, bypass Guardian, or treat another agent's conclusion as proof. MCP servers remain project/user managed and are selected only when required.
<!-- AAH:END -->'''
text=p.read_text(encoding='utf-8') if p.exists() else ''
if start in text and end in text:
    before=text.split(start,1)[0].rstrip(); after=text.split(end,1)[1].lstrip(); text=(before+'\n\n' if before else '')+block+('\n\n'+after if after else '')+'\n'
else: text=text.rstrip()+('\n\n' if text.strip() else '')+block+'\n'
p.write_text(text,encoding='utf-8')
PY

"$BIN/factory" setup --target "$TARGET" --non-interactive >/dev/null

cat <<MSG
Adaptive Agent Harness installed in: $TARGET
Check: $BIN/factory doctor --target "$TARGET"
Claude Code: open the project and run /aah
External/Hermes: $BIN/factory run "your goal" --target "$TARGET" --profile auto
Optional local adapters: AAH_TOOL_WEB / AAH_TOOL_IMAGE / AAH_TOOL_VIDEO / AAH_TOOL_VOICE via $BIN/tool-adapter.
No GitHub Actions were installed. API keys are not required or used by default.
MSG
