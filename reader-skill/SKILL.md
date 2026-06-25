# LQCC Capsule Reader Skill

Use this skill when the user provides a `.capsule` file or says that project context is stored in LQCC.

## Goal

Retrieve only the context needed for the current task. Do not ask the user to paste the full conversation history.

## Procedure

1. Start with a resume packet:

```bash
lqcc resume <capsule> --task "<current task>" --budget 800
```

2. Use the returned packet as the active context for the current answer.

3. If a specific decision, file, or evidence item is missing, search the capsule:

```bash
lqcc search <capsule> "<question>" --limit 8
```

4. If exact evidence is needed, retrieve a cited record:

```bash
lqcc get <capsule> E12
lqcc get <capsule> T40
lqcc get <capsule> A3
```

5. After useful new visible context is produced, append the new turns:

```bash
lqcc append <capsule> --role user --text "..."
lqcc append <capsule> --role assistant --text "..."
```

## Rules

- Prefer `resume` before `search`.
- Prefer dictionary entries before raw turns.
- Load raw turns only when exact evidence is needed.
- Keep active context under the requested budget.
- Never treat LQCC as a normal summarizer; it is a queryable context dictionary.
