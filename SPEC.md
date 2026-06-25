# LQCC Spec Summary

LQCC stores long-running AI work in a local `.capsule` file.

The file contains:

```text
lossless visible history
compressed raw blocks
context dictionary entries
attachment metadata and payloads
compressed tail index
integrity hashes
```

The active AI context is produced by:

```text
lqcc resume <capsule> --task <task> --budget <tokens>
```

The output is a small context packet intended for a new AI conversation.

See `docs/FORMAT.md` for the packed file layout.
