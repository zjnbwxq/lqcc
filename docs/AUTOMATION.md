# LQCC Automation 0.7.1

LQCC has two roles:

```text
wrapper/proxy/daemon  records context automatically
reader skill          teaches the AI how to retrieve context
```

A skill alone is not enough for automatic writing. The reliable path is a wrapper or proxy that captures visible user and assistant messages outside the model.

## Daemon

Start:

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

Append one message:

```bash
curl -X POST http://127.0.0.1:8765/append \
  -H "Content-Type: application/json" \
  -d '{"role":"user","content":"Decision: use daemon for automatic writing."}'
```

Get a resume packet:

```bash
curl -X POST http://127.0.0.1:8765/resume \
  -H "Content-Type: application/json" \
  -d '{"task":"continue the project","budget":800}'
```

## Proxy

Start:

```bash
export OPENAI_API_KEY="your-key"
lqcc proxy project.capsule \
  --upstream https://api.openai.com/v1/chat/completions \
  --context-mode auto \
  --port 8765
```

Then use:

```text
http://127.0.0.1:8765/v1/chat/completions
```

The proxy records visible request messages and assistant replies into the capsule.

Context modes:

```text
pass    record and forward original request
resume  forward capsule resume packet plus recent messages
auto    pass first, then resume after the token threshold
```

Current limitation: non-streaming only.

## Command wrapper

```bash
lqcc wrap project.capsule -- python -m pytest
```

This records command start, exit code, stdout, and stderr.

## Recommended usage

For manual users:

```bash
lqcc quick chat.md
```

For tools and agents:

```bash
lqcc daemon project.capsule
```

For API clients:

```bash
lqcc proxy project.capsule --context-mode auto
```
