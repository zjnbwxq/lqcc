# LQCC Architecture 0.7.1

LQCC is built around three components.

## 1. `.capsule` file

A single local packed file.

It stores:

- compressed raw conversation blocks
- extracted dictionary entries
- attachment payloads
- attachment sidecars
- query sketches
- compressed tail index

The file is no-SQL. Readers open the file, jump to the tail index, search the dictionary, and decode raw blocks only when needed.

## 2. CLI and local services

The CLI exposes both manual and automated flows.

Manual:

```text
quick
build
search
resume
append
attach
export
verify
```

Automation:

```text
daemon
proxy
wrap
start
```

The daemon provides a local HTTP API. The proxy provides an OpenAI-compatible non-streaming capture layer.

## 3. Reader skill

The reader skill is a short instruction file for AI agents.

It tells the agent:

- do not ask for full history first
- call `lqcc resume` for minimal context
- call `lqcc search` when more information is needed
- call `lqcc get` when exact evidence is needed
- keep active context small

## Data flow

Manual flow:

```text
chat export -> lqcc quick/build -> .capsule -> lqcc resume -> next AI chat
```

Daemon flow:

```text
client/tool -> local daemon -> .capsule
                         -> search/resume/get
```

Proxy flow:

```text
API client -> LQCC proxy -> upstream model API
                   ↓
              .capsule
```

## Design principle

Keep raw history complete, but keep active model context small.
