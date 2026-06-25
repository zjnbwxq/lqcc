# LQCC 0.7.1 Specification Summary

LQCC stores AI conversation context in a local `.capsule` file.

## `.capsule`

A `.capsule` file is a no-SQL packed container. It contains:

- compressed raw conversation blocks
- attachment payload sections
- a compressed tail index
- a footer pointing to the current index

The runtime reads the tail index first. Raw blocks are only decoded when exact evidence is needed.

## Context dictionary

LQCC extracts visible conversation content into dictionary entries:

```text
FACT
DECISION
REQUIREMENT
TASK
PREFERENCE
WARNING
TRACE
ARTIFACT
```

These entries are used by `search` and `resume` to keep active context small.

## Automation

0.7.1 includes three automation paths:

```text
daemon   local HTTP append/search/resume/get API
proxy    OpenAI-compatible non-streaming capture proxy
wrap     records command stdout/stderr as tool context
```

## Scope

LQCC 0.7.1 is not a stable 1.0 file format. The `.capsule` format may still change before 1.0.
