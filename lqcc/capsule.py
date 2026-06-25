from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import struct
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .codec import DEFAULT_CODEC, SUPPORTED_CODECS, compress_bytes, decompress_bytes
from .extract import Atom, extract_atoms
from .text import (
    SKETCH_BYTES,
    best_excerpt,
    build_query_sketch,
    estimate_tokens,
    jaccard_terms,
    lexical_features,
    lexical_terms,
    normalize_text,
    sketch_maybe_contains,
    sketch_query_score,
    strong_anchors,
    text_fingerprint,
    weighted_query_coverage,
)

FORMAT_VERSION = "0.7"
DEFAULT_BLOCK_TURNS = 16

MAGIC = b"LQCCPACK1\n"       # file magic; no SQLite
SECTION_MAGIC = b"LQSC"
FOOTER_MAGIC = b"LQCCFTR1"   # 8 bytes
SECTION_HEADER = struct.Struct(">4s1sQIQ")  # magic, kind, id, meta_len, payload_len
FOOTER = struct.Struct(">8sQQ32s")          # magic, index_offset, index_len, sha256(index_blob)
INDEX_CODEC = "zlib9"  # fixed so the index can be read before metadata exists

ENTRY_KINDS = {"FACT", "DECISION", "REQUIREMENT", "TASK", "PREFERENCE", "WARNING", "TRACE", "ARTIFACT"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SearchHit:
    hit_type: str
    hit_id: int
    score: float
    kind: str | None
    content: str
    source_turn_id: int | None = None


class CapsuleError(RuntimeError):
    pass


def _json_dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_loads(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))


def _index_compress(raw: bytes) -> bytes:
    # Use zlib directly to keep index decoding dependency-free.
    return zlib.compress(raw, level=9)


def _index_decompress(blob: bytes) -> bytes:
    return zlib.decompress(blob)


def _hex_sketch(text: str, max_terms: int = 64) -> str:
    return build_query_sketch(lexical_features(text, max_terms=max_terms)).hex()


def _sketch_bytes(record: dict) -> bytes:
    try:
        return bytes.fromhex(record.get("query_sketch", ""))
    except Exception:
        return b""


