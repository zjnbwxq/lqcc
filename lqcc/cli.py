from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .capsule import Capsule, CapsuleError, import_chat_file, import_jsonl
from .codec import DEFAULT_CODEC, SUPPORTED_CODECS
from .text import estimate_tokens


def _text_arg(value: str | None) -> str:
    if value is not None:
        return value
    if sys.stdin.isatty():
        raise CapsuleError("Provide --text or pipe text through stdin")
    return sys.stdin.read()


def cmd_build(args: argparse.Namespace) -> None:
    with Capsule.create(args.output, title=args.title, codec=args.codec, overwrite=args.force) as cap:
        turns, atoms = import_chat_file(
            cap,
            args.source,
            session_id=args.session,
            input_format=args.format,
            default_role=args.default_role,
        )
        stats = cap.stats()
    print(
        f"created {args.output}; imported {turns} turns; "
        f"dictionary updates: {atoms}; active_entries={stats['active_entries']}"
    )


def cmd_create(args: argparse.Namespace) -> None:
    with Capsule.create(args.output, title=args.title, codec=args.codec, overwrite=args.force) as cap:
        print(json.dumps(cap.stats(), ensure_ascii=False, indent=2))


def cmd_append(args: argparse.Namespace) -> None:
    content = _text_arg(args.text)
    with Capsule(args.capsule) as cap:
        turn_id, atoms = cap.append_turn(
            role=args.role,
            content=content,
            session_id=args.session,
            extract=not args.no_extract,
        )
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
    for hit in hits:
        label = (
            f"E{hit.hit_id}" if hit.hit_type == "entry"
            else f"A{hit.hit_id}" if hit.hit_type == "attachment"
            else f"T{hit.hit_id}"
        )
        kind = hit.kind or hit.hit_type
        print(f"{label} [{kind}] score={hit.score:.3f}\n{hit.content}\n")


def cmd_resume(args: argparse.Namespace) -> None:
    with Capsule(args.capsule, read_only=True) as cap:
        packet = cap.resume(args.task, budget=args.budget, recent=args.recent)
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
            raise CapsuleError("ID must start with T (turn), E (entry), or A (attachment)")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lqcc",
        description="Local-first queryable context capsules for token-efficient AI continuity.",
    )
    parser.add_argument("--version", action="version", version=f"lqcc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    codec_choices = sorted(SUPPORTED_CODECS)

    p = sub.add_parser("build", help="Create a .capsule from a chat export in one step")
    p.add_argument("source")
    p.add_argument("-o", "--output", required=True)
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
    p.add_argument("--no-extract", action="store_true", help="Archive only; skip dictionary extraction")
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
    p.add_argument("--task", required=True)
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
    try:
        args.func(args)
    except CapsuleError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
