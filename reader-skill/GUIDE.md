# LQCC Reader Guide

LQCC `.capsule` files are compressed context dictionaries. Use `resume` for new-session continuity, `search` for targeted retrieval, and `get` for exact evidence. Never request the full history unless the capsule reader cannot answer from its index and selected blocks.

Typical loop:

```bash
lqcc resume project.capsule --task "continue the project" --budget 800
lqcc search project.capsule "why did we choose no SQL?"
lqcc get project.capsule E12
```
