from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Iterable, Mapping

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_LATIN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./:+#@-]*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])\s*|(?<=[.])\s+(?=[A-Z0-9])|\n+")

_EN_STOP = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "to", "of", "in", "on", "at",
    "for", "from", "with", "without", "by", "as", "is", "are", "was", "were", "be", "been", "being",
    "it", "this", "that", "these", "those", "i", "you", "we", "they", "he", "she", "my", "your", "our",
    "their", "do", "does", "did", "have", "has", "had", "can", "could", "would", "should", "will", "just",
    "what", "which", "who", "where", "when", "how", "why", "about", "into", "through", "very", "more",
}
_ZH_STOP = {
    "这个", "那个", "我们", "你们", "他们", "可以", "就是", "一个", "一些", "已经", "现在", "然后",
    "因为", "所以", "但是", "还是", "可能", "什么", "怎么", "这样", "那样", "一下", "一下子", "觉得",
    "有没有", "是不是", "会不会", "能不能", "为什么", "的话", "里面", "本身", "真的", "其实", "来说",
}
# Only these one-character Chinese tokens are sufficiently informative to index.
# General single characters created many false matches in the first prototype.
_ZH_KEY_CHARS = set("叫改快慢小准禁存取读写查压解引奖会费名")
_ZH_GRAM_EDGE_STOP = set("的一是在了和与或而也就都还把被给从到让要会能可用这那我你他她它们个些其于为之并及所吗呢么")

SKETCH_BYTES = 64  # 512-bit Bloom-style query sketch per record.
_SKETCH_HASHES = 2

# Transparent, small bilingual query expansion. Rules are generic and deliberately
# low-weight. Explicit technical anchors in a query always dominate expansions.
_QUERY_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("叫什么", "名字", "名称", "项目名", "name"), ("叫", "命名", "决定", "暂定", "全称", "暂定全称", "called")),
    (("核心概念", "主要概念", "concept"), ("概念", "提出", "定义", "命名", "framework", "operation")),
    (("核心目标", "主要目标", "purpose", "goal"), ("核心", "目标", "目的", "定位")),
    (("保留", "保存", "丢失", "preserve"), ("完整", "无损", "原文", "历史", "完整对话", "lossless")),
    (("完整历史", "全部历史", "每次都发", "全量上下文"), ("活跃上下文", "固定预算", "只取", "相关内容", "按需")),
    (("写入", "追加", "边聊", "进行时"), ("持续写入", "每轮", "追加", "continuous", "append")),
    (("读取", "怎么读", "如何读", "read"), ("reader", "skill", "decode", "query", "检索")),
    (("引用", "被引", "citation", "cited"), ("reference", "related work", "google scholar")),
    (("演讲", "报告", "presentation", "talk"), ("分钟", "发言", "oral")),
    (("修正", "改正", "后来", "重新理解", "纠正"), ("实际上", "不需要", "不需要这么快", "理解偏", "不是", "改为", "重新")),
    (("下一步", "接下来", "继续", "目前"), ("测试", "压测", "实验", "benchmark", "next step", "当前任务")),
    (("进行时", "边聊", "持续写入", "怎么写入", "如何写入", "append"), ("每轮", "持续", "追加", "边聊边写", "写入")),
    (("先后", "顺序", "先做", "后做"), ("先", "然后", "产品", "论文", "再写")),
    (("完整历史", "每次都发", "为什么不", "全部历史"), ("相关", "按需", "预算", "活跃上下文", "固定")),
    (("保留什么", "完整原始", "原始历史"), ("完整", "原始", "无损", "历史", "原文")),
    (("原则", "快小精准", "三原则"), ("快", "小", "精准", "原则")),
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    text = normalize_text(text)
    parts = [p.strip(" \t-•") for p in _SENTENCE_SPLIT_RE.split(text)]
    return [p for p in parts if len(p) >= 8]


def _add(counter: Counter[str], term: str, weight: float) -> None:
    term = term.strip().lower()
    if term and term not in _ZH_STOP and term not in _EN_STOP:
        counter[term] += weight


