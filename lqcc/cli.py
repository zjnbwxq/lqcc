from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .automation import ServerConfig, run_server, wrap_command
from .capsule import Capsule, CapsuleError, import_chat_file, import_jsonl
from .codec import DEFAULT_CODEC, SUPPORTED_CODECS
from .text import estimate_tokens


def _text_arg(value: str | None) -> str:
    if value is not None:
        return value
    if sys.stdin.isatty():
        raise CapsuleError("Provide --text or pipe text through stdin")
    return sys.stdin.read()


def _default_capsule_name(source: str | Path) -> str:
    path = Path(source)
    if path.suffix:
        return str(path.with_suffix(".capsule"))
    return str(path) + ".capsule"


def _prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or (default or "")


def _prompt_int(text: str, default: int) -> int:
    raw = _prompt(text, str(default))
    try:
        return int(raw)
    except ValueError:
        print(f"Using default: {default}")
        return default


def _print_next_steps(capsule: str) -> None:
    print("\nNext commands:")
    print(f"  lqcc resume {capsule} --budget 600")
    print(f"  lqcc search {capsule} \"your question\"")
    print(f"  lqcc daemon {capsule}")
    print(f"  lqcc verify {capsule}")


def _ensure_capsule(path: str, title: str | None = None, force: bool = False) -> None:
    capsule = Path(path)
    if capsule.exists() and not force:
        return
    if capsule.exists() and force:
        capsule.unlink()
    with Capsule.create(capsule, title=title or capsule.stem, codec=DEFAULT_CODEC, overwrite=True):
        pass


def _build_from_source(args: argparse.Namespace) -> tuple[str, int, int, dict]:
    output = args.output or _default_capsule_name(args.source)
    with Capsule.create(output, title=args.title, codec=args.codec, overwrite=args.force) as cap:
        turns, atoms = import_chat_file(
            cap,
            args.source,
            session_id=args.session,
            input_format=args.format,
            default_role=args.default_role,
        )
        stats = cap.stats()
    return output, turns, atoms, stats


def cmd_quick(args: argparse.Namespace) -> None:
    output = args.output or _default_capsule_name(args.source)
    title = args.title if args.title != "Untitled capsule" else Path(output).stem
    build_args = argparse.Namespace(
        source=args.source,
        output=output,
        title=title,
        codec=args.codec,
        format=args.format,
        default_role=args.default_role,
        session=args.session,
        force=args.force,
    )
    output, turns, atoms, stats = _build_from_source(build_args)
    task = args.task or "continue this conversation/project"
    with Capsule(output, read_only=True) as cap:
        packet = cap.resume(task, budget=args.budget, recent=args.recent)
    print(f"created {output}; imported {turns} turns; dictionary updates: {atoms}; active_entries={stats['active_entries']}")
    print("\n--- Copy this into your next AI chat ---\n")
    print(packet, end="")
    print("\n--- End resume packet ---")
    _print_next_steps(output)


def cmd_build(args: argparse.Namespace) -> None:
    output, turns, atoms, stats = _build_from_source(args)
    print(f"created {output}; imported {turns} turns; dictionary updates: {atoms}; active_entries={stats['active_entries']}")
    _print_next_steps(output)


def cmd_create(args: argparse.Namespace) -> None:
    with Capsule.create(args.output, title=args.title, codec=args.codec, overwrite=args.force) as cap:
        print(json.dumps(cap.stats(), ensure_ascii=False, indent=2))


def cmd_append(args: argparse.Namespace) -> None:
    content = _text_arg(args.text)
    with Capsule(args.capsule) as cap:
        turn_id, atoms = cap.append_turn(role=args.role, content=content, session_id=args.session, extract=not args.no_extract)
    print(f"appended turn T{turn_id}; dictionary updates: {atoms}")


def cmd_import_jsonl(args: argparse.Namespace) -> None:
    with Capsule(args.capsule) as cap:
        turns, atoms = import_jsonl(cap, args.source, session_id=args.session)
    print(f"imported {turns} turns; dictionary updates: {atoms}")


