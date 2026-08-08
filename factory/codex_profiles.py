from __future__ import annotations
import sys, tomllib
from pathlib import Path

START="# AAH:PERMISSIONS:START"
END="# AAH:PERMISSIONS:END"

_DENIES='''
".env" = "deny"
".env.*" = "deny"
"*/.env" = "deny"
"*/.env.*" = "deny"
"*/*/.env" = "deny"
"*/*/.env.*" = "deny"
"*/*/*/.env" = "deny"
"*/*/*/.env.*" = "deny"
'''.strip()

BLOCK=f'''{START}
# AAH named profiles are selected only by AAH's Codex subprocesses.
# The user's default_permissions setting is intentionally not changed.
[permissions.aah_readonly.filesystem]
":minimal" = "read"
glob_scan_max_depth = 4

[permissions.aah_readonly.filesystem.":workspace_roots"]
"." = "read"
{_DENIES}

[permissions.aah_workspace.filesystem]
":minimal" = "read"
glob_scan_max_depth = 4

[permissions.aah_workspace.filesystem.":workspace_roots"]
"." = "write"
".git/**" = "read"
".claude/**" = "read"
".codex/**" = "read"
".aah/**" = "read"
{_DENIES}
{END}'''


def _strip_existing(text: str) -> str:
    if START not in text or END not in text:
        return text.rstrip()
    before=text.split(START,1)[0].rstrip()
    after=text.split(END,1)[1].lstrip()
    return (before + ("\n\n" if before and after else "") + after).rstrip()


def install_profiles(target: Path | str) -> dict[str, object]:
    target=Path(target)
    path=target/".codex"/"config.toml"
    path.parent.mkdir(parents=True,exist_ok=True)
    original=path.read_text(encoding="utf-8") if path.exists() else ""
    base=_strip_existing(original)
    try:
        if base.strip():
            tomllib.loads(base)
    except Exception:
        print(f"AAH warning: preserving unparseable {path}; Codex AAH permission profiles were not installed",file=sys.stderr)
        return {"installed":False,"path":str(path),"reason":"unparseable_existing_config"}
    combined=(base+("\n\n" if base else "")+BLOCK+"\n")
    # Validate the final generated TOML too; never install a profile Codex cannot parse.
    try:
        tomllib.loads(combined)
    except Exception as exc:
        print(f"AAH warning: generated Codex permission profile is invalid: {type(exc).__name__}",file=sys.stderr)
        return {"installed":False,"path":str(path),"reason":"generated_profile_invalid"}
    path.write_text(combined,encoding="utf-8")
    return {"installed":True,"path":str(path),"profiles":["aah_readonly","aah_workspace"]}


def has_profiles(target: Path | str) -> bool:
    path=Path(target)/".codex"/"config.toml"
    if not path.exists():
        return False
    try:
        text=path.read_text(encoding="utf-8")
        tomllib.loads(text)
        return START in text and END in text and '":workspace_roots"' in text
    except (OSError,ValueError,tomllib.TOMLDecodeError):
        return False
