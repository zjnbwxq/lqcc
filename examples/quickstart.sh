#!/usr/bin/env bash
set -euo pipefail

rm -f demo.capsule
lqcc build examples/demo_chat.md -o demo.capsule --title "LQCC demo" --force
lqcc attach demo.capsule examples/notes.md
lqcc search demo.capsule "Why is LQCC not a normal summarizer?"
lqcc resume demo.capsule --task "Continue the LQCC project" --budget 600
