# Domain packs

AAH keeps one universal protocol across domains:

```text
REQUEST
  ↓
SPEC + sealed acceptance rubric
  ↓
PRODUCE
  ↓
INDEPENDENT VERIFY
  ↓
FINDINGS
  ↓
BOUNDED FIX
  ↓
FRESH RE-VERIFY
  ↓
DETERMINISTIC GATE
```

The domain changes **identities, tools and admissible evidence**, not the producer/evaluator separation.

## Code

Canonical producer/verifiers:

```text
Planner / Builder / Tester / Evaluator / Fixer
```

Common evidence:

```text
technical_test
build
test
http/browser execution
diff-based verification
system_test
```

FACTORY code additionally requires positive security evidence before the global gate can complete.

## Operations

Uses the code-style implementation roles but expects operational proof such as:

```text
dry_run
simulation
logs
rollback evidence
system_test
```

Production-sensitive commands are independently governed by Guardian risk mode. AAH should prefer dry-run/simulation before live mutation whenever the target system supports it.

## Content

Canonical roles:

```text
Content Strategist
Content Producer
Independent Content Evaluator
```

Expected acceptance criteria should be measurable where possible: format/dimensions, duration, captions, spelling, claims, CTA, safe zones, rendering/output presence, brand constraints and factual requirements.

Content technical/system gates use explicit `content_check` evidence rather than pretending a media artifact passed a software unit test.

Media generation capabilities are not assumed. Image/video/voice adapters are considered available only when the corresponding local `AAH_TOOL_*` adapter is configured. The adapter command value is not persisted in AAH manifests or prompts.

## Research

Canonical roles:

```text
Planner
Researcher
Independent Fact Checker
```

Expected evidence includes source support, citations, recency and contradiction checks. Research technical/system gates use explicit `fact_check` evidence.

Web access is provider-aware. Claude external runtime can map web capability to provider-native web tools. Other providers require an explicitly configured compatible adapter when AAH cannot prove native web capability.

## MCP and domain packs

A task may declare MCP requirements separately from ordinary tools:

```json
{
  "required_mcp": ["github"],
  "optional_mcp": ["docs"]
}
```

Missing required MCP stops the dispatch. AAH discovers/persists server metadata only; credential values remain owned by the provider/project configuration.

Claude external runtime can technically load project MCP configuration in strict mode for selected servers. Codex MCP remains config/provider-managed when no verified per-run disable control exists; AAH does not claim stronger isolation than the CLI provides.

## Env policy across domains

Review roles never receive project secret environment variables. Producer roles receive a project secret only when Project Adapter discovered its name and the task explicitly requests it in `required_env`. Ambient secret-looking variables are removed by default.

## Domain extension rule

A new domain pack is valid only if it preserves:

1. a producer distinct from its evaluator;
2. fresh evaluator context per verification pass;
3. sealed binary/measurable acceptance criteria;
4. explicit admissible evidence types;
5. bounded repair loops;
6. deterministic Final Gate semantics;
7. tool/MCP/env capabilities that are discovered rather than invented.
