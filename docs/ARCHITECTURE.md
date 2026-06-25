# Architecture

LQCC has three layers.

## 1. Lossless local archive

Every visible turn is stored in compressed raw blocks inside the `.capsule` file.

This layer is not sent to the AI by default. It exists so the user does not lose context.

## 2. Context dictionary

LQCC extracts a small set of typed records from the visible conversation:

```text
DECISION
REQUIREMENT
TASK
PREFERENCE
WARNING
FACT
TRACE
ARTIFACT
```

These entries form the active context dictionary. They are sparse on purpose. The archive remains available when exact evidence is needed.

## 3. Budgeted retrieval

When the user starts a new AI session, LQCC builds a resume packet:

```text
current task
+ most relevant dictionary entries
+ optional recent turns
+ limited evidence snippets
```

The packet is kept under a token budget.

## Runtime flow

```text
append/import
    -> normalize visible turn
    -> store raw content in compressed block
    -> extract dictionary records
    -> update tail index

search/resume
    -> load tail index
    -> score dictionary records and source turns
    -> locally decode only needed raw blocks
    -> return a small result packet
```

## No-SQL packed format

v0.7 does not use SQLite as the runtime capsule format.

The file is a packed appendable container:

```text
magic header
section: raw block
section: attachment
...
compressed tail index
footer
```

The reader opens the file, jumps to the footer, loads the compressed tail index, and only decodes raw blocks when needed.

## Local-first principle

The base product does not require:

```text
API key
cloud upload
account login
browser extension
local database server
```

Optional future integrations may use local models or external APIs, but the core must remain usable offline.
