# LQCC Reader Skill 0.7.1

Use this skill when a project provides an LQCC `.capsule` file or a local LQCC daemon.

## Goal

Keep active context small. Do not ask the user to paste the full conversation history first.

## Preferred retrieval order

1. Use `lqcc resume <capsule> --task "<current task>" --budget 800`.
2. If more information is needed, use `lqcc search <capsule> "<query>"`.
3. If exact evidence is needed, use `lqcc get <capsule> E#`, `T#`, or `A#`.
4. Only request full export when the capsule context is insufficient.

## Writing back

When local tools are available, write meaningful visible updates back to the capsule:

```bash
lqcc append project.capsule --role assistant --text "Decision: ..."
```

If the daemon is running, use:

```text
POST /append
POST /append-many
```

Do not save hidden chain-of-thought. Save only visible decisions, requirements, tasks, warnings, artifacts, and final work traces.

## Local daemon

If the user says a daemon is running, prefer HTTP endpoints:

```text
POST /resume
POST /search
POST /get
POST /append
```

## Principle

Retrieve only what is needed for the current task.
