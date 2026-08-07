# Adaptive Agent Harness instructions

This repository implements AAH, a provider-adaptive multi-agent harness with LITE, PRO and FACTORY profiles.

When changing AAH itself:
- keep LITE minimal and sequential;
- never let the producer approve its own work;
- `UNVERIFIED` is never equivalent to `PASS`;
- never persist `.env` values or OAuth/API credentials;
- preserve subscription-first behavior and do not add automatic paid API fallback;
- do not add GitHub Actions or `.github/workflows/*`;
- run `python -m unittest discover -s tests -v` and `bash -n install.sh` before claiming completion.

When AAH is installed into another project, use `.aah/bin/factory doctor` before a run and respect that project's existing `AGENTS.md`, `CLAUDE.md`, README, tests, structure, and environment conventions.