class Capsule:
    """LQCC v0.7 packed single-file context dictionary.

    v0.7 keeps SQLite out from the .capsule runtime format. The file is an
    appendable binary pack:

        MAGIC
        section(raw block / attachment)*
        compressed index
        footer(index offset + index hash)

    Readers load only the compressed tail index first. Raw turns and attachment
    bytes are stored in compressed sections and decoded locally only when a
    query needs exact evidence. This is deliberately closer to a codec than a
    database, while keeping the product usable through the same CLI.
    """

    def __init__(self, path: str | os.PathLike[str], *, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        if not self.path.exists():
            raise CapsuleError(f"Capsule does not exist: {self.path}")
        self.index = self._read_index()
        self._check_format()

    @classmethod
    def create(
        cls,
        path: str | os.PathLike[str],
        *,
        title: str = "Untitled capsule",
        codec: str = DEFAULT_CODEC,
        overwrite: bool = False,
        block_turns: int = DEFAULT_BLOCK_TURNS,
    ) -> "Capsule":
        path = Path(path)
        if codec not in SUPPORTED_CODECS:
            raise CapsuleError(f"Unsupported codec {codec!r}; choose from {sorted(SUPPORTED_CODECS)}")
        if path.exists():
            if not overwrite:
                raise CapsuleError(f"File already exists: {path}")
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        now = utc_now()
        index = {
            "meta": {
                "format": "LQCC packed capsule",
                "format_version": FORMAT_VERSION,
                "storage": "packed-blocks+tail-index",
                "title": title,
                "codec": codec,
                "created_at": now,
                "updated_at": now,
                "capsule_id": str(uuid.uuid4()),
                "sketch_bytes": str(SKETCH_BYTES),
                "block_turns": str(max(1, int(block_turns))),
            },
            "sessions": [{"id": "main", "title": "Main session", "created_at": now}],
            "turns": [],
            "raw_blocks": [],
            "entries": [],
            "entry_sources": [],
            "attachments": [],
            "counters": {"turn": 0, "block": 0, "entry": 0, "attachment": 0},
        }
        with open(path, "wb") as fh:
            fh.write(MAGIC)
        obj = cls.__new__(cls)
        obj.path = path
        obj.read_only = False
        obj.index = index
        obj._commit()
        return cls(path)

    def close(self) -> None:
        return None

    def __enter__(self) -> "Capsule":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---------- low-level file format ----------
    def _read_index(self) -> dict:
        with open(self.path, "rb") as fh:
            head = fh.read(len(MAGIC))
            if head != MAGIC:
                raise CapsuleError(f"Not a packed LQCC capsule: {self.path}")
            if self.path.stat().st_size < len(MAGIC) + FOOTER.size:
                raise CapsuleError(f"Missing LQCC footer: {self.path}")
            fh.seek(-FOOTER.size, os.SEEK_END)
            footer_raw = fh.read(FOOTER.size)
            magic, index_offset, index_len, sha = FOOTER.unpack(footer_raw)
            if magic != FOOTER_MAGIC:
                raise CapsuleError(f"Missing packed LQCC footer: {self.path}")
            fh.seek(index_offset)
            index_blob = fh.read(index_len)
            if len(index_blob) != index_len:
                raise CapsuleError("Truncated LQCC index")
            if hashlib.sha256(index_blob).digest() != sha:
                raise CapsuleError("LQCC index hash mismatch")
            return _json_loads(_index_decompress(index_blob))

    def _check_format(self) -> None:
        meta = self.index.get("meta", {})
        version = str(meta.get("format_version", ""))
        if version != FORMAT_VERSION:
            raise CapsuleError(f"Unsupported capsule format {version}; this build reads {FORMAT_VERSION}")
        self.format_version = version

    def _write_section(self, fh, *, kind: str, ident: int, meta: dict, payload: bytes) -> dict:
        if len(kind) != 1:
            raise CapsuleError("Section kind must be one byte")
        offset = fh.tell()
        meta_raw = _json_dumps(meta)
        header = SECTION_HEADER.pack(SECTION_MAGIC, kind.encode("ascii"), int(ident), len(meta_raw), len(payload))
        fh.write(header)
        fh.write(meta_raw)
        fh.write(payload)
        return {
            "offset": offset,
            "length": len(header) + len(meta_raw) + len(payload),
            "meta_len": len(meta_raw),
            "payload_len": len(payload),
        }

    def _read_section(self, section: dict, expected_kind: str | None = None) -> tuple[dict, bytes]:
        with open(self.path, "rb") as fh:
            fh.seek(int(section["offset"]))
            raw_header = fh.read(SECTION_HEADER.size)
            if len(raw_header) != SECTION_HEADER.size:
                raise CapsuleError("Truncated LQCC section header")
            magic, kind_b, ident, meta_len, payload_len = SECTION_HEADER.unpack(raw_header)
            if magic != SECTION_MAGIC:
                raise CapsuleError("Bad LQCC section magic")
            kind = kind_b.decode("ascii")
            if expected_kind is not None and kind != expected_kind:
                raise CapsuleError(f"Expected section {expected_kind}, found {kind}")
            meta = _json_loads(fh.read(meta_len))
            payload = fh.read(payload_len)
            if len(payload) != payload_len:
                raise CapsuleError("Truncated LQCC section payload")
            return meta, payload

    def _append_index_blob(self, fh) -> None:
        self.index["meta"]["updated_at"] = utc_now()
        raw = _json_dumps(self.index)
        blob = _index_compress(raw)
        offset = fh.tell()
        fh.write(blob)
        fh.write(FOOTER.pack(FOOTER_MAGIC, offset, len(blob), hashlib.sha256(blob).digest()))

    def _commit(self) -> None:
        if self.read_only:
            raise CapsuleError("Capsule is read-only")
        with open(self.path, "ab") as fh:
            self._append_index_blob(fh)

    def meta(self, key: str, default: str | None = None) -> str | None:
        value = self.index.get("meta", {}).get(key, default)
        return str(value) if value is not None else None

    def set_meta(self, key: str, value: str) -> None:
        self.index.setdefault("meta", {})[key] = value
        self._commit()

    def _block_cap(self) -> int:
        try:
            return max(1, int(self.meta("block_turns", str(DEFAULT_BLOCK_TURNS)) or DEFAULT_BLOCK_TURNS))
        except ValueError:
            return DEFAULT_BLOCK_TURNS

    # ---------- sessions ----------
    def new_session(self, title: str) -> str:
        session_id = uuid.uuid4().hex[:12]
        self.index["sessions"].append({"id": session_id, "title": title, "created_at": utc_now()})
        self._commit()
        return session_id

    def _ensure_session(self, session_id: str) -> None:
        if not any(s["id"] == session_id for s in self.index.get("sessions", [])):
            raise CapsuleError(f"Unknown session: {session_id}")

    # ---------- raw block storage ----------
    def _encode_block(self, items: list[dict], codec: str) -> tuple[bytes, int, str]:
        raw = _json_dumps(items)
        payload = compress_bytes(raw, codec)
        return payload, len(raw), hashlib.sha256(raw).hexdigest()

    def _decode_block_items(self, block: dict) -> list[dict]:
        _, payload = self._read_section(block["section"], expected_kind="B")
        raw = decompress_bytes(payload, block["codec"])
        if hashlib.sha256(raw).hexdigest() != block["sha256"]:
            raise CapsuleError(f"Raw block hash mismatch B{block['id']}")
        return _json_loads(raw)

    def _write_raw_block(self, fh, *, session_id: str, items: list[dict]) -> dict:
        codec = self.meta("codec", DEFAULT_CODEC) or DEFAULT_CODEC
        block_id = int(self.index["counters"].get("block", 0)) + 1
        payload, raw_bytes, sha = self._encode_block(items, codec)
        meta = {
            "block_id": block_id,
            "session_id": session_id,
            "first_seq": items[0]["seq"],
            "last_seq": items[-1]["seq"],
            "turn_count": len(items),
            "codec": codec,
            "sha256": sha,
        }
        section = self._write_section(fh, kind="B", ident=block_id, meta=meta, payload=payload)
        block = {
            "id": block_id,
            "session_id": session_id,
            "first_seq": items[0]["seq"],
            "last_seq": items[-1]["seq"],
            "first_turn_id": items[0]["id"],
            "last_turn_id": items[-1]["id"],
            "turn_count": len(items),
            "codec": codec,
            "raw_bytes": raw_bytes,
            "compressed_bytes": len(payload),
            "sha256": sha,
            "section": section,
            "created_at": utc_now(),
        }
        self.index["raw_blocks"].append(block)
        self.index["counters"]["block"] = block_id
        for item in items:
            for t in self.index["turns"]:
                if t["id"] == item["id"]:
                    t["block_id"] = block_id
                    break
        return block

    def append_turn(
        self,
        *,
        role: str,
        content: str,
        session_id: str = "main",
        created_at: str | None = None,
        extract: bool = True,
    ) -> tuple[int, int]:
        results = self.append_many(
            [{"role": role, "content": content, "session_id": session_id, "created_at": created_at, "extract": extract}],
            session_id=session_id,
        )
        return results[0]

    def append_many(self, items_in: Sequence[dict], *, session_id: str = "main") -> list[tuple[int, int]]:
        self._ensure_session(session_id)
        staged_by_session: dict[str, list[dict]] = {}
        results: list[tuple[int, int]] = []
        # Assign IDs and dictionary entries first, then write raw blocks once.
        for src in items_in:
            role = str(src.get("role", "")).strip().lower()
            if role not in {"user", "assistant", "system", "tool"}:
                raise CapsuleError("role must be one of: user, assistant, system, tool")
            content = normalize_text(str(src.get("content") or src.get("text") or ""))
            if not content:
                raise CapsuleError("Cannot append an empty turn")
            sid = str(src.get("session_id") or session_id)
            self._ensure_session(sid)
            sha = text_fingerprint(content)
            existing = next((t for t in self.index["turns"] if t["session_id"] == sid and t["role"] == role and t["sha256"] == sha), None)
            if existing is not None:
                results.append((int(existing["id"]), 0))
                continue
            turn_id = int(self.index["counters"].get("turn", 0)) + 1
            seq = 1 + max((int(t["seq"]) for t in self.index["turns"] if t["session_id"] == sid), default=0)
            now = src.get("created_at") or utc_now()
            turn = {
                "id": turn_id,
                "session_id": sid,
                "seq": seq,
                "block_id": None,
                "role": role,
                "created_at": now,
                "query_sketch": _hex_sketch(content, max_terms=64),
                "raw_bytes": len(content.encode("utf-8")),
                "estimated_tokens": estimate_tokens(content),
                "sha256": sha,
            }
            self.index["turns"].append(turn)
            self.index["counters"]["turn"] = turn_id
            staged_by_session.setdefault(sid, []).append({"id": turn_id, "seq": seq, "role": role, "created_at": now, "content": content})

            atom_count = 0
            if bool(src.get("extract", True)):
                authority = {"user": 1.0, "system": 0.95, "assistant": 0.72, "tool": 0.55}[role]
                for atom in extract_atoms(content, role):
                    if self._upsert_atom(atom, authority, sid, turn_id, None):
                        atom_count += 1
            results.append((turn_id, atom_count))

        if not results:
            return []
        cap = self._block_cap()
        with open(self.path, "ab") as fh:
            for sid, staged in staged_by_session.items():
                for i in range(0, len(staged), cap):
                    self._write_raw_block(fh, session_id=sid, items=staged[i : i + cap])
            self._append_index_blob(fh)
        return results

    # ---------- dictionary entries ----------
    def _candidate_entries(self, kind: str, content: str, limit: int = 20) -> list[dict]:
        qf = lexical_features(content, max_terms=48)
        rows = [e for e in self.index.get("entries", []) if e.get("kind") == kind and e.get("status") == "active"]
        coarse: list[tuple[float, dict]] = []
        for row in rows:
            score = sketch_query_score(_sketch_bytes(row), qf)
            if score > 0:
                coarse.append((score, row))
        coarse.sort(key=lambda item: (-item[0], -int(item[1]["id"])))
        return [row for _, row in coarse[:limit]]

    def _upsert_atom(self, atom: Atom, authority: float, session_id: str, turn_id: int | None, attachment_id: int | None) -> bool:
        content = normalize_text(atom.content)
        fingerprint = text_fingerprint(f"{atom.kind}\n{content}")
        exact = next((e for e in self.index["entries"] if e.get("fingerprint") == fingerprint and e.get("status") == "active"), None)
        if exact is not None:
            if turn_id is not None:
                pair = {"entry_id": exact["id"], "turn_id": turn_id}
                if pair not in self.index["entry_sources"]:
                    self.index["entry_sources"].append(pair)
            return False

        terms = lexical_terms(content, max_terms=48)
        similar: dict | None = None
        best_similarity = 0.0
        for row in self._candidate_entries(atom.kind, content):
            sim = jaccard_terms(terms, lexical_terms(row["content"], max_terms=48))
            if sim > best_similarity:
                best_similarity = sim
                similar = row

        now = utc_now()
        supersedes_id: int | None = None
        version = 1
        if similar is not None and best_similarity >= 0.80:
            if authority >= float(similar.get("authority", 0.0)):
                supersedes_id = int(similar["id"])
                version = int(similar.get("version", 1)) + 1
                similar["status"] = "superseded"
                similar["updated_at"] = now
            else:
                if turn_id is not None:
                    pair = {"entry_id": similar["id"], "turn_id": turn_id}
                    if pair not in self.index["entry_sources"]:
                        self.index["entry_sources"].append(pair)
                return False

        entry_id = int(self.index["counters"].get("entry", 0)) + 1
        entry = {
            "id": entry_id,
            "kind": atom.kind,
            "content": content,
            "query_sketch": _hex_sketch(content, max_terms=48),
            "confidence": float(atom.confidence),
            "authority": float(authority),
            "status": "active",
            "version": version,
            "fingerprint": fingerprint,
            "source_session_id": session_id,
            "source_turn_id": turn_id,
            "source_attachment_id": attachment_id,
            "supersedes_id": supersedes_id,
            "created_at": now,
            "updated_at": now,
        }
        self.index["entries"].append(entry)
        self.index["counters"]["entry"] = entry_id
        if turn_id is not None:
            self.index["entry_sources"].append({"entry_id": entry_id, "turn_id": turn_id})
        return True

    def add_entry(self, *, kind: str, content: str, session_id: str = "main", source_turn_id: int | None = None) -> int:
        kind = kind.upper().strip()
        if kind not in ENTRY_KINDS:
            raise CapsuleError(f"Unsupported entry kind: {kind}. Choose from {sorted(ENTRY_KINDS)}")
        if source_turn_id is None:
            source_turn_id, _ = self.append_turn(role="system", content=f"Manual {kind}: {content}", session_id=session_id, extract=False)
        atom = Atom(kind=kind, content=content, confidence=1.0)
        self._upsert_atom(atom, 1.0, session_id, source_turn_id, None)
        self._commit()
        fingerprint = text_fingerprint(f"{kind}\n{normalize_text(content)}")
        row = next((e for e in reversed(self.index["entries"]) if e.get("fingerprint") == fingerprint), None)
        return int(row["id"]) if row else -1

    # ---------- retrieval helpers ----------
    def _turn_record(self, turn_id: int) -> dict | None:
        return next((t for t in self.index.get("turns", []) if int(t["id"]) == int(turn_id)), None)

    def _block_record(self, block_id: int) -> dict | None:
        return next((b for b in self.index.get("raw_blocks", []) if int(b["id"]) == int(block_id)), None)

    def get_turn(self, turn_id: int) -> dict:
        record = self._turn_record(turn_id)
        if record is None:
            raise CapsuleError(f"Turn not found: T{turn_id}")
        block = self._block_record(int(record["block_id"])) if record.get("block_id") is not None else None
        if block is None:
            raise CapsuleError(f"Missing raw block for T{turn_id}")
        for item in self._decode_block_items(block):
            if int(item["id"]) == int(turn_id):
                if text_fingerprint(item["content"]) != record["sha256"]:
                    raise CapsuleError(f"Hash mismatch in T{turn_id}")
                out = dict(record)
                out["content"] = item["content"]
                return out
        raise CapsuleError(f"T{turn_id} not found in raw block B{block['id']}")

    def get_entry(self, entry_id: int) -> dict:
        row = next((e for e in self.index.get("entries", []) if int(e["id"]) == int(entry_id)), None)
        if row is None:
            raise CapsuleError(f"Entry not found: E{entry_id}")
        return dict(row)

    def recent_turns(self, *, limit: int = 4, session_id: str | None = None) -> list[dict]:
        rows = [t for t in self.index.get("turns", []) if session_id is None or t.get("session_id") == session_id]
        rows = sorted(rows, key=lambda r: int(r["id"]))[-limit:]
        return [self.get_turn(int(row["id"])) for row in rows]

    # ---------- multimodal / artifacts ----------
    @staticmethod
    def _media_type(mime: str, filename: str) -> str:
        lower = filename.lower()
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("video/"):
            return "video"
        if mime == "application/pdf" or lower.endswith(".pdf"):
            return "pdf"
        if mime.startswith("text/") or lower.endswith((".md", ".txt", ".py", ".json", ".yaml", ".yml", ".csv", ".tex")):
            return "text"
        return "binary"

    @staticmethod
    def _attachment_sidecar(path: Path, media_type: str, mime: str) -> tuple[dict, str]:
        meta: dict[str, Any] = {"mime_type": mime, "media_type": media_type}
        sidecar = ""
        try:
            if media_type == "image":
                try:
                    from PIL import Image  # type: ignore
                    with Image.open(path) as im:
                        meta.update({"width": im.width, "height": im.height, "mode": im.mode, "format": im.format})
                        sidecar = f"Image {path.name}: {im.width}x{im.height}, mode={im.mode}, format={im.format}."
                except Exception:
                    sidecar = f"Image {path.name}: metadata extraction unavailable."
            elif media_type == "pdf":
                try:
                    from pypdf import PdfReader  # type: ignore
                    reader = PdfReader(str(path))
                    meta["pages"] = len(reader.pages)
                    extracted: list[str] = []
                    for page in reader.pages[:3]:
                        try:
                            extracted.append(page.extract_text() or "")
                        except Exception:
                            pass
                    text = normalize_text("\n".join(extracted))
                    sidecar = f"PDF {path.name}: {meta['pages']} pages. " + text[:2500]
                except Exception:
                    sidecar = f"PDF {path.name}: text extraction unavailable."
            elif media_type == "text":
                raw = path.read_bytes()[:200_000]
                for enc in ("utf-8", "utf-16", "latin-1"):
                    try:
                        text = raw.decode(enc)
                        meta["text_encoding"] = enc
                        sidecar = normalize_text(text)[:5000]
                        break
                    except Exception:
                        continue
            else:
                sidecar = f"Attachment {path.name}: {media_type}, {path.stat().st_size} bytes."
        except Exception as exc:
            meta["sidecar_error"] = str(exc)
            sidecar = f"Attachment {path.name}: {media_type}, sidecar extraction failed."
        return meta, sidecar

    def attach_file(self, file_path: str | os.PathLike[str], *, session_id: str = "main", source_turn_id: int | None = None) -> int:
        self._ensure_session(session_id)
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise CapsuleError(f"Attachment file not found: {path}")
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        existing = next((a for a in self.index["attachments"] if a.get("sha256") == sha), None)
        if existing is not None:
            return int(existing["id"])
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        media_type = self._media_type(mime, path.name)
        meta, sidecar = self._attachment_sidecar(path, media_type, mime)
        meta.update({"filename": path.name, "raw_bytes": len(raw), "sha256": sha})
        codec = self.meta("codec", DEFAULT_CODEC) or DEFAULT_CODEC
        payload = compress_bytes(raw, codec)
        attachment_id = int(self.index["counters"].get("attachment", 0)) + 1
        section_meta = {"attachment_id": attachment_id, "filename": path.name, "codec": codec, "sha256": sha}
        with open(self.path, "ab") as fh:
            section = self._write_section(fh, kind="A", ident=attachment_id, meta=section_meta, payload=payload)
            rec = {
                "id": attachment_id,
                "session_id": session_id,
                "source_turn_id": source_turn_id,
                "filename": path.name,
                "mime_type": mime,
                "media_type": media_type,
                "codec": codec,
                "raw_bytes": len(raw),
                "compressed_bytes": len(payload),
                "sha256": sha,
                "metadata": meta,
                "sidecar_text": sidecar,
                "query_sketch": _hex_sketch(f"{path.name}\n{mime}\n{media_type}\n{sidecar}", max_terms=96),
                "created_at": utc_now(),
                "section": section,
            }
            self.index["attachments"].append(rec)
            self.index["counters"]["attachment"] = attachment_id
            summary = f"Artifact {path.name} ({media_type}, {len(raw)} bytes): {sidecar[:700]}"
            self._upsert_atom(Atom("ARTIFACT", summary, 1.0), 1.0, session_id, source_turn_id, attachment_id)
            self._append_index_blob(fh)
        return attachment_id

    def get_attachment(self, attachment_id: int, output: str | os.PathLike[str] | None = None) -> dict:
        row = next((a for a in self.index.get("attachments", []) if int(a["id"]) == int(attachment_id)), None)
        if row is None:
            raise CapsuleError(f"Attachment not found: A{attachment_id}")
        _, payload = self._read_section(row["section"], expected_kind="A")
        raw = decompress_bytes(payload, row["codec"])
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise CapsuleError(f"Attachment hash mismatch A{attachment_id}")
        if output:
            Path(output).write_bytes(raw)
        out = dict(row)
        out.pop("section", None)
        out.pop("query_sketch", None)
        return out

    def search_attachments(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        qf = lexical_features(query, max_terms=64, expand_query=True)
        hits: list[SearchHit] = []
        for row in self.index.get("attachments", []):
            coarse = sketch_query_score(_sketch_bytes(row), qf)
            if coarse <= 0:
                continue
            text = f"{row['filename']} {row['mime_type']} {row['media_type']} {row.get('sidecar_text','')}"
            exact = weighted_query_coverage(qf, lexical_features(text, max_terms=128))
            score = 0.25 * coarse + 0.75 * exact
            if score > 0:
                hits.append(SearchHit("attachment", int(row["id"]), score, str(row["media_type"]).upper(), best_excerpt(text, query, max_chars=800), row.get("source_turn_id")))
        hits.sort(key=lambda h: (-h.score, -h.hit_id))
        return hits[:limit]

    # ---------- search / resume ----------
    @staticmethod
    def _kind_boost(kind: str | None) -> float:
        return {"DECISION": 1.38, "REQUIREMENT": 1.34, "WARNING": 1.30, "TASK": 1.18, "PREFERENCE": 1.16, "FACT": 1.06, "TRACE": 1.00, "ARTIFACT": 1.00}.get(kind or "", 1.0)

    @staticmethod
    def _anchor_factor(anchors: set[str], content: str) -> float:
        if not anchors:
            return 1.0
        lower = normalize_text(content).lower()
        ratio = sum(1 for a in anchors if a in lower) / len(anchors)
        return 0.10 if ratio <= 0 else 0.65 + 2.35 * ratio

    def _idf_query_features(self, query: str) -> tuple[dict[str, float], set[str]]:
        base = lexical_features(query, max_terms=64, expand_query=True)
        sketches: list[bytes] = []
        sketches.extend(_sketch_bytes(r) for r in self.index.get("turns", []))
        sketches.extend(_sketch_bytes(r) for r in self.index.get("entries", []) if r.get("status") == "active")
        sketches.extend(_sketch_bytes(r) for r in self.index.get("attachments", []))
        n_docs = max(1, len(sketches))
        weighted: dict[str, float] = {}
        for term, weight in base.items():
            df = sum(1 for sketch in sketches if sketch_maybe_contains(sketch, term))
            if df == 0:
                continue
            weighted[term] = weight * (1.0 + max(0.0, (n_docs - df) / n_docs))
        return weighted or base, strong_anchors(query)

    def _entry_hits(self, query: str, *, limit: int) -> list[SearchHit]:
        qf, anchors = self._idf_query_features(query)
        rows = [e for e in self.index.get("entries", []) if e.get("status") == "active"]
        max_id = max((int(r["id"]) for r in rows), default=1)
        hits: list[SearchHit] = []
        for row in rows:
            coarse = sketch_query_score(_sketch_bytes(row), qf)
            if coarse <= 0:
                continue
            exact = weighted_query_coverage(qf, lexical_features(row["content"], max_terms=96))
            score = (0.18 * coarse + 0.82 * exact) * self._kind_boost(row.get("kind"))
            score *= 0.62 + 0.28 * float(row.get("authority", 0.0)) + 0.10 * float(row.get("confidence", 0.0))
            score *= self._anchor_factor(anchors, row["content"])
            score *= 1.0 + 0.04 * (int(row["id"]) / max_id)
            if score > 0:
                hits.append(SearchHit("entry", int(row["id"]), score, row.get("kind"), row["content"], row.get("source_turn_id")))
        hits.sort(key=lambda h: (-h.score, -(h.source_turn_id or 0), -h.hit_id))
        return hits[:limit]

    def _next_assistant_turn(self, turn_id: int) -> dict | None:
        turn = self._turn_record(turn_id)
        if turn is None:
            return None
        sid = turn["session_id"]
        seq = int(turn["seq"])
        candidates = [t for t in self.index.get("turns", []) if t["session_id"] == sid and int(t["seq"]) > seq and t["role"] == "assistant"]
        if not candidates:
            return None
        nxt = min(candidates, key=lambda t: int(t["seq"]))
        return self.get_turn(int(nxt["id"]))

    def _turn_hits(self, query: str, *, limit: int) -> list[SearchHit]:
        qf, anchors = self._idf_query_features(query)
        rows = list(self.index.get("turns", []))
        max_id = max((int(r["id"]) for r in rows), default=1)
        coarse: list[tuple[float, int, str]] = []
        for row in rows:
            score = sketch_query_score(_sketch_bytes(row), qf)
            if score > 0:
                score *= 1.0 + 0.04 * (int(row["id"]) / max_id)
                coarse.append((score, int(row["id"]), row["role"]))
        coarse.sort(key=lambda x: (-x[0], -x[1]))
        hits: list[SearchHit] = []
        for coarse_score, turn_id, role in coarse[: max(32, limit * 8)]:
            turn = self.get_turn(turn_id)
            exact = weighted_query_coverage(qf, lexical_features(turn["content"], max_terms=128))
            score = (0.12 * coarse_score + 0.88 * exact) * self._anchor_factor(anchors, turn["content"])
            if role == "user":
                score *= 1.05
            if score <= 0:
                continue
            hits.append(SearchHit("turn", turn_id, score, role.upper(), best_excerpt(turn["content"], query, max_chars=820, max_sentences=4), turn_id))
            wants_answer = any(cue in normalize_text(query).lower() for cue in ("怎么", "如何", "回复", "是什么", "为什么", "what", "why", "how", "reply"))
            if role == "user" and wants_answer:
                reply = self._next_assistant_turn(turn_id)
                if reply is not None:
                    reply_id = int(reply["id"])
                    reply_exact = weighted_query_coverage(qf, lexical_features(reply["content"], max_terms=128))
                    reply_score = max(score * 0.96, 0.88 * reply_exact)
                    hits.append(SearchHit("turn", reply_id, reply_score, "ASSISTANT", best_excerpt(reply["content"], query, max_chars=820, max_sentences=4), reply_id))
        hits.sort(key=lambda h: (-h.score, -h.hit_id))
        return hits[:limit]

    def search(self, query: str, *, limit: int = 8, include_evidence: bool = True, include_attachments: bool = True) -> list[SearchHit]:
        query = normalize_text(query)
        hits = self._entry_hits(query, limit=max(limit * 3, 18))
        if include_attachments:
            hits.extend(self.search_attachments(query, limit=max(limit, 5)))
        if include_evidence:
            hits.extend(self._turn_hits(query, limit=max(limit * 3, 18)))
        best: dict[tuple[str, int], SearchHit] = {}
        for hit in hits:
            key = (hit.hit_type, hit.hit_id)
            if key not in best or hit.score > best[key].score:
                best[key] = hit
        merged = sorted(best.values(), key=lambda h: (-h.score, h.hit_type != "entry", -(h.source_turn_id or 0), -h.hit_id))
        out: list[SearchHit] = []
        seen: set[str] = set()
        for hit in merged:
            canonical = normalize_text(hit.content).lower()
            if canonical in seen:
                continue
            seen.add(canonical)
            out.append(hit)
            if len(out) >= limit:
                break
        return out

    def _latest_state_hits(self, *, limit: int = 12, window_turns: int = 28) -> list[SearchHit]:
        turns = self.index.get("turns", [])
        max_turn = max((int(t["id"]) for t in turns), default=0)
        cutoff = max(1, max_turn - window_turns + 1)
        active = [e for e in self.index.get("entries", []) if e.get("status") == "active" and (e.get("source_turn_id") is None or int(e.get("source_turn_id") or 0) >= cutoff)]
        priority = {"TASK": 1.35, "DECISION": 1.30, "REQUIREMENT": 1.25, "WARNING": 1.20, "PREFERENCE": 1.08, "ARTIFACT": 1.03, "FACT": 1.00, "TRACE": 0.90}
        hits: list[SearchHit] = []
        for row in active:
            source_turn_id = row.get("source_turn_id")
            source_turn = self._turn_record(int(source_turn_id)) if source_turn_id is not None else None
            source_role = source_turn.get("role", "tool") if source_turn else "tool"
            recency = ((int(source_turn_id or max_turn) / max_turn) if max_turn else 1.0)
            role_boost = 1.16 if source_role == "user" else 0.98
            score = priority.get(row.get("kind"), 0.9) * role_boost * (0.55 + 0.65 * recency)
            hits.append(SearchHit("entry", int(row["id"]), score, row.get("kind"), row["content"], source_turn_id))
        hits.sort(key=lambda h: (-h.score, -(h.source_turn_id or 0), -h.hit_id))
        selected: list[SearchHit] = []
        per_kind: dict[str, int] = {}
        for h in hits:
            k = h.kind or ""
            cap = 3 if k in {"DECISION", "REQUIREMENT", "TASK"} else 2
            if per_kind.get(k, 0) >= cap:
                continue
            selected.append(h)
            per_kind[k] = per_kind.get(k, 0) + 1
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _fit_text(text: str, max_tokens: int) -> str:
        if max_tokens <= 4:
            return ""
        if estimate_tokens(text) <= max_tokens:
            return text
        chars = max(80, int(len(text) * max_tokens / max(1, estimate_tokens(text))))
        truncated = text[:chars].rstrip()
        while estimate_tokens(truncated + "...") > max_tokens and chars > 40:
            chars = int(chars * 0.82)
            truncated = text[:chars].rstrip()
        return truncated + "..."

    def resume(self, task: str, *, budget: int = 1000, recent: int = 2) -> str:
        title = self.meta("title", "Untitled capsule") or "Untitled capsule"
        task = normalize_text(task)
        hits = self.search(task, limit=10, include_evidence=True, include_attachments=True)
        if len(hits) < 5:
            ids = {(h.hit_type, h.hit_id) for h in hits}
            for h in self._latest_state_hits(limit=10):
                if (h.hit_type, h.hit_id) not in ids:
                    hits.append(h)
                    ids.add((h.hit_type, h.hit_id))
        hits.sort(key=lambda h: (h.hit_type != "entry", -h.score, -(h.source_turn_id or 0)))
        lines: list[str] = []
        lines.append("You are continuing work from an LQCC .capsule context dictionary.")
        lines.append("Use this packet as the source of truth; do not ask for full chat history unless evidence is missing.\n")
        lines.append(f"Project: {title}")
        lines.append(f"Current task: {task}\n")
        lines.append("Relevant capsule entries:")
        remaining = max(80, budget - estimate_tokens("\n".join(lines)) - 60)
        used = 0
        for hit in hits:
            bullet = f"- [{hit.kind or hit.hit_type} {hit.hit_type[0].upper()}{hit.hit_id}] {hit.content}"
            t = estimate_tokens(bullet)
            if used + t > remaining:
                bullet = self._fit_text(bullet, max(16, remaining - used))
                if bullet.strip("- ."):
                    lines.append(bullet)
                break
            lines.append(bullet)
            used += t
            if used >= remaining:
                break
        rec = self.recent_turns(limit=recent) if recent else []
        if rec and estimate_tokens("\n".join(lines)) < budget * 0.86:
            lines.append("\nRecent visible turns:")
            for turn in rec:
                snippet = self._fit_text(turn["content"], 70)
                lines.append(f"- T{turn['id']} {turn['role']}: {snippet}")
                if estimate_tokens("\n".join(lines)) >= budget:
                    break
        return self._fit_text("\n".join(lines).rstrip() + "\n", budget)

    # ---------- exports / stats / verification ----------
    def stats(self) -> dict:
        raw_msg_bytes = sum(int(t.get("raw_bytes", 0)) for t in self.index.get("turns", []))
        block_raw = sum(int(b.get("raw_bytes", 0)) for b in self.index.get("raw_blocks", []))
        block_compressed = sum(int(b.get("compressed_bytes", 0)) for b in self.index.get("raw_blocks", []))
        attach_raw = sum(int(a.get("raw_bytes", 0)) for a in self.index.get("attachments", []))
        attach_compressed = sum(int(a.get("compressed_bytes", 0)) for a in self.index.get("attachments", []))
        entry_text_bytes = sum(len(e.get("content", "").encode("utf-8")) for e in self.index.get("entries", []))
        sketches = 0
        for collection in ("turns", "entries", "attachments"):
            sketches += sum(len(_sketch_bytes(r)) for r in self.index.get(collection, []))
        dictionary_text = "\n".join(e.get("content", "") for e in self.index.get("entries", []) if e.get("status") == "active")
        return {
            "path": str(self.path),
            "file_bytes": self.path.stat().st_size,
            "title": self.meta("title", ""),
            "format_version": self.format_version,
            "codec": self.meta("codec", ""),
            "storage": self.meta("storage", ""),
            "sessions": len(self.index.get("sessions", [])),
            "turns": len(self.index.get("turns", [])),
            "raw_blocks": len(self.index.get("raw_blocks", [])),
            "attachments": len(self.index.get("attachments", [])),
            "active_entries": sum(1 for e in self.index.get("entries", []) if e.get("status") == "active"),
            "all_entries": len(self.index.get("entries", [])),
            "raw_message_bytes": raw_msg_bytes,
            "block_json_raw_bytes": block_raw,
            "block_payload_compressed_bytes": block_compressed,
            "attachment_raw_bytes": attach_raw,
            "attachment_payload_compressed_bytes": attach_compressed,
            "entry_text_bytes": entry_text_bytes,
            "query_sketch_bytes": sketches,
            "estimated_raw_tokens": sum(int(t.get("estimated_tokens", 0)) for t in self.index.get("turns", [])),
            "estimated_dictionary_tokens": estimate_tokens(dictionary_text),
            "payload_ratio": block_compressed / raw_msg_bytes if raw_msg_bytes else 0.0,
            "file_to_raw_ratio": self.path.stat().st_size / raw_msg_bytes if raw_msg_bytes else 0.0,
            "index_records": len(self.index.get("turns", [])) + len(self.index.get("entries", [])) + len(self.index.get("attachments", [])),
        }

    def export_jsonl(self, output: str | os.PathLike[str]) -> None:
        with open(output, "w", encoding="utf-8") as fh:
            for row in sorted(self.index.get("turns", []), key=lambda r: int(r["id"])):
                turn = self.get_turn(int(row["id"]))
                item = {"role": turn["role"], "content": turn["content"], "session_id": turn["session_id"], "created_at": turn["created_at"]}
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    def export_markdown(self, output: str | os.PathLike[str]) -> None:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(f"# {self.meta('title', 'LQCC capsule')}\n\n")
            for row in sorted(self.index.get("turns", []), key=lambda r: int(r["id"])):
                turn = self.get_turn(int(row["id"]))
                fh.write(f"## {turn['role'].title()} · T{turn['id']}\n\n{turn['content']}\n\n")

    def verify(self) -> list[str]:
        problems: list[str] = []
        try:
            _ = self._read_index()
        except Exception as exc:
            problems.append(f"Index verification failed: {exc}")
        for block in self.index.get("raw_blocks", []):
            try:
                items = self._decode_block_items(block)
                raw = _json_dumps(items)
                if hashlib.sha256(raw).hexdigest() != block["sha256"]:
                    problems.append(f"Raw block hash mismatch B{block['id']}")
            except Exception as exc:
                problems.append(f"Raw block B{block.get('id')} failed: {exc}")
        for turn in self.index.get("turns", []):
            try:
                item = self.get_turn(int(turn["id"]))
                if text_fingerprint(item["content"]) != turn["sha256"]:
                    problems.append(f"Hash mismatch in turn {turn['id']}")
            except Exception as exc:
                problems.append(f"Turn T{turn.get('id')} failed: {exc}")
        for att in self.index.get("attachments", []):
            try:
                _, payload = self._read_section(att["section"], expected_kind="A")
                raw = decompress_bytes(payload, att["codec"])
                if hashlib.sha256(raw).hexdigest() != att["sha256"]:
                    problems.append(f"Attachment hash mismatch A{att['id']}")
            except Exception as exc:
                problems.append(f"Attachment A{att.get('id')} failed: {exc}")
        return problems

    def compact(self) -> None:
        """Rewrite the packed capsule without orphaned old tail indexes.

        The live format is appendable: every append writes a new tail index. That
        is good for safety but creates stale index blobs. compact() repacks the
        currently visible archive and attachments into a fresh file.
        """
        if self.read_only:
            raise CapsuleError("Capsule is read-only")
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        old_index = json.loads(json.dumps(self.index))
        turns_by_id = {int(t["id"]): self.get_turn(int(t["id"])) for t in old_index.get("turns", [])}
        attachment_payloads: dict[int, bytes] = {}
        for a in old_index.get("attachments", []):
            _, payload = self._read_section(a["section"], expected_kind="A")
            attachment_payloads[int(a["id"])] = payload

        new_index = json.loads(json.dumps(old_index))
        new_index["raw_blocks"] = []
        for t in new_index.get("turns", []):
            t["block_id"] = None
        new_index["attachments"] = []
        new_index["counters"]["block"] = 0
        new_index["counters"]["attachment"] = 0
        with open(tmp, "wb") as fh:
            fh.write(MAGIC)
            self.index = new_index
            cap = self._block_cap()
            for sid in [s["id"] for s in old_index.get("sessions", [])]:
                turns = [turns_by_id[int(t["id"])] for t in old_index.get("turns", []) if t["session_id"] == sid]
                turns.sort(key=lambda t: int(t["seq"]))
                for i in range(0, len(turns), cap):
                    items = [
                        {"id": int(t["id"]), "seq": int(t["seq"]), "role": t["role"], "created_at": t["created_at"], "content": t["content"]}
                        for t in turns[i : i + cap]
                    ]
                    if items:
                        self._write_raw_block(fh, session_id=sid, items=items)
            # Re-append attachments with same IDs and metadata.
            for old_att in old_index.get("attachments", []):
                attachment_id = int(old_att["id"])
                payload = attachment_payloads[attachment_id]
                section = self._write_section(
                    fh,
                    kind="A",
                    ident=attachment_id,
                    meta={"attachment_id": attachment_id, "filename": old_att["filename"], "codec": old_att["codec"], "sha256": old_att["sha256"]},
                    payload=payload,
                )
                rec = dict(old_att)
                rec["section"] = section
                self.index["attachments"].append(rec)
                self.index["counters"]["attachment"] = max(int(self.index["counters"].get("attachment", 0)), attachment_id)
            self._append_index_blob(fh)
        os.replace(tmp, self.path)
        self.index = self._read_index()


_ROLE_ALIASES = {
    "human": "user",
    "user": "user",
    "assistant": "assistant",
    "ai": "assistant",
    "chatgpt": "assistant",
    "claude": "assistant",
    "system": "system",
    "tool": "tool",
}
_ROLE_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(user|human|assistant|ai|chatgpt|claude|system|tool)\s*[:：]?\s*$",
    re.IGNORECASE,
)
_ROLE_PREFIX_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(user|human|assistant|ai|chatgpt|claude|system|tool)\s*[:：]\s*(.*)$",
    re.IGNORECASE,
)


