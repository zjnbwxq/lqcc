# CLI Guide

LQCC is currently a local command-line tool.

## Build in one step

```bash
lqcc build chat.md -o project.capsule --title "Project"
```

This creates a new capsule and imports the transcript.

## Create

```bash
lqcc create project.capsule --title "Project"
```

Options:

```text
--title   human-readable title
--codec   zlib9, zlib, lzma, bz2, zstd, brotli, none
--force   overwrite an existing capsule
```

The default codec is `zlib9`, so the base CLI has no external codec dependency. Optional `zstd` and `brotli` codecs can be selected when installed.

## Append

```bash
lqcc append project.capsule --role user --text "..."
```

Roles:

```text
user
assistant
system
tool
```

You can also pipe text:

```bash
cat message.txt | lqcc append project.capsule --role user
```

## Import

JSONL:

```bash
lqcc import-jsonl project.capsule chat.jsonl
```

Auto-detected JSON, JSONL, Markdown, or plain text:

```bash
lqcc import-chat project.capsule chat.md
```

Explicit format:

```bash
lqcc import-chat project.capsule chat.json --format json
lqcc import-chat project.capsule chat.txt --format text
```

## Search

```bash
lqcc search project.capsule "what was decided about SQL?"
```

JSON output:

```bash
lqcc search project.capsule "token budget" --json
```

Only dictionary entries:

```bash
lqcc search project.capsule "token budget" --entries-only
```

## Resume

```bash
lqcc resume project.capsule --task "continue the project" --budget 800
```

Write to a file:

```bash
lqcc resume project.capsule --task "write README" --budget 600 --output next_prompt.md
```

## Attach files

```bash
lqcc attach project.capsule paper.pdf
lqcc attach project.capsule screenshot.png
lqcc attach project.capsule notes.md
```

Inspect an attachment:

```bash
lqcc get project.capsule A1
```

Recover bytes:

```bash
lqcc extract-attachment project.capsule A1 restored.pdf
```

## Manual dictionary correction

```bash
lqcc add-entry project.capsule \
  --kind DECISION \
  --text "LQCC should remain local-first and should not require an API key."
```

Supported kinds:

```text
DECISION REQUIREMENT TASK PREFERENCE WARNING FACT TRACE ARTIFACT
```

## Export

```bash
lqcc export project.capsule full.md
lqcc export project.capsule full.jsonl --format jsonl
```

## Inspect / compact / verify

```bash
lqcc inspect project.capsule
lqcc compact project.capsule
lqcc verify project.capsule
```
