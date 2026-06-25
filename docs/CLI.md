# LQCC CLI 0.7.1

## Beginner commands

```bash
lqcc quick chat.md
```

Build a capsule and immediately print a resume packet.

```bash
lqcc
```

Open the terminal menu.

## Build and import

```bash
lqcc build chat.md -o project.capsule --title "Project"
lqcc create project.capsule --title "Project"
lqcc import-chat project.capsule chat.md
lqcc import-jsonl project.capsule chat.jsonl
```

Supported imports:

```text
Markdown
plain text with User:/Assistant: markers
JSON
JSONL role/content messages
```

## Retrieve context

```bash
lqcc search project.capsule "what did we decide?"
lqcc resume project.capsule --task "continue the project" --budget 800
lqcc get project.capsule E1
lqcc get project.capsule T1
lqcc get project.capsule A1
```

## Write context

```bash
lqcc append project.capsule --role user --text "Decision: keep active context small."
lqcc add-entry project.capsule --kind DECISION --text "Use no-SQL packed capsules."
lqcc attach project.capsule paper.pdf
```

## Export and verify

```bash
lqcc export project.capsule history.md
lqcc export project.capsule history.jsonl --format jsonl
lqcc verify project.capsule
lqcc compact project.capsule
lqcc inspect project.capsule
```

## Automation

```bash
lqcc daemon project.capsule --port 8765
```

Run local HTTP endpoints for automatic appends and retrieval.

```bash
lqcc proxy project.capsule --upstream https://api.openai.com/v1/chat/completions --context-mode auto
```

Run an OpenAI-compatible non-streaming proxy.

```bash
lqcc wrap project.capsule -- python -m pytest
```

Run a command and record stdout/stderr.

## Version

```bash
lqcc --version
```

Expected:

```text
lqcc 0.7.1
```
