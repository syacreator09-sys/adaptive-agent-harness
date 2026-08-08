#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET_RAW="${1:-$PWD}"
if [ ! -e "$TARGET_RAW" ]; then
  mkdir -p "$TARGET_RAW"
fi
TARGET="$(cd "$TARGET_RAW" 2>/dev/null && pwd -P || true)"

if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
  echo "AAH: target path is not a directory" >&2
  exit 2
fi

PY="${AAH_PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "AAH: Python 3.11+ is required" >&2
  exit 3
fi

if ! "$PY" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3,11) else 1)
PY
then
  echo "AAH: Python 3.11+ is required" >&2
  exit 3
fi

AAH="$TARGET/.aah"
RUNTIME="$AAH/runtime"
BIN="$AAH/bin"
mkdir -p "$AAH" "$BIN"

# Runtime is copied into the project so the source clone is not required afterward.
rm -rf "$RUNTIME.new"
mkdir -p "$RUNTIME.new"
cp -R "$ROOT/factory" "$RUNTIME.new/factory"
rm -rf "$RUNTIME"
mv "$RUNTIME.new" "$RUNTIME"

cat > "$BIN/factory" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$RUNTIME:\${PYTHONPATH:-}"
exec "$PY" -m factory.cli "\$@"
WRAP
chmod +x "$BIN/factory"
ln -sf factory "$BIN/aah"

cat > "$BIN/guardian-hook" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$RUNTIME:\${PYTHONPATH:-}"
export AAH_TARGET_ROOT="$TARGET"
exec "$PY" -m factory.hook_guardian
WRAP
chmod +x "$BIN/guardian-hook"

# Initialize Git only for a project that does not already have it.
if command -v git >/dev/null 2>&1 && [ "${AAH_NO_GIT_INIT:-0}" != "1" ]; then
  if ! git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$TARGET" init -q || true
  fi
fi

# Install Claude Code bridge with unique AAH-prefixed names; existing unrelated agents/skills remain untouched.
mkdir -p "$TARGET/.claude/skills/aah" "$TARGET/.claude/agents"
cp "$ROOT/.claude/skills/aah/SKILL.md" "$TARGET/.claude/skills/aah/SKILL.md"
PYTHONPATH="$RUNTIME" "$PY" - "$TARGET" <<'PY'
from pathlib import Path
import sys
from factory.agents import AgentRegistry
target=Path(sys.argv[1]); out=target/'.claude'/'agents'; out.mkdir(parents=True,exist_ok=True)
map_tools={'read':'Read','glob':'Glob','grep':'Grep','edit':'Edit','write':'Write','shell':'Bash','browser':'Skill'}
roles=['planner','architect','builder','tester','evaluator','fixer','worker','task_evaluator','integrator','system_tester','security_reviewer','final_reviewer']
reg=AgentRegistry()
for role in roles:
    a=reg.get(role); tools=[]
    for t in a['tools']:
        if t in map_tools and map_tools[t] not in tools: tools.append(map_tools[t])
    lines=['---',f'name: aah-{role.replace("_","-")}',f'description: {a["mission"]}','model: inherit']
    if tools: lines.append('tools: '+', '.join(tools))
    lines += ['---','',f'# {a["identity"]}','',a['mission'],'','## Contract','',f'Inputs: {", ".join(a["inputs"])}',f'Outputs: {", ".join(a["outputs"])}','','## Rules','']
    lines += [f'- {rule}' for rule in a['rules']]
    lines += ['','When the orchestrator supplies `run_dir`, coordination artifacts must be written only there. Product code changes are allowed only for roles whose mission explicitly requires implementation.']
    (out/f'aah-{role.replace("_","-")}.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
PY

# Install an idempotent Claude PreToolUse enforcement hook without replacing existing project hooks.
"$PY" - "$TARGET" <<'PY'
from pathlib import Path
import json, sys
root=Path(sys.argv[1]); p=root/'.claude'/'settings.local.json'; p.parent.mkdir(parents=True,exist_ok=True)
try:
    data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
except Exception:
    print(f"AAH warning: preserving unparseable {p}; Guardian hook was not installed there", file=sys.stderr)
    raise SystemExit(0)
hooks=data.setdefault('hooks',{}).setdefault('PreToolUse',[])
entry={
  'matcher':'Bash|Read|Write|Edit|NotebookEdit',
  'hooks':[{'type':'command','command':'.aah/bin/guardian-hook','timeout':10,'statusMessage':'AAH Guardian'}]
}
def is_aah(x):
    return any(isinstance(h,dict) and h.get('command')=='.aah/bin/guardian-hook' for h in (x.get('hooks') or [])) if isinstance(x,dict) else False
hooks[:]=[x for x in hooks if not is_aah(x)] + [entry]
p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
PY

# Add a small idempotent Codex/agent guidance block without replacing an existing AGENTS.md.
"$PY" - "$TARGET" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'AGENTS.md'
start='<!-- AAH:START -->'
end='<!-- AAH:END -->'
block='''<!-- AAH:START -->
## Adaptive Agent Harness
When a task is explicitly assigned to AAH, inspect `.aah/project.json` and use the AAH protocol: producer and evaluator are independent, evidence is required, and Final Gate decides completion. From an external shell use `.aah/bin/factory run "<goal>" --profile auto`. Do not bypass AAH Guardian or expose `.env` values.
<!-- AAH:END -->'''
text=p.read_text(encoding='utf-8') if p.exists() else ''
if start in text and end in text:
    before=text.split(start,1)[0].rstrip(); after=text.split(end,1)[1].lstrip()
    text=(before+'\n\n' if before else '')+block+('\n\n'+after if after else '')+'\n'
else:
    text=text.rstrip()+('\n\n' if text.strip() else '')+block+'\n'
p.write_text(text,encoding='utf-8')
PY

"$BIN/factory" setup --target "$TARGET" --non-interactive >/dev/null

cat <<MSG

Adaptive Agent Harness installed in:
  $TARGET

Runtime:
  $BIN/factory

Next:
  $BIN/factory doctor --target "$TARGET"

Claude Code:
  open Claude Code in the project and run /aah

External/Hermes:
  $BIN/factory run "your goal" --target "$TARGET" --profile auto

No GitHub Actions were installed. API keys are not required.
MSG
