# Guardian

Guardian is an enforcement layer, not a developer agent.

- `OPEN`: routine local work is frictionless; universal destructive actions are still blocked.
- `GUARDED`: normal default. Production-sensitive commands are surfaced and protected paths/secrets are denied.
- `LOCKED`: production/auth/payments/infra work. Sensitive commands require approval and remote pipe-to-shell is blocked.

## Claude Code enforcement

`install.sh` installs an idempotent `PreToolUse` hook into `.claude/settings.local.json` without replacing existing hooks. The hook runs `.aah/bin/guardian-hook` before `Bash`, `Read`, `Write`, `Edit`, and `NotebookEdit` actions. It can deny dangerous commands and sensitive path access before the tool executes.

Protected reads include `.env*`, common credential locations, and AAH runtime internals. Protected writes include `.env*`, `.git`, `.claude`, `.codex`, and AAH runtime/config surfaces. `.aah/runs/*` remains writable because it is the coordination channel between independent agents.

The provider subprocess receives `AAH_GUARDIAN_MODE`, `AAH_TARGET_ROOT`, and `AAH_ROLE`; API keys are removed in subscription-only mode.

## Codex enforcement

AAH launches Codex with its native sandbox boundary. Reviewer/evaluator roles use `read-only`; implementation roles use `workspace-write`. AAH does not switch Codex to danger/full-access automatically. Project-specific Codex rules may further tighten this boundary without changing AAH core.

Guardian never grants permissions that the underlying provider/OS sandbox denies.
