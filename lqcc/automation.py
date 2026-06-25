from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .capsule import Capsule, CapsuleError
from .text import estimate_tokens


@dataclass
class ServerConfig:
    capsule: str
    host: str = "127.0.0.1"
    port: int = 8765
    upstream: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    context_mode: str = "pass"  # pass, resume, auto
    context_budget: int = 1000
    auto_threshold: int = 6000
    recent: int = 2
    timeout: int = 120


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict | list | str) -> None:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    raw = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8" if not isinstance(payload, str) else "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "authorization, content-type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(raw)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CapsuleError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(value, dict):
        raise CapsuleError("Request JSON must be an object")
    return value


def _message_text(content: Any) -> str:
    """Normalize OpenAI-style message content into visible text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "text" and isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(parts)
    return str(content)


def _extract_assistant_response(payload: dict[str, Any]) -> str:
    try:
        choices = payload.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if content:
                return _message_text(content)
            text = choices[0].get("text")
            if text:
                return _message_text(text)
    except Exception:
        pass
    return ""


def _latest_user_task(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            text = _message_text(msg.get("content"))
            if text.strip():
                return text.strip()[:1000]
    return "continue this conversation/project"


def _total_message_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_tokens(_message_text(m.get("content"))) for m in messages)


def _prepare_forward_messages(config: ServerConfig, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if config.context_mode == "pass":
        return messages
    if config.context_mode == "auto" and _total_message_tokens(messages) < config.auto_threshold:
        return messages
    task = _latest_user_task(messages)
    with Capsule(config.capsule, read_only=True) as cap:
        packet = cap.resume(task, budget=config.context_budget, recent=config.recent)
    recent = messages[-max(1, config.recent * 2):] if messages else []
    return [
        {
            "role": "system",
            "content": (
                "Use the following LQCC capsule resume as the source of prior context. "
                "Do not ask the user to paste the full history unless the retrieved context is insufficient.\n\n"
                + packet
            ),
        },
        *recent,
    ]


def _forward_to_upstream(config: ServerConfig, body: dict[str, Any]) -> tuple[int, bytes, str]:
    if not config.upstream:
        raise CapsuleError("Proxy upstream is not configured")
    if body.get("stream") is True:
        raise CapsuleError("Streaming proxy is not supported in this release. Set stream=false.")
    api_key = os.environ.get(config.api_key_env, "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    raw = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(config.upstream, data=raw, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            return response.status, response.read(), response.headers.get("content-type", "application/json")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("content-type", "application/json")


def make_handler(config: ServerConfig):
    class LQCCHandler(BaseHTTPRequestHandler):
        server_version = "LQCC/0.7.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[lqcc] " + fmt % args + "\n")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "authorization, content-type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path in {"/", "/health"}:
                    _json_response(self, 200, {"ok": True, "capsule": config.capsule, "version": "0.7.1"})
                    return
                if parsed.path == "/stats":
                    with Capsule(config.capsule, read_only=True) as cap:
                        _json_response(self, 200, cap.stats())
                    return
                _json_response(self, 404, {"error": "not found"})
            except Exception as exc:
                _json_response(self, 500, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            try:
                path = urlparse(self.path).path
                if path == "/append":
                    body = _read_json(self)
                    role = str(body.get("role", "user"))
                    content = _message_text(body.get("content") or body.get("text"))
                    session_id = str(body.get("session_id", "main"))
                    extract = bool(body.get("extract", True))
                    with Capsule(config.capsule) as cap:
                        tid, atoms = cap.append_turn(role=role, content=content, session_id=session_id, extract=extract)
                    _json_response(self, 200, {"ok": True, "turn_id": tid, "dictionary_updates": atoms})
                    return

                if path == "/append-many":
                    body = _read_json(self)
                    messages = body.get("messages") or body.get("turns") or []
                    if not isinstance(messages, list):
                        raise CapsuleError("messages must be a list")
                    session_id = str(body.get("session_id", "main"))
                    items = []
                    for msg in messages:
                        if not isinstance(msg, dict):
                            continue
                        items.append({
                            "role": msg.get("role", "user"),
                            "content": _message_text(msg.get("content") or msg.get("text")),
                            "session_id": msg.get("session_id", session_id),
                            "extract": bool(msg.get("extract", True)),
                        })
                    with Capsule(config.capsule) as cap:
                        results = cap.append_many(items, session_id=session_id) if items else []
                    _json_response(self, 200, {"ok": True, "results": [{"turn_id": t, "dictionary_updates": a} for t, a in results]})
                    return

                if path == "/resume":
                    body = _read_json(self)
                    task = str(body.get("task") or "continue this conversation/project")
                    budget = int(body.get("budget") or config.context_budget)
                    recent = int(body.get("recent") or config.recent)
                    with Capsule(config.capsule, read_only=True) as cap:
                        packet = cap.resume(task, budget=budget, recent=recent)
                    _json_response(self, 200, {"ok": True, "packet": packet, "estimated_tokens": estimate_tokens(packet)})
                    return

                if path == "/search":
                    body = _read_json(self)
                    query = str(body.get("query") or "")
                    limit = int(body.get("limit") or 8)
                    with Capsule(config.capsule, read_only=True) as cap:
                        hits = cap.search(query, limit=limit)
                    _json_response(self, 200, {"ok": True, "hits": [hit.__dict__ for hit in hits]})
                    return

                if path == "/get":
                    body = _read_json(self)
                    ident = str(body.get("id") or "").upper()
                    with Capsule(config.capsule, read_only=True) as cap:
                        if ident.startswith("T"):
                            payload = cap.get_turn(int(ident[1:]))
                        elif ident.startswith("E"):
                            payload = cap.get_entry(int(ident[1:]))
                        elif ident.startswith("A"):
                            payload = cap.get_attachment(int(ident[1:]))
                        else:
                            raise CapsuleError("id must start with T, E, or A")
                    _json_response(self, 200, {"ok": True, "result": payload})
                    return

                if path == "/attach":
                    body = _read_json(self)
                    file_path = body.get("path") or body.get("file")
                    if not file_path:
                        raise CapsuleError("attach requires path")
                    with Capsule(config.capsule) as cap:
                        aid = cap.attach_file(str(file_path), session_id=str(body.get("session_id", "main")))
                    _json_response(self, 200, {"ok": True, "attachment_id": aid})
                    return

                if path == "/v1/chat/completions":
                    if not config.upstream:
                        raise CapsuleError("Proxy endpoint is disabled. Start with lqcc proxy.")
                    body = _read_json(self)
                    messages = body.get("messages") or []
                    if not isinstance(messages, list):
                        raise CapsuleError("OpenAI-compatible request requires messages=[]")
                    # Store incoming visible messages before forwarding. Exact duplicates are ignored by Capsule.
                    items = []
                    for msg in messages:
                        if not isinstance(msg, dict):
                            continue
                        role = msg.get("role", "user")
                        if role not in {"user", "assistant", "system", "tool"}:
                            continue
                        text = _message_text(msg.get("content"))
                        if text.strip():
                            items.append({"role": role, "content": text, "session_id": "main", "extract": True})
                    if items:
                        with Capsule(config.capsule) as cap:
                            cap.append_many(items, session_id="main")
                    forward_body = dict(body)
                    forward_body["messages"] = _prepare_forward_messages(config, messages)
                    status, raw, content_type = _forward_to_upstream(config, forward_body)
                    try:
                        response_obj = json.loads(raw.decode("utf-8"))
                        reply = _extract_assistant_response(response_obj)
                        if reply:
                            with Capsule(config.capsule) as cap:
                                cap.append_turn(role="assistant", content=reply, session_id="main")
                    except Exception:
                        pass
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return

                _json_response(self, 404, {"error": "not found"})
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})

    return LQCCHandler


def run_server(config: ServerConfig) -> None:
    server = ThreadingHTTPServer((config.host, int(config.port)), make_handler(config))
    print(f"LQCC server running at http://{config.host}:{config.port}")
    print(f"Capsule: {config.capsule}")
    if config.upstream:
        print(f"OpenAI-compatible proxy: http://{config.host}:{config.port}/v1/chat/completions")
        print(f"Upstream: {config.upstream}")
        print(f"Context mode: {config.context_mode}")
    else:
        print("Endpoints: /health, /stats, /append, /append-many, /resume, /search, /get, /attach")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLQCC server stopped.")
    finally:
        server.server_close()


def wrap_command(capsule: str, command: list[str], *, session_id: str = "main") -> int:
    if not command:
        raise CapsuleError("wrap requires a command after --")
    command_text = " ".join(command)
    with Capsule(capsule) as cap:
        cap.append_turn(role="tool", content=f"Command started: {command_text}", session_id=session_id, extract=True)
    proc = subprocess.run(command, text=True, capture_output=True)
    output = ""
    if proc.stdout:
        output += "STDOUT:\n" + proc.stdout
    if proc.stderr:
        output += "\nSTDERR:\n" + proc.stderr
    summary = f"Command finished: {command_text}\nExit code: {proc.returncode}\n{output}".strip()
    with Capsule(capsule) as cap:
        cap.append_turn(role="tool", content=summary, session_id=session_id, extract=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return int(proc.returncode)
