# Roadmap

LQCC follows one rule: useful product first, research paper after the system works.

## v0.7 — First GitHub Release

Status: current target.

Goals:

```text
Python CLI complete
no-SQL packed .capsule format
import JSONL / JSON / Markdown / text
search / resume / append / attach / export / verify
clean README and docs
basic tests
```

Not included:

```text
browser extension
GUI app
cloud sync
API dependency
```

## v0.8 — Installable User Build

Goals:

```text
publish Python package
prebuilt executables for Windows / Linux / macOS
GitHub Actions release workflow
better sample capsules
```

The normal user should not need to compile anything locally.

## v0.9 — Stronger Context Dictionary

Goals:

```text
better DECISION / TASK / PREFERENCE extraction
better duplicate merging
entry version history
stronger search ranking
better resume packet packing
```

Main metric:

```text
same or lower token budget, better context recovery
```

## v1.0 — Stable Capsule Format

Goals:

```text
stable .capsule v1 format
migration tool from v0.x
cross-platform compatibility tests
clear public spec
reliable import/export
```

## v1.1 — Multimodal Sidecars

Goals:

```text
better PDF text/table sidecars
image sidecars
code-file indexing
Markdown / LaTeX / Word support
audio transcript sidecars
```

The original files remain recoverable.

## v1.2 — Agent Reader Integrations

Goals:

```text
Claude Code skill
Codex skill
Cursor rule
local MCP server
ChatGPT starter prompt
```

The agent should call LQCC for context instead of carrying the full old conversation.

## Research Track

Research questions:

```text
How much active model context can be avoided?
How accurately can key decisions be recovered under a fixed budget?
How small can the context dictionary become without losing task continuity?
How should multimodal sidecars be compressed for AI use, not human reading?
```

Paper direction:

```text
LQCC: Lightweight Queryable Context Compression for Long-Running AI Sessions
```
