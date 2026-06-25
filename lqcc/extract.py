from __future__ import annotations

import re
from dataclasses import dataclass

from .text import lexical_terms, normalize_text, split_sentences, strong_anchors


@dataclass(frozen=True)
class Atom:
    kind: str
    content: str
    confidence: float


_USER_PATTERNS: list[tuple[str, tuple[str, ...], float]] = [
    (
        "DECISION",
        (
            "定了", "决定", "确定", "最终", "就叫", "我要叫", "项目叫", "名字是", "名称是",
            "命名为", "叫做", "we decided", "the decision is", "we will call", "will be called",
        ),
        0.96,
    ),
    (
        "REQUIREMENT",
        (
            "必须", "最主要", "核心是", "核心不是", "原则", "要让", "我们要", "我要让", "肯定是要",
            "需要做到", "要求", "目标是", "本质是", "关键是", "must", "need to", "we need",
            "requirement", "the core is", "should support", "has to",
        ),
        0.93,
    ),
    (
        "WARNING",
        (
            "不要", "别把", "别再", "避免", "不应该", "不得", "不需要", "不能把", "do not", "don't",
            "avoid", "must not", "should not", "not a generic",
        ),
        0.92,
    ),
    (
        "TASK",
        (
            "下一步", "接下来", "开始准备", "开始做", "现在做", "继续开发", "继续实现", "继续吧",
            "开始创造", "todo", "next step", "start building", "implement", "current task",
        ),
        0.89,
    ),
    (
        "PREFERENCE",
        (
            "我想", "我希望", "我觉得", "我不要", "我更想", "我在想", "偏好", "i want", "i prefer",
            "i don't want", "i do not want", "i would like",
        ),
        0.86,
    ),
]

_ASSISTANT_PATTERNS: list[tuple[str, tuple[str, ...], float]] = [
    ("DECISION", ("定了:", "定了：", "最终决定", "项目叫", "我们决定", "the decision is"), 0.86),
    (
        "REQUIREMENT",
        (
            "真正要做的", "核心不是", "核心是", "准确定位", "必须", "产品原则", "目标是",
            "the core is", "must", "the goal is",
        ),
        0.82,
    ),
    ("WARNING", ("不要把", "不能把", "不应该", "do not", "must not"), 0.80),
    ("TASK", ("下一步", "接下来应该", "第一版先", "现在需要", "next step"), 0.78),
    ("TRACE", ("建议", "可以考虑", "可以先", "更合理", "一种方式", "we propose", "we can"), 0.70),
]

_KIND_PRIORITY = {
    "DECISION": 8,
    "REQUIREMENT": 7,
    "WARNING": 6,
    "TASK": 5,
    "PREFERENCE": 4,
    "FACT": 3,
    "TRACE": 2,
    "ARTIFACT": 1,
}


def _looks_like_question(sentence: str) -> bool:
    stripped = sentence.strip()
    lower = stripped.lower()
    if stripped.endswith(("?", "？")):
        return True
    if any(token in lower for token in ("为什么", "怎么", "谁", "有没有", "会不会", "能不能", "是不是")):
        return True
    if re.search(r"(?:吗|呢|么)[,，。.!！]?$", stripped):
        return True
    return False


def _explicit_cannot(lower: str) -> bool:
    return bool(re.search(r"(?<!能)不能", lower))


def _classify_user(sentence: str) -> tuple[str | None, float]:
    lower = sentence.lower()
    if "不是" in lower and ("而是" in lower or "是我们要" in lower or "实际上" in lower):
        return "DECISION", 0.98
    for kind, cues, confidence in _USER_PATTERNS:
        if any(cue in lower for cue in cues):
            return kind, confidence
    if _explicit_cannot(lower):
        return "WARNING", 0.92
    return None, 0.0


def _classify_assistant(sentence: str) -> tuple[str | None, float]:
    lower = sentence.lower()
    for kind, cues, confidence in _ASSISTANT_PATTERNS:
        if any(cue in lower for cue in cues):
            return kind, confidence
    return None, 0.0


def _fact_candidate(sentence: str, role: str) -> tuple[str | None, float]:
    if _looks_like_question(sentence):
        return None, 0.0
    stripped = sentence.lstrip()
    if stripped.startswith(("[Image", "[Images", "[PDF")):
        return None, 0.0
    lower = sentence.lower()
    anchors = strong_anchors(sentence)
    has_number = bool(re.search(r"\b\d{2,}\b|\d+\s*[–-]\s*\d+", sentence))
    definitional = any(
        cue in lower
        for cue in (
            "是一个", "是指", "指的是", "意味着", "包括", "名为", "题目", "文章", "论文", "引用",
            "任教", "主席", "研究方向", "认证", "定位", "called", "means", "is a", "refers to",
            "introduces", "proposes", "consists of",
        )
    )
    quantitative = has_number and any(
        cue in lower for cue in ("分钟", "小时", "天", "年", "届", "页", "词", "学生", "排名", "citation", "cited")
    )
    terms = lexical_terms(sentence, max_terms=24)
    if len(terms) < 3:
        return None, 0.0
    if role == "user":
        if (anchors or has_number) and len(sentence) >= 18:
            return "FACT", 0.70
    else:
        if ((anchors and definitional) or quantitative) and 20 <= len(sentence) <= 420:
            return "FACT", 0.67
    return None, 0.0


def extract_atoms(text: str, role: str) -> list[Atom]:
    """Extract a small, high-precision context dictionary without LLM calls.

    Raw turns remain lossless, so this layer intentionally sacrifices recall to
    avoid flooding the active dictionary with every sentence in an answer.
    """
    candidates: list[Atom] = []
    for sentence in split_sentences(text):
        sentence = normalize_text(sentence)
        if not 8 <= len(sentence) <= 700:
            continue
        if role == "user":
            kind, confidence = _classify_user(sentence)
        else:
            kind, confidence = _classify_assistant(sentence)
        if kind is None:
            kind, confidence = _fact_candidate(sentence, role)
        if kind is None:
            continue
        if role == "user":
            confidence = min(0.99, confidence + 0.03)
        elif role == "assistant":
            confidence = max(0.1, confidence - 0.08)
        candidates.append(Atom(kind=kind, content=sentence, confidence=confidence))

    # Keep the dictionary sparse. Full evidence is always available from turns.
    limit = 8 if role == "user" else 2
    candidates.sort(
        key=lambda atom: (
            -_KIND_PRIORITY.get(atom.kind, 0),
            -atom.confidence,
            len(atom.content),
        )
    )
    output: list[Atom] = []
    seen: set[tuple[str, str]] = set()
    for atom in candidates:
        key = (atom.kind, atom.content.lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(atom)
        if len(output) >= limit:
            break
    return output
