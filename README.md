# LQCC

**Lightweight Queryable Context Compression** for long-running AI conversations.

LQCC stores a long conversation in a local `.capsule` file, turns it into a queryable context dictionary, and generates a small task-specific resume packet for the next AI chat.

It keeps the full visible history locally and only sends the model the context needed for the current task.

## What works now

- Single-file `.capsule` format, no SQLite runtime backend.
- Local Python CLI.
- Import JSONL, JSON, Markdown, or loose plain-text chat transcripts.
- Append new turns as a project continues.
- Extract context dictionary entries: `DECISION`, `REQUIREMENT`, `TASK`, `PREFERENCE`, `WARNING`, `FACT`, `TRACE`, `ARTIFACT`.
- Search the capsule without loading the full history into an AI model.
- Generate token-budgeted resume packets for a new chat.
- Attach files such as PDFs, images, text files, and binaries.
- Export the full history back to Markdown or JSONL.
- Verify capsule integrity.

LQCC runs locally. No API key is required.

## Install

From source:

```bash
python -m pip install -e .
```

Optional extras:

```bash
python -m pip install -e '.[multimodal]'
```

The base CLI uses the Python standard library. Optional extras improve compression and file sidecars.

## Quick start

Create a capsule:

```bash
lqcc create project.capsule --title "My project"
```

Or build one directly from a transcript:

```bash
lqcc build chat.md -o project.capsule --title "My project"
```

Append turns:

```bash
lqcc append project.capsule --role user --text "The project is called LQCC."
lqcc append project.capsule --role assistant --text "LQCC stores context in a local .capsule file."
```

Import an existing transcript:

```bash
lqcc import-chat project.capsule chat.md
```

Search the context dictionary:

```bash
lqcc search project.capsule "What did we decide about the file format?"
```

Generate a small packet for a fresh AI chat:

```bash
lqcc resume project.capsule \
  --task "Continue implementing the CLI" \
  --budget 800
```

Attach files:

```bash
lqcc attach project.capsule paper.pdf
lqcc attach project.capsule screenshot.png
```

Export the full archive:

```bash
lqcc export project.capsule full-history.md
```

Verify integrity:

```bash
lqcc verify project.capsule
```

## Input formats

### JSONL

```jsonl
{"role":"user","content":"We need a queryable context dictionary."}
{"role":"assistant","content":"The raw conversation remains lossless."}
```

```bash
lqcc import-jsonl project.capsule chat.jsonl
```

### JSON

A list of messages or an object with `messages`:

```json
[
  {"role": "user", "content": "The project is called LQCC."},
  {"role": "assistant", "content": "Got it."}
]
```

```bash
lqcc import-chat project.capsule chat.json --format json
```

### Markdown / plain text

```text
User: The project is called LQCC.
Assistant: LQCC saves context in a .capsule file.
```

```bash
lqcc import-chat project.capsule chat.md
```

If a text file has no role markers, it is imported as one turn using `--default-role user` by default.

## Core commands

```text
lqcc build               create a .capsule from a chat transcript
lqcc create              create an empty .capsule
lqcc append              append one visible turn
lqcc import-jsonl        import JSONL role/content messages
lqcc import-chat         import JSON, JSONL, Markdown, or plain text
lqcc search              search dictionary entries, attachments, and source turns
lqcc resume              build a small restart packet for a new AI session
lqcc attach              attach a file with payload and sidecar metadata
lqcc get                 retrieve E#, T#, or A# metadata/evidence
lqcc extract-attachment  restore attachment bytes by A#
lqcc add-entry           add/correct an authoritative dictionary entry
lqcc new-session         branch into a fresh conversation inside the capsule
lqcc export              export the lossless archive
lqcc inspect             show storage and token statistics
lqcc compact             repack the capsule and remove stale tail indexes
lqcc verify              verify index, raw blocks, attachments, and hashes
```

## Platform support

The Python CLI runs on:

- Linux
- macOS Intel
- macOS Apple Silicon
- Windows

The `.capsule` file is platform-independent.

## Current limits

- Browser integration is not included in the first release.
- Hidden model chain-of-thought is not captured. LQCC stores visible conversation and public work traces only.
- The current dictionary extraction is deterministic and conservative. It is useful, but not final.
- Multimodal support currently stores original files and lightweight sidecars; deeper image/audio understanding is future work.

## Documentation

- [CLI guide](docs/CLI.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Capsule format](docs/FORMAT.md)
- [Roadmap](ROADMAP.md)
- [Chinese README](README.zh-CN.md)

## License

MIT.
