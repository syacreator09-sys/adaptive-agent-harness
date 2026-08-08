from __future__ import annotations
import os
import shlex
import subprocess
import sys


ENV_BY_CAPABILITY = {
    "web": "AAH_TOOL_WEB",
    "image": "AAH_TOOL_IMAGE",
    "video": "AAH_TOOL_VIDEO",
    "voice": "AAH_TOOL_VOICE",
}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ENV_BY_CAPABILITY:
        print("usage: tool-adapter <web|image|video|voice> [args...]", file=sys.stderr)
        return 2
    capability = args.pop(0)
    env_name = ENV_BY_CAPABILITY[capability]
    configured = os.environ.get(env_name)
    if not configured:
        print(f"AAH adapter {capability} is not configured ({env_name})", file=sys.stderr)
        return 3
    try:
        command = shlex.split(configured)
    except ValueError as exc:
        print(f"AAH adapter {capability} has invalid command syntax: {exc}", file=sys.stderr)
        return 4
    if not command:
        print(f"AAH adapter {capability} command is empty", file=sys.stderr)
        return 4
    try:
        completed = subprocess.run([*command, *args])
    except OSError as exc:
        print(f"AAH adapter {capability} failed to start: {exc}", file=sys.stderr)
        return 5
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
