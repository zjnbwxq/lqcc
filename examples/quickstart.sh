#!/usr/bin/env bash
set -euo pipefail

# Build a capsule and print a resume packet.
lqcc quick examples/demo_chat.md --force --budget 600

# Search it.
lqcc search examples/demo_chat.capsule "what is LQCC?"

# Verify it.
lqcc verify examples/demo_chat.capsule

# Optional automation:
# lqcc daemon examples/demo_chat.capsule --port 8765
# lqcc proxy examples/demo_chat.capsule --context-mode auto --port 8765
