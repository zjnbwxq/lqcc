# Changelog

## 0.7.1

Usability and automation release.

Added:

- `lqcc quick` one-command beginner flow
- `lqcc menu` interactive terminal menu
- `lqcc start` guided launcher
- `lqcc daemon` local HTTP API
- `lqcc proxy` OpenAI-compatible non-streaming capture proxy
- `lqcc wrap` command-output recorder
- daemon endpoints: `/append`, `/append-many`, `/resume`, `/search`, `/get`, `/attach`
- proxy context modes: `pass`, `resume`, `auto`
- updated English and Chinese documentation
- reader skill updates for automated retrieval and local writing

Kept:

- package version remains `0.7.1`
- no-SQL packed `.capsule` backend
- local-first operation
- no API key required for core CLI

Known limitations:

- proxy is non-streaming only
- no browser extension yet
- `.capsule` format is not stable until 1.0

## 0.7.0

Initial public CLI release.

Added:

- no-SQL packed `.capsule` file
- `build`, `create`, `append`, `import-chat`, `import-jsonl`
- `search`, `resume`, `get`, `attach`, `export`, `verify`, `compact`
- basic multimodal sidecars
- reader skill