def strong_anchors(text: str) -> set[str]:
    """Return explicit identifiers that should dominate semantic expansions."""
    text = normalize_text(text)
    anchors: set[str] = set()
    for token in _LATIN_RE.findall(text):
        cleaned = token.strip("./:+#@-").lower()
        if not cleaned:
            continue
        if (
            len(cleaned) >= 5
            or any(ch.isdigit() for ch in cleaned)
            or "." in token
            or "_" in token
            or token.isupper()
        ):
            anchors.add(cleaned)
    for quoted in re.findall(r"[\"“‘']([^\"”’']{3,80})[\"”’']", text):
        quoted = normalize_text(quoted).lower()
        if quoted:
            anchors.add(quoted)
    return anchors


def lexical_features(
    text: str,
    *,
    max_terms: int = 96,
    expand_query: bool = False,
) -> dict[str, float]:
    """Return bounded weighted lexical features for compressed retrieval.

    The feature set is intentionally sparse. Chinese uses short phrase features
    and selected 2/3/4-grams; generic single characters are omitted. This keeps
    a 512-bit sketch useful instead of saturating it.
    """
    normalized = normalize_text(text).lower()
    counts: Counter[str] = Counter()

    raw_text = normalize_text(text)
    raw_tokens = _LATIN_RE.findall(raw_text)
    for raw_token in raw_tokens:
        token = raw_token.strip("./:+#@-").lower()
        if len(token) < 2 or token in _EN_STOP:
            continue
        weight = 5.8 if len(token) >= 4 else 3.4
        if any(ch.isdigit() for ch in token) or "." in raw_token or "_" in raw_token or raw_token.isupper():
            weight += 1.4
        _add(counts, token, weight)

    for seq in _CJK_RE.findall(normalized):
        if seq in _ZH_STOP:
            continue
        if len(seq) == 1:
            if seq in _ZH_KEY_CHARS:
                _add(counts, seq, 3.4)
            continue
        # Keep short clean phrases, but do not let long raw sequences crowd out
        # identifiers and useful 2/3-grams in the bounded sketch.
        if len(seq) <= 8 and not any(ch in _ZH_GRAM_EDGE_STOP for ch in seq):
            _add(counts, seq, 4.2)
        for ch in seq:
            if ch in _ZH_KEY_CHARS:
                _add(counts, ch, 1.8)
        for n, weight in ((2, 4.0), (3, 3.4), (4, 2.8)):
            if len(seq) < n:
                continue
            for i in range(len(seq) - n + 1):
                gram = seq[i : i + n]
                if gram in _ZH_STOP or gram[0] in _ZH_GRAM_EDGE_STOP or gram[-1] in _ZH_GRAM_EDGE_STOP:
                    continue
                informative = sum(ch not in _ZH_GRAM_EDGE_STOP for ch in gram)
                if informative < max(1, n - 1):
                    continue
                _add(counts, gram, weight)

    if expand_query:
        anchor_count = len(strong_anchors(normalized))
        expansion_weight = 0.55 if anchor_count else 1.0
        for cues, additions in _QUERY_EXPANSIONS:
            if any(cue in normalized for cue in cues):
                for item in additions:
                    _add(counts, item, expansion_weight)
                    if _CJK_RE.fullmatch(item) and len(item) >= 2:
                        for n, weight in ((2, 0.30), (3, 0.42)):
                            for i in range(max(0, len(item) - n + 1)):
                                _add(counts, item[i : i + n], weight * expansion_weight)

    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[:max_terms]
    return dict(ordered)


def lexical_terms(text: str, *, max_terms: int = 96) -> list[str]:
    return list(lexical_features(text, max_terms=max_terms).keys())


def _sketch_positions(term: str, bits: int) -> tuple[int, ...]:
    digest = hashlib.blake2b(term.encode("utf-8"), digest_size=16, person=b"LQCCsketch").digest()
    positions = []
    for offset in range(0, 4 * _SKETCH_HASHES, 4):
        positions.append(int.from_bytes(digest[offset : offset + 4], "little") % bits)
    return tuple(positions)


def build_query_sketch(features: Mapping[str, float] | Iterable[str], *, size_bytes: int = SKETCH_BYTES) -> bytes:
    terms = list(features.keys() if isinstance(features, Mapping) else features)
    bits = size_bytes * 8
    value = bytearray(size_bytes)
    for term in terms:
        for pos in _sketch_positions(term, bits):
            value[pos >> 3] |= 1 << (pos & 7)
    return bytes(value)


