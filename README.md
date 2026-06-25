# LQCC 0.7.1

**Lightweight Queryable Context Compression** is a local-first `.capsule` context dictionary for long-running AI conversations.

LQCC saves the full visible history locally, extracts a searchable context dictionary, and gives the next AI session only the small context packet it needs.

## What works in 0.7.1

- no-SQL packed `.capsule` file format
- Python CLI for Linux, Windows, and macOS
- one-command beginner flow: `lqcc quick chat.md`
- interactive terminal menu: `lqcc` or `lqcc menu`
- local HTTP daemon for automatic appends and retrieval
- OpenAI-compatible non-streaming proxy that records requests and replies
- command wrapper that records command output as tool context
- search and resume from the capsule without loading full history
- PDF, image, text, code, and binary attachments with AI-readable sidecars
- full-history export and capsule verification
- reader skill for Codex, Claude Code, Cursor, and other agents

## Install

<<<<<<< HEAD
Test install via TestPyPI: 
=======
From TestPyPI:
>>>>>>> 5f32ab7 (Add automation layer and rewrite 0.7.1 docs)

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple lqcc
```

From source:

```bash
git clone https://github.com/zjnbwxq/lqcc.git
cd lqcc
python -m pip install -e ".[multimodal]"
```

Check:

```bash
lqcc --version
```

Expected:

```text
lqcc 0.7.1
```

## Fastest use

```bash
lqcc quick examples/demo_chat.md
```

This creates `examples/demo_chat.capsule` and prints a small packet you can paste into a new AI chat.

## Normal manual flow

```bash
lqcc build chat.md -o project.capsule --title "My Project"
lqcc search project.capsule "what did we decide?"
lqcc resume project.capsule --task "continue the project" --budget 800
lqcc verify project.capsule
```

## Interactive menu

```bash
lqcc
```

or:

```bash
lqcc menu
```

The menu lets users build, resume, search, append, attach, verify, start a daemon, or start a proxy without remembering command syntax.

## Local daemon

Use the daemon when another tool or agent should write into and read from a capsule automatically.

```bash
lqcc daemon project.capsule --port 8765
```

Endpoints:

```text
GET  /health
GET  /stats
POST /append
POST /append-many
POST /resume
POST /search
POST /get
POST /attach
```

Example:

```bash
curl -X POST http://127.0.0.1:8765/append \
  -H "Content-Type: application/json" \
  -d '{"role":"user","content":"Decision: keep active context small."}'
```

## OpenAI-compatible proxy

Use the proxy when an API client should send messages through LQCC so visible messages are automatically written to the capsule.

```bash
export OPENAI_API_KEY="your-key"
lqcc proxy project.capsule \
  --upstream https://api.openai.com/v1/chat/completions \
  --context-mode auto \
  --port 8765
```

Then point the client to:

```text
http://127.0.0.1:8765/v1/chat/completions
```

Context modes:

```text
pass    record messages, forward original request
resume  forward a capsule resume packet plus recent messages
auto    use pass until the request becomes large, then use resume
```

Current limitation: streaming proxy responses are not supported in 0.7.1. Use non-streaming requests.

## Command wrapper

Use `wrap` to record command output as tool context:

```bash
lqcc wrap project.capsule -- python -m pytest
```

This records the command start, exit code, stdout, and stderr into the capsule.

## Agent reader skill

See:

```text
reader-skill/SKILL.md
reader-skill/SKILL.zh-CN.md
```

The skill tells an agent to use `lqcc resume` first, then `lqcc search` or `lqcc get` only when more evidence is needed.

## Scope

LQCC 0.7.1 handles visible text and file artifacts. It does not capture hidden chain-of-thought. It does not include a browser extension yet. Browser support, desktop UI, stronger multimodal indexing, and stable v1.0 format guarantees are future work.

## License

MIT.