def _normalize_role(role: str) -> str:
    normalized = role.strip().lower()
    mapped = _ROLE_ALIASES.get(normalized)
    if mapped is None:
        raise CapsuleError(f"Unsupported role {role!r}; expected user/assistant/system/tool")
    return mapped


def _items_from_json_object(obj: Any, *, session_id: str) -> list[dict]:
    if isinstance(obj, dict) and isinstance(obj.get("messages"), list):
        obj = obj["messages"]
    if not isinstance(obj, list):
        raise CapsuleError("JSON import expects a list of messages or an object with messages=[...]")
    items: list[dict] = []
    for i, item in enumerate(obj, 1):
        if not isinstance(item, dict):
            raise CapsuleError(f"JSON message {i} is not an object")
        role = item.get("role") or item.get("author") or item.get("speaker")
        content = item.get("content") or item.get("text") or item.get("message")
        if isinstance(content, list):
            # Some exports represent content as a list of text parts.
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    value = part.get("text") or part.get("content") or ""
                    if value:
                        parts.append(str(value))
            content = "\n".join(parts)
        if not role or not content:
            raise CapsuleError(f"JSON message {i} requires role and content/text")
        items.append({
            "role": _normalize_role(str(role)),
            "content": str(content),
            "session_id": item.get("session_id", session_id),
            "created_at": item.get("created_at") or item.get("timestamp"),
            "extract": bool(item.get("extract", True)),
        })
    return items