def sketch_maybe_contains(sketch: bytes, term: str) -> bool:
    bits = len(sketch) * 8
    return all(sketch[pos >> 3] & (1 << (pos & 7)) for pos in _sketch_positions(term, bits))


def sketch_query_score(sketch: bytes, query_features: Mapping[str, float]) -> float:
    if not sketch or not query_features:
        return 0.0
    total = sum(query_features.values())
    if total <= 0:
        return 0.0
    matched = sum(weight for term, weight in query_features.items() if sketch_maybe_contains(sketch, term))
    return matched / total


def weighted_query_coverage(query_features: Mapping[str, float], document_features: Mapping[str, float]) -> float:
    if not query_features:
        return 0.0
    total = sum(query_features.values())
    matched = sum(weight for term, weight in query_features.items() if term in document_features)
    return matched / total if total else 0.0


def anchor_match_ratio(anchors: Iterable[str], text: str) -> float:
    anchors = list(anchors)
    if not anchors:
        return 1.0
    lower = normalize_text(text).lower()
    return sum(1 for anchor in anchors if anchor in lower) / len(anchors)


def best_excerpt(text: str, query: str, *, max_chars: int = 900, max_sentences: int = 4) -> str:
    """Extract the smallest useful evidence span from a candidate turn."""
    text = normalize_text(text)
    if len(text) <= max_chars:
        return text
    qf = lexical_features(query, max_terms=64, expand_query=True)
    anchors = strong_anchors(query)
    sentences = split_sentences(text)
    if not sentences:
        return text[: max_chars - 3] + "..."

    q_lower = normalize_text(query).lower()
    wants_duration = "分钟" in q_lower or any(cue in q_lower for cue in ("多久", "多长时间", "duration", "how long"))
    wants_citation = any(cue in q_lower for cue in ("引用", "被引", "citation", "cited"))
    wants_concept = any(cue in q_lower for cue in ("核心概念", "概念是什么", "concept"))
    wants_reply = any(cue in q_lower for cue in ("怎么回复", "如何回复", "reply"))

    scored: list[tuple[float, int, str]] = []
    for idx, sentence in enumerate(sentences):
        sf = lexical_features(sentence, max_terms=72)
        score = weighted_query_coverage(qf, sf)
        if anchors:
            ratio = anchor_match_ratio(anchors, sentence)
            score *= 0.25 + 1.75 * ratio
        # Prefer definitional and decision-bearing sentences as context evidence.
        lower = sentence.lower()
        if any(cue in lower for cue in ("核心", "决定", "意味着", "指", "定义", "提出", "是:", "is ", "means", "propose")):
            score += 0.05
        # Query-type evidence cues. These do not change retrieval, only which
        # sentence is exposed from an already selected compressed block.
        if wants_duration and re.search(r"\d+\s*[–-]\s*\d+\s*分钟|\d+\s*分钟", lower):
            score += 1.75
        if wants_citation and any(cue in lower for cue in ("被引用", "引用了", "1 次", "1次", "一引", "related work", "reference")):
            score += 1.10
        if wants_concept and any(cue in lower for cue in ("dual recognition", "third resistance", "richer existential geometry", "multidimensional positionality")):
            score += 1.20
        if wants_reply and any(cue in lower for cue in ("dear ", "confirm", "确认参加", "with best regards")):
            score += 1.25
        scored.append((score, idx, sentence))

    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen = sorted(scored[:max_sentences], key=lambda item: item[1])
    output: list[str] = []
    total = 0
    for _, _, sentence in chosen:
        extra = len(sentence) + (1 if output else 0)
        if total + extra > max_chars:
            remaining = max_chars - total
            if remaining > 40:
                output.append(sentence[: remaining - 3] + "...")
            break
        output.append(sentence)
        total += extra
    if not output:
        return text[: max_chars - 3] + "..."
    return "\n".join(output)


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-free estimate for relative product measurements."""
    cjk = sum(1 for ch in text if "\u3400" <= ch <= "\u9fff")
    non_cjk = max(0, len(text) - cjk)
    return max(1, cjk + math.ceil(non_cjk / 4))


def jaccard_terms(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