def cmd_import_chat(args: argparse.Namespace) -> None:
    with Capsule(args.capsule) as cap:
        turns, atoms = import_chat_file(
            cap,
            args.source,
            session_id=args.session,
            input_format=args.format,
            default_role=args.default_role,
        )
    print(f"imported {turns} turns; dictionary updates: {atoms}")


def cmd_search(args: argparse.Namespace) -> None:
    with Capsule(args.capsule, read_only=True) as cap:
        hits = cap.search(args.query, limit=args.limit, include_evidence=not args.entries_only)
    if args.json:
        print(json.dumps([hit.__dict__ for hit in hits], ensure_ascii=False, indent=2))
        return
    if not hits:
        print("No hits.")
        return
    for hit in hits:
        label = f"E{hit.hit_id}" if hit.hit_type == "entry" else f"A{hit.hit_id}" if hit.hit_type == "attachment" else f"T{hit.hit_id}"
        kind = hit.kind or hit.hit_type
        print(f"{label} [{kind}] score={hit.score:.3f}\n{hit.content}\n")


def cmd_resume(args: argparse.Namespace) -> None:
    task = args.task or "continue this conversation/project"
    with Capsule(args.capsule, read_only=True) as cap:
        packet = cap.resume(task, budget=args.budget, recent=args.recent)
    if args.output:
        Path(args.output).write_text(packet, encoding="utf-8")
        print(f"wrote {args.output} ({estimate_tokens(packet)} estimated tokens)")
    else:
        print(packet, end="")


def cmd_inspect(args: argparse.Namespace) -> None:
    with Capsule(args.capsule, read_only=True) as cap:
        stats = cap.stats()
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    for key, value in stats.items():
        if key in {"payload_ratio", "file_to_raw_ratio"}:
            value = f"{float(value):.3f}"
        print(f"{key}: {value}")


def cmd_new_session(args: argparse.Namespace) -> None:
    with Capsule(args.capsule) as cap:
        session_id = cap.new_session(args.title)
    print(session_id)


def cmd_add_entry(args: argparse.Namespace) -> None:
    content = _text_arg(args.text)
    with Capsule(args.capsule) as cap:
        entry_id = cap.add_entry(kind=args.kind, content=content, session_id=args.session)
    print(f"added E{entry_id}")


def cmd_attach(args: argparse.Namespace) -> None:
    with Capsule(args.capsule) as cap:
        attachment_id = cap.attach_file(args.file, session_id=args.session, source_turn_id=args.source_turn)
    print(f"attached A{attachment_id}")


