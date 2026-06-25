# Contributing

LQCC is early-stage. Keep contributions small and testable.

## Setup

```bash
python -m pip install -e '.[dev,multimodal]'
python -m pytest
```

## Principles

```text
local-first
no required API key
small active context
lossless archive
clear CLI behavior
```

## Before opening a PR

```bash
python -m pytest
lqcc --help
```

Avoid adding cloud dependencies to core functionality.
