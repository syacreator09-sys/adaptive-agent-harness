# Real-provider smoke fixture

This tiny project is intentionally broken. It exists only so `scripts/provider-smoke.sh` can copy it to a temporary directory and exercise AAH with a real authenticated Claude Code and/or Codex subscription without modifying the AAH repository.

Baseline command:

```bash
python3 -m unittest discover -s tests -v
```

The baseline is expected to fail until an AAH smoke run repairs the selected behavior.