def cmd_get(args: argparse.Namespace) -> None:
    ident = args.id.upper()
    with Capsule(args.capsule, read_only=True) as cap:
        if ident.startswith("T"):
            payload = cap.get_turn(int(ident[1:]))
        elif ident.startswith("E"):
            payload = cap.get_entry(int(ident[1:]))
        elif ident.startswith("A"):
            payload = cap.get_attachment(int(ident[1:]))
        else:
            raise CapsuleError("ID must start with T, E, or A")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def cmd_extract_attachment(args: argparse.Namespace) -> None:
    ident = args.id.upper()
    if not ident.startswith("A"):
        raise CapsuleError("Attachment ID must start with A")
    with Capsule(args.capsule, read_only=True) as cap:
        payload = cap.get_attachment(int(ident[1:]), output=args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def cmd_export(args: argparse.Namespace) -> None:
    with Capsule(args.capsule, read_only=True) as cap:
        if args.format == "jsonl":
            cap.export_jsonl(args.output)
        else:
            cap.export_markdown(args.output)
    print(f"exported {args.output}")


def cmd_compact(args: argparse.Namespace) -> None:
    with Capsule(args.capsule) as cap:
        before = cap.path.stat().st_size
        cap.compact()
        after = cap.path.stat().st_size
    print(f"compacted {args.capsule}: {before} -> {after} bytes")


def cmd_verify(args: argparse.Namespace) -> None:
    with Capsule(args.capsule, read_only=True) as cap:
        problems = cap.verify()
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        raise SystemExit(1)
    print("ok")


def cmd_daemon(args: argparse.Namespace) -> None:
    _ensure_capsule(args.capsule, title=args.title, force=args.force)
    run_server(ServerConfig(capsule=args.capsule, host=args.host, port=args.port, context_budget=args.context_budget, recent=args.recent))


def cmd_proxy(args: argparse.Namespace) -> None:
    _ensure_capsule(args.capsule, title=args.title, force=args.force)
    run_server(ServerConfig(
        capsule=args.capsule,
        host=args.host,
        port=args.port,
        upstream=args.upstream,
        api_key_env=args.api_key_env,
        context_mode=args.context_mode,
        context_budget=args.context_budget,
        auto_threshold=args.auto_threshold,
        recent=args.recent,
        timeout=args.timeout,
    ))


def cmd_wrap(args: argparse.Namespace) -> None:
    _ensure_capsule(args.capsule, title=args.title, force=False)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    code = wrap_command(args.capsule, command, session_id=args.session)
    raise SystemExit(code)


def cmd_start(args: argparse.Namespace) -> None:
    _ensure_capsule(args.capsule, title=args.title, force=args.force)
    print(f"Ready: {args.capsule}")
    print("1) Generate a resume packet")
    print("2) Start local daemon")
    print("3) Start OpenAI-compatible proxy")
    print("4) Open interactive menu")
    print("0) Exit")
    choice = _prompt("Choose", "1")
    if choice == "1":
        task = _prompt("Current task", "continue this conversation/project")
        budget = _prompt_int("Token budget", args.context_budget)
        cmd_resume(argparse.Namespace(capsule=args.capsule, task=task, budget=budget, recent=args.recent, output=None))
    elif choice == "2":
        cmd_daemon(argparse.Namespace(capsule=args.capsule, host=args.host, port=args.port, title=args.title, force=False, context_budget=args.context_budget, recent=args.recent))
    elif choice == "3":
        upstream = _prompt("OpenAI-compatible upstream URL", args.upstream or "https://api.openai.com/v1/chat/completions")
        mode = _prompt("Context mode: pass/resume/auto", args.context_mode)
        cmd_proxy(argparse.Namespace(capsule=args.capsule, host=args.host, port=args.port, title=args.title, force=False, upstream=upstream, api_key_env=args.api_key_env, context_mode=mode, context_budget=args.context_budget, auto_threshold=args.auto_threshold, recent=args.recent, timeout=args.timeout))
    elif choice == "4":
        cmd_menu(None)


def cmd_menu(args: argparse.Namespace | None = None) -> None:
    print("LQCC interactive mode")
    print("1) Build a capsule from a chat/file")
    print("2) Resume from an existing capsule")
    print("3) Search an existing capsule")
    print("4) Append one message to a capsule")
    print("5) Attach a file")
    print("6) Verify a capsule")
    print("7) Start local daemon")
    print("8) Start OpenAI-compatible proxy")
    print("0) Exit")
    choice = _prompt("Choose", "1")
    if choice == "0":
        return
    if choice == "1":
        source = _prompt("Chat/file path")
        output = _prompt("Output capsule", _default_capsule_name(source))
        title = _prompt("Title", Path(output).stem)
        budget = _prompt_int("Resume packet budget", 600)
        cmd_quick(argparse.Namespace(source=source, output=output, title=title, codec=DEFAULT_CODEC, format="auto", default_role="user", session="main", force=True, task="continue this conversation/project", budget=budget, recent=2))
    elif choice == "2":
        capsule = _prompt("Capsule path")
        task = _prompt("Current task", "continue this conversation/project")
        budget = _prompt_int("Token budget", 800)
        cmd_resume(argparse.Namespace(capsule=capsule, task=task, budget=budget, recent=2, output=None))
    elif choice == "3":
        capsule = _prompt("Capsule path")
        query = _prompt("Search query")
        cmd_search(argparse.Namespace(capsule=capsule, query=query, limit=8, entries_only=False, json=False))
    elif choice == "4":
        capsule = _prompt("Capsule path")
        role = _prompt("Role", "user").lower()
        text = _prompt("Message text")
        cmd_append(argparse.Namespace(capsule=capsule, role=role, text=text, session="main", no_extract=False))
    elif choice == "5":
        capsule = _prompt("Capsule path")
        file = _prompt("File to attach")
        cmd_attach(argparse.Namespace(capsule=capsule, file=file, session="main", source_turn=None))
    elif choice == "6":
        capsule = _prompt("Capsule path")
        cmd_verify(argparse.Namespace(capsule=capsule))
    elif choice == "7":
        capsule = _prompt("Capsule path")
        port = _prompt_int("Port", 8765)
        cmd_daemon(argparse.Namespace(capsule=capsule, title=Path(capsule).stem, force=False, host="127.0.0.1", port=port, context_budget=1000, recent=2))
    elif choice == "8":
        capsule = _prompt("Capsule path")
        upstream = _prompt("Upstream URL", "https://api.openai.com/v1/chat/completions")
        port = _prompt_int("Port", 8765)
        cmd_proxy(argparse.Namespace(capsule=capsule, title=Path(capsule).stem, force=False, host="127.0.0.1", port=port, upstream=upstream, api_key_env="OPENAI_API_KEY", context_mode="auto", context_budget=1000, auto_threshold=6000, recent=2, timeout=120))
    else:
        print("Unknown choice.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lqcc", description="Local-first queryable context capsules for token-efficient AI continuity.")
    parser.add_argument("--version", action="version", version=f"lqcc {__version__}")
    sub = parser.add_subparsers(dest="command")
    codec_choices = sorted(SUPPORTED_CODECS)

    p = sub.add_parser("quick", help="One-command flow: chat/file -> .capsule -> resume packet")
    p.add_argument("source")
    p.add_argument("-o", "--output")
    p.add_argument("--title", default="Untitled capsule")
    p.add_argument("--task")
    p.add_argument("--budget", type=int, default=600)
    p.add_argument("--recent", type=int, default=2)
    p.add_argument("--codec", choices=codec_choices, default=DEFAULT_CODEC)
    p.add_argument("--format", choices=["auto", "jsonl", "json", "markdown", "md", "text", "txt"], default="auto")
    p.add_argument("--default-role", choices=["user", "assistant", "system", "tool"], default="user")
    p.add_argument("--session", default="main")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_quick)

    p = sub.add_parser("menu", help="Interactive terminal menu")
    p.set_defaults(func=cmd_menu)

    p = sub.add_parser("start", help="Guided one-entry launcher for resume, daemon, or proxy")
    p.add_argument("capsule")
    p.add_argument("--title", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--upstream", default="https://api.openai.com/v1/chat/completions")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY")
    p.add_argument("--context-mode", choices=["pass", "resume", "auto"], default="auto")
    p.add_argument("--context-budget", type=int, default=1000)
    p.add_argument("--auto-threshold", type=int, default=6000)
    p.add_argument("--recent", type=int, default=2)
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("daemon", help="Run a local HTTP daemon for automatic appends and retrieval")
    p.add_argument("capsule")
    p.add_argument("--title", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--context-budget", type=int, default=1000)
    p.add_argument("--recent", type=int, default=2)
    p.set_defaults(func=cmd_daemon)

    p = sub.add_parser("proxy", help="Run an OpenAI-compatible non-streaming proxy that records messages into a capsule")
    p.add_argument("capsule")
    p.add_argument("--title", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--upstream", default="https://api.openai.com/v1/chat/completions")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY")
    p.add_argument("--context-mode", choices=["pass", "resume", "auto"], default="auto")
    p.add_argument("--context-budget", type=int, default=1000)
    p.add_argument("--auto-threshold", type=int, default=6000)
    p.add_argument("--recent", type=int, default=2)
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(func=cmd_proxy)

    p = sub.add_parser("wrap", help="Run a command and record its stdout/stderr as tool context")
    p.add_argument("capsule")
    p.add_argument("--title", default=None)
    p.add_argument("--session", default="main")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_wrap)

    p = sub.add_parser("build", help="Create a .capsule from a chat export in one step")
    p.add_argument("source")
    p.add_argument("-o", "--output")
    p.add_argument("--title", default="Untitled capsule")
    p.add_argument("--codec", choices=codec_choices, default=DEFAULT_CODEC)
    p.add_argument("--format", choices=["auto", "jsonl", "json", "markdown", "md", "text", "txt"], default="auto")
    p.add_argument("--default-role", choices=["user", "assistant", "system", "tool"], default="user")
    p.add_argument("--session", default="main")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("create", help="Create an empty .capsule file")
    p.add_argument("output")
    p.add_argument("--title", default="Untitled capsule")
    p.add_argument("--codec", choices=codec_choices, default=DEFAULT_CODEC)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("append", help="Append one conversation turn")
    p.add_argument("capsule")
    p.add_argument("--role", required=True, choices=["user", "assistant", "system", "tool"])
    p.add_argument("--text")
    p.add_argument("--session", default="main")
    p.add_argument("--no-extract", action="store_true")
    p.set_defaults(func=cmd_append)

    p = sub.add_parser("import-jsonl", help="Import role/content JSONL")
    p.add_argument("capsule")
    p.add_argument("source")
    p.add_argument("--session", default="main")
    p.set_defaults(func=cmd_import_jsonl)

    p = sub.add_parser("import-chat", help="Import JSON/JSONL/Markdown/plain-text chat exports")
    p.add_argument("capsule")
    p.add_argument("source")
    p.add_argument("--format", choices=["auto", "jsonl", "json", "markdown", "md", "text", "txt"], default="auto")
    p.add_argument("--default-role", choices=["user", "assistant", "system", "tool"], default="user")
    p.add_argument("--session", default="main")
    p.set_defaults(func=cmd_import_chat)

    p = sub.add_parser("import-file", help="Alias for import-chat")
    p.add_argument("capsule")
    p.add_argument("source")
    p.add_argument("--format", choices=["auto", "jsonl", "json", "markdown", "md", "text", "txt"], default="auto")
    p.add_argument("--default-role", choices=["user", "assistant", "system", "tool"], default="user")
    p.add_argument("--session", default="main")
    p.set_defaults(func=cmd_import_chat)

    p = sub.add_parser("search", help="Search dictionary and compressed archive index")
    p.add_argument("capsule")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--entries-only", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("resume", help="Build a minimal context packet for a new conversation")
    p.add_argument("capsule")
    p.add_argument("--task")
    p.add_argument("--budget", type=int, default=1000)
    p.add_argument("--recent", type=int, default=2)
    p.add_argument("--output")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("inspect", help="Show capsule statistics")
    p.add_argument("capsule")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("new-session", help="Create a branch/session inside a capsule")
    p.add_argument("capsule")
    p.add_argument("--title", default="New conversation")
    p.set_defaults(func=cmd_new_session)

    p = sub.add_parser("add-entry", help="Add or correct an authoritative dictionary entry")
    p.add_argument("capsule")
    p.add_argument("--kind", required=True)
    p.add_argument("--text")
    p.add_argument("--session", default="main")
    p.set_defaults(func=cmd_add_entry)

    p = sub.add_parser("attach", help="Attach a file with compressed payload and AI-readable sidecar")
    p.add_argument("capsule")
    p.add_argument("file")
    p.add_argument("--session", default="main")
    p.add_argument("--source-turn", type=int)
    p.set_defaults(func=cmd_attach)

    p = sub.add_parser("get", help="Retrieve an exact entry (E#), turn (T#), or attachment metadata (A#)")
    p.add_argument("capsule")
    p.add_argument("id")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("extract-attachment", help="Extract an attachment payload by A#")
    p.add_argument("capsule")
    p.add_argument("id")
    p.add_argument("output")
    p.set_defaults(func=cmd_extract_attachment)

    p = sub.add_parser("export", help="Export the lossless archive")
    p.add_argument("capsule")
    p.add_argument("output")
    p.add_argument("--format", choices=["jsonl", "markdown"], default="markdown")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("compact", help="Repack the capsule and remove stale tail indexes")
    p.add_argument("capsule")
    p.set_defaults(func=cmd_compact)

    p = sub.add_parser("verify", help="Verify packed index, raw blocks, attachments, and turn hashes")
    p.add_argument("capsule")
    p.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        cmd_menu(args)
        return
    try:
        args.func(args)
    except CapsuleError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
