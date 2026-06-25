.PHONY: test install demo

install:
	python -m pip install -e .

test:
	python -m pytest

demo:
	rm -f demo.capsule
	lqcc create demo.capsule --title "Demo"
	lqcc import-chat demo.capsule examples/demo_chat.md
	lqcc resume demo.capsule --task "Continue the LQCC project" --budget 600
