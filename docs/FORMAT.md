# `.capsule` Format v0.7

The `.capsule` file is a single packed file.

## Goals

```text
local-first
single-file
appendable
queryable
recoverable
cross-platform
```

## High-level layout

```text
MAGIC
SECTION*
TAIL_INDEX
FOOTER
```

## Sections

Each section has:

```text
section magic
kind
id
metadata length
payload length
metadata JSON
compressed payload
```

Current section kinds:

```text
B  raw block
A  attachment
```

## Tail index

The tail index is compressed JSON in v0.7. It contains:

```text
metadata
sessions
turn records
raw block table
dictionary entries
entry-source links
attachment records
counters
```

The footer stores the tail index offset, length, and hash.

## Integrity

LQCC verifies:

```text
tail index hash
raw block hashes
turn content hashes
attachment hashes
```

Run:

```bash
lqcc verify project.capsule
```

## Compatibility

Format v0.7 is still alpha. The CLI reads format version `0.7`.

Future versions should provide migration commands before the format is declared stable.
