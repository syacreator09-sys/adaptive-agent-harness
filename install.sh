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

# Atomic-ish runtime replacement: stage the complete runtime first, then swap.
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

cat > "$BIN/tool-adapter" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$RUNTIME:\${PYTHONPATH:-}"
exec "$PY" -m factory.tool_adapter_cli "\$@"
WRAP
chmod +x "$BIN/tool-adapter"

# Git provides LITE's durable checkpoint/memory boundary. Never add existing
# user files to a commit here; initialize only when the target has no repo.
if command -v git >/dev/null 2>&1 && [ "${AAH_NO_GIT_INIT:-0}" != "1" ]; then
  if ! git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$TARGET" init -q || true
  fi
fi

# Claude Code bridge: overwrite only AAH-owned agent/skill names. Unrelated
# project agents, skills and CLAUDE.md remain untouched.
mkdir -p "$TARGET/.claude/skills/aah" "$TARGET/.claude/agents"
cp "$ROOT/.claude/skills/aah/SKILL.md" "$TARGET/.claude/skills/aah/SKILL.md"
PYTHONPATH="$RUNTIME" "$PY" -m factory.agent_renderer "$TARGET/.claude/agents"

# Install an idempotent PreToolUse hook without replacing existing hooks. If
# settings are malformed, preserve them byte-for-byte and warn rather than
# guessing a repair.
"$PY" - "$TARGET" <<'PY'
from pathlib import Path
import json, sys
root=Path(sys.argv[1]); p=root/'.claude'/'settings.local.json'; p.parent.mkdir(parents=True,exist_ok=True)
try:
    data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
except Exception:
    print(f"AAH warning: preserving unparseable {p}; native Guardian hook was not installed", file=sys.stderr)
    raise SystemExit(0)
hooks=data.setdefault('hooks',{}).setdefault('PreToolUse',[])
entry={
  'matcher':'Bash|Read|Write|Edit|NotebookEdit|Grep|Glob',
  'hooks':[{'type':'command','command':'.aah/bin/guardian-hook','timeout':10,'statusMessage':'AAH Guardian'}]
}
def is_aah(value):
    return any(isinstance(h,dict) and h.get('command')=='.aah/bin/guardian-hook' for h in (value.get('hooks') or [])) if isinstance(value,dict) else False
hooks[:]=[value for value in hooks if not is_aah(value)] + [entry]
p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
PY

# Add/update only the marked AAH block in AGENTS.md. Existing project guidance
# stays before/after it. MCP credentials/configuration are never copied here.
"$PY" - "$TARGET" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1]); p=root/'AGENTS.md'
start='<!-- AAH:START -->'; end='<!-- AAH:END -->'
block='''<!-- AAH:START -->
## Adaptive Agent Harness
When work is explicitly assigned to AAH, use its sealed-artifact protocol: fresh independent producer/evaluator brains, persistent SPEC/RUBRIC/FINDINGS/EVIDENCE, and deterministic Final Gate. External runs use `.aah/bin/factory run "<goal>" --profile auto`; native Claude Code uses `/aah`. Never expose `.env` values, bypass AAH Guardian, or treat another agent's conclusion as verification. MCP servers remain user/project managed and must be selected only when the task requires them.
<!-- AAH:END -->'''
text=p.read_text(encoding='utf-8') if p.exists() else ''
if start in text and end in text:
    before=text.split(start,1)[0].rstrip(); after=text.split(end,1)[1].lstrip()
    text=(before+'\n\n' if before else '')+block+('\n\n'+after if after else '')+'\n'
else:
    text=text.rstrip()+('\n\n' if text.strip() else '')+block+'\n'
p.write_text(text,encoding='utf-8')
PY

# Detect project/provider/tool/MCP capabilities and write only safe metadata.
"$BIN/factory" setup --target "$TARGET" --non-interactive >/dev/null

cat <<MSG

Adaptive Agent Harness installed in:
  $TARGET

Runtime:
  $BIN/factory

Check:
  $BIN/factory doctor --target "$TARGET"

Claude Code:
  open Claude Code in the project and run /aah

External / Hermes / scripts:
  $BIN/factory run "your goal" --target "$TARGET" --profile auto

Local adapters (optional):
  AAH_TOOL_WEB / AAH_TOOL_IMAGE / AAH_TOOL_VIDEO / AAH_TOOL_VOICE
  are invoked through $BIN/tool-adapter and their command values are not persisted.

No GitHub Actions were installed. API keys are not required or used by default.
MSG
