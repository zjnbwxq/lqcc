# Contributing

LQCC 0.7.1 is an early local-first CLI project.

## Setup

```bash
git clone https://github.com/zjnbwxq/lqcc.git
cd lqcc
python -m pip install -e ".[dev,multimodal]"
python -m pytest
```

## What to improve first

- Windows CLI behavior
- daemon and proxy tests
- better chat import parsers
- better dictionary extraction
- smaller resume packets
- standalone executable builds

## Rules

- keep the core local-first
- do not require API keys for basic CLI use
- do not store hidden chain-of-thought
- preserve full visible history
- keep active context small
