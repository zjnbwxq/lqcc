# LQCC Roadmap

Current public version: **0.7.1**.

The goal is simple: keep long-running AI work continuous without making every new request carry the full historical context.

## 0.7.1: usable CLI + automation foundation

Status: implemented.

- no-SQL packed `.capsule` format
- one-command `quick` flow
- terminal `menu`
- local `daemon`
- OpenAI-compatible non-streaming `proxy`
- command `wrap`
- search, resume, get, attach, export, verify
- reader skill for agent tools
- Linux / Windows / macOS Python CLI

## 0.7.x: hardening

Planned:

- improve Windows path handling
- better error messages
- more tests for daemon and proxy
- more robust JSON / Markdown chat import
- better duplicate detection across imported chats
- stricter capsule verification
- cleaner release workflow for GitHub and TestPyPI

## 0.8: standalone executables

Goal: users should not need Python.

Planned assets:

```text
lqcc-windows-x64.exe
lqcc-linux-x64
lqcc-macos-x64
lqcc-macos-arm64
```

Also planned:

- GitHub Actions binary builds
- downloadable sample capsule
- checksum files for every release

## 0.9: stronger context dictionary

Goal: fewer useless tokens and better recall of decisions.

Planned:

- better DECISION / TASK / PREFERENCE / WARNING extraction
- entry versioning and conflict handling
- better budget packing
- better multilingual handling
- better attachment sidecars
- query-specific evidence retrieval

## 1.0: stable local-first context layer

Goal: stable public format and stable automation workflow.

Planned guarantees:

- stable `.capsule` format version
- stable CLI commands
- stable local daemon API
- stable reader skill contract
- stable export format
- backward compatibility for 1.x readers

## After 1.0

Possible directions:

<<<<<<< HEAD
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

=======
- browser extension
- local desktop UI
- MCP server
- richer multimodal sidecars
- local embedding index
- stronger compressed dictionary codec
- public benchmark for active-context token savings
>>>>>>> 5f32ab7 (Add automation layer and rewrite 0.7.1 docs)