def parse_chat_text(text: str, *, default_role: str = "user", session_id: str = "main") -> list[dict]:
    """Parse a loose Markdown/plain chat transcript into role/content items.

    This is intentionally conservative and local-only. It supports simple forms
    such as:

        User: ...
        Assistant: ...

    and Markdown headings such as:

        ## User
        ...
        ## Assistant
        ...

    If no role markers are found, the entire file is imported as one turn using
    default_role. Users can always use JSONL for exact control.
    """
    default_role = _normalize_role(default_role)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    turns: list[tuple[str, list[str]]] = []
    current_role: str | None = None
    current: list[str] = []
    found_marker = False

    def flush() -> None:
        nonlocal current_role, current
        if current_role is not None:
            content = "\n".join(current).strip()
            if content:
                turns.append((current_role, [content]))
        current_role = None
        current = []

    for line in lines:
        heading = _ROLE_HEADING_RE.match(line)
        prefix = _ROLE_PREFIX_RE.match(line)
        if heading:
            flush()
            current_role = _normalize_role(heading.group(1))
            found_marker = True
            continue
        if prefix:
            flush()
            current_role = _normalize_role(prefix.group(1))
            rest = prefix.group(2)
            current = [rest] if rest else []
            found_marker = True
            continue
        if current_role is None:
            current_role = default_role
        current.append(line)
    flush()

    if not found_marker:
        content = text.strip()
        return [{"role": default_role, "content": content, "session_id": session_id}] if content else []

    return [
        {"role": role, "content": parts[0], "session_id": session_id}
        for role, parts in turns
        if parts and parts[0].strip()
    ]


