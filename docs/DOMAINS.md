# Domain packs

AAH's universal contract is:

`REQUEST → SPEC → PRODUCE → VERIFY → FINDINGS → FIX → RE-VERIFY → FINAL GATE`

The `code`, `content`, `research`, and `operations` packs change agent identities, tool requirements and evidence expectations without changing that contract.

## Tool truthfulness

AAH never marks a media/search capability as usable merely because an agent asks for it.

- Claude Code can expose its built-in `WebSearch`, `WebFetch`, `Read`, `Glob` and `Grep` tools when the selected role needs web/files.
- Codex filesystem access is governed by its AAH sandbox profile. AAH does not assume live web search is enabled for a Codex installation because that setting is installation-dependent.
- Executable tools such as Git, Docker, Playwright, FFmpeg/FFprobe and Semgrep are discovered on the current machine.
- Image/video/voice generation require an explicit local adapter. If the requested content needs one and none is connected, AAH stops instead of fabricating a result.

## Local adapters

A machine can expose its own wrapper/CLI for external systems without changing AAH core:

```bash
export AAH_TOOL_IMAGE=/path/to/image-adapter
export AAH_TOOL_VIDEO=/path/to/video-adapter
export AAH_TOOL_VOICE=/path/to/voice-adapter
export AAH_TOOL_WEB=/path/to/web-search-adapter
```

The value may be an executable name on `PATH` or an existing executable/path. Tool Router records the resolved path in the agent context. Roles must also have shell capability before an executable adapter is considered usable.

This makes the same clone adaptable to different equipment: one machine may expose only Claude web tools, another may add FFmpeg and media adapters, and another may run only code-domain tooling.

## Content

Content Producer dynamically requires `image`, `video`, or `voice` only when the request actually asks for those artifact types. Content Evaluator uses files/web plus `ffprobe` when available and must return explicit positive evidence for PASS.

## Research

Researcher and Fact Checker require real web access. When Claude and Codex are both available, AAH prefers Claude for web-grounded roles because AAH can explicitly expose Claude Code's web tools. A Codex-only research machine needs an explicit `AAH_TOOL_WEB` adapter unless its future capability can be probed deterministically.

## Operations

Operations reuses the code-domain safety model. Production/auth/payment/infrastructure work should route to GUARDED/LOCKED Guardian according to risk and must pass the deterministic Final Gate.
