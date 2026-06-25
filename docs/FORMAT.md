# `.capsule` Format 0.7.1

LQCC 0.7.1 uses a no-SQL packed capsule format.

## High-level layout

```text
MAGIC header
section: compressed raw block
section: attachment payload
section: attachment payload
...
compressed tail index
footer
```

The footer stores the offset and hash of the current tail index.

## Raw blocks

Conversation turns are grouped into compressed raw blocks. A block contains visible role/content turns.

The index stores:

```text
turn id
session id
role
sequence number
hash
query sketch
block id
```

Raw block payloads are decoded only when exact turn text is needed.

## Dictionary entries

LQCC extracts structured entries from visible text:

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

Entries are used for search and resume packets.

## Attachments

Attachments are stored as compressed payloads. Each attachment also gets an AI-readable sidecar.

Examples:

```text
PDF: page count and first extracted text
image: width, height, mode, format
text/code: extracted text preview
binary: basic file metadata
```

## Stability

0.7.1 is an alpha format. The stable compatibility promise starts at 1.0.