def import_items(capsule: Capsule, items: Sequence[dict], session_id: str = "main") -> tuple[int, int]:
    normalized_items: list[dict] = []
    for item in items:
        role = _normalize_role(str(item.get("role", "")))
        content = item.get("content") or item.get("text")
        if not content:
            raise CapsuleError("Each imported item requires content/text")
        normalized_items.append({
            "role": role,
            "content": str(content),
            "session_id": item.get("session_id", session_id),
            "created_at": item.get("created_at"),
            "extract": bool(item.get("extract", True)),
        })
    results = capsule.append_many(normalized_items, session_id=session_id)
    return len(results), sum(atom_count for _, atom_count in results)


def import_jsonl(capsule: Capsule, source: str | os.PathLike[str], session_id: str = "main") -> tuple[int, int]:
    items: list[dict] = []
    with open(source, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CapsuleError(f"Invalid JSONL at line {line_no}: {exc}") from exc
            role = item.get("role")
            content = item.get("content") or item.get("text")
            if not role or not content:
                raise CapsuleError(f"Line {line_no} requires role and content/text")
            items.append({
                "role": _normalize_role(str(role)),
                "content": content,
                "session_id": item.get("session_id", session_id),
                "created_at": item.get("created_at"),
                "extract": bool(item.get("extract", True)),
            })
    return import_items(capsule, items, session_id=session_id)


def import_chat_file(
    capsule: Capsule,
    source: str | os.PathLike[str],
    *,
    session_id: str = "main",
    input_format: str = "auto",
    default_role: str = "user",
) -> tuple[int, int]:
    path = Path(source)
    text = path.read_text(encoding="utf-8")
    fmt = input_format.lower()
    if fmt not in {"auto", "jsonl", "json", "markdown", "md", "text", "txt"}:
        raise CapsuleError("format must be auto, jsonl, json, markdown, or text")

    if fmt in {"jsonl"}:
        return import_jsonl(capsule, source, session_id=session_id)
    if fmt in {"json"}:
        return import_items(capsule, _items_from_json_object(json.loads(text), session_id=session_id), session_id=session_id)
    if fmt in {"markdown", "md", "text", "txt"}:
        return import_items(capsule, parse_chat_text(text, default_role=default_role, session_id=session_id), session_id=session_id)

    # auto: JSON object/list -> JSONL -> loose transcript.
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            return import_items(capsule, _items_from_json_object(json.loads(text), session_id=session_id), session_id=session_id)
        except Exception:
            pass
    try:
        parsed = []
        for line in text.splitlines():
            if line.strip():
                parsed.append(json.loads(line))
        if parsed:
            return import_items(capsule, parsed, session_id=session_id)
    except Exception:
        pass
    return import_items(capsule, parse_chat_text(text, default_role=default_role, session_id=session_id), session_id=session_id)
