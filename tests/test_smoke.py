import json
from pathlib import Path

from lqcc.capsule import Capsule, import_jsonl


def test_end_to_end(tmp_path: Path):
    path = tmp_path / "demo.capsule"
    with Capsule.create(path, title="Demo") as cap:
        cap.append_turn(role="user", content="Decision: the project is called LQCC and it reduces active context tokens.")
        cap.append_turn(role="assistant", content="The first version uses a .capsule file and budgeted retrieval.")
        cap.append_turn(role="user", content="Warning: do not make it a normal summarizer; it must preserve raw history.")
        hits = cap.search("What must LQCC preserve?", limit=5)
        assert hits
        packet = cap.resume("Continue designing LQCC", budget=400)
        assert "LQCC" in packet
        assert cap.stats()["turns"] == 3
        assert cap.stats()["format_version"] == "0.7"
        assert cap.verify() == []


def test_jsonl_import_and_resume(tmp_path: Path):
    source = tmp_path / "chat.jsonl"
    source.write_text(
        json.dumps({"role": "user", "content": "Requirement: LQCC must work locally without API keys."})
        + "\n"
        + json.dumps({"role": "assistant", "content": "Use deterministic local extraction and search."})
        + "\n",
        encoding="utf-8",
    )
    path = tmp_path / "import.capsule"
    with Capsule.create(path, title="Import") as cap:
        turns, atoms = import_jsonl(cap, source)
        assert turns == 2
        assert atoms >= 1
        packet = cap.resume("What is the local-first requirement?", budget=300, recent=0)
        assert "API" in packet or "locally" in packet


def test_attachment_roundtrip(tmp_path: Path):
    file_path = tmp_path / "notes.md"
    file_path.write_text("Decision: active context should stay small while raw history stays complete.", encoding="utf-8")
    capsule_path = tmp_path / "attachments.capsule"
    restored = tmp_path / "restored.md"
    with Capsule.create(capsule_path, title="Attachments") as cap:
        aid = cap.attach_file(file_path)
        assert aid == 1
        hits = cap.search("active context raw history", limit=5)
        assert hits
        meta = cap.get_attachment(aid, output=restored)
        assert meta["filename"] == "notes.md"
        assert restored.read_text(encoding="utf-8") == file_path.read_text(encoding="utf-8")
        assert cap.verify() == []


def test_compact_keeps_data(tmp_path: Path):
    path = tmp_path / "compact.capsule"
    with Capsule.create(path, title="Compact") as cap:
        cap.append_turn(role="user", content="Decision: compact should remove stale tail indexes.")
        cap.append_turn(role="assistant", content="Compaction repacks the capsule while preserving turns.")
        before = cap.stats()["turns"]
        cap.compact()
        after = cap.stats()["turns"]
        assert before == after == 2
        assert cap.verify() == []


def test_import_chat_plain_text(tmp_path: Path):
    from lqcc.capsule import import_chat_file
    source = tmp_path / "chat.txt"
    source.write_text(
        "User: Requirement: LQCC should import copied chats.\n"
        "Assistant: It can parse User and Assistant markers.\n"
        "User: Decision: browser support is not required for v0.7.\n",
        encoding="utf-8",
    )
    path = tmp_path / "text.capsule"
    with Capsule.create(path, title="Text") as cap:
        turns, atoms = import_chat_file(cap, source, input_format="text")
        assert turns == 3
        assert atoms >= 1
        packet = cap.resume("Is browser support required for v0.7?", budget=260, recent=0)
        assert "browser" in packet.lower() or "浏览器" in packet


def test_cli_build_smoke(tmp_path: Path):
    from lqcc.cli import main
    source = tmp_path / "chat.jsonl"
    source.write_text(
        json.dumps({"role": "user", "content": "Requirement: CLI build should create capsules."}) + "\n",
        encoding="utf-8",
    )
    path = tmp_path / "cli.capsule"
    main(["build", str(source), "-o", str(path), "--title", "CLI"])
    assert path.exists()
    main(["verify", str(path)])


def test_cli_beginner_quick_and_defaults(tmp_path: Path, capsys):
    from lqcc.cli import main
    source = tmp_path / "easy.txt"
    source.write_text(
        "User: Decision: LQCC needs one-command beginner UX.\n"
        "Assistant: Add lqcc quick and make resume task optional.\n",
        encoding="utf-8",
    )
    capsule = tmp_path / "easy.capsule"
    main(["quick", str(source), "-o", str(capsule), "--force", "--budget", "300"])
    captured = capsys.readouterr().out
    assert capsule.exists()
    assert "Copy this into your next AI chat" in captured
    main(["resume", str(capsule), "--budget", "250"])
    captured = capsys.readouterr().out
    assert "LQCC" in captured


def test_cli_build_output_default_and_search(tmp_path: Path, capsys, monkeypatch):
    from lqcc.cli import main
    source = tmp_path / "default.md"
    source.write_text("User: Requirement: output should default to source.capsule.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["build", str(source), "--force"])
    assert (tmp_path / "default.capsule").exists()
    main(["search", str(tmp_path / "default.capsule"), "output default"])
    captured = capsys.readouterr().out
    assert "output" in captured.lower()


def test_daemon_http_endpoints(tmp_path: Path):
    import json
    import threading
    import urllib.request
    from lqcc.auto import make_daemon_server

    path = tmp_path / "daemon.capsule"
    with Capsule.create(path, title="Daemon"):
        pass
    server = make_daemon_server(path, port=0)
    host, port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def post(endpoint, payload):
            req = urllib.request.Request(
                f"http://{host}:{port}{endpoint}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))

        out = post("/append", {"role": "user", "content": "Decision: daemon should write automatically."})
        assert out["ok"] and out["turn_id"] == 1
        out = post("/resume", {"task": "automatic writing", "budget": 300})
        assert out["ok"] and "packet" in out
        out = post("/search", {"query": "daemon automatically", "limit": 3})
        assert out["ok"] and out["hits"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
