"""Lightweight local embedding and scoring.

The production target is pgvector plus a real embedding provider. This module
keeps the current app deterministic and testable without external services.
"""
from __future__ import annotations

import math
import re
from collections import Counter


ASCII_TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_./+@%>=:-]*", re.UNICODE)
CJK_RE = re.compile(r"[\u4e00-\u9fff]+", re.UNICODE)

SYNONYMS = {
    "眼镜": ["防护眼镜", "护目镜", "od", "ppe"],
    "护目镜": ["防护眼镜", "眼镜", "od", "ppe"],
    "绿光": ["532", "532nm", "532 nm"],
    "近红外": ["1064", "1064nm", "1064 nm", "808", "808nm"],
    "联锁": ["门控联锁", "interlock", "e-stop", "急停"],
    "急停": ["e-stop", "紧急停止", "联锁"],
    "上报": ["报告", "lso", "事故报告"],
    "照到眼睛": ["眼睛", "照射", "应急", "e-stop", "lso"],
    "调光": ["准直", "对准", "align", "alignment"],
    "不出光": ["无输出", "no output", "nolase"],
    "无输出": ["不出光", "no output", "nolase"],
    "功率偏低": ["低功率", "low power", "lowpow"],
    "光斑": ["beam", "beam spot"],
    "污染": ["灰尘", "指纹", "contamination"],
    "关机": ["shutdown", "冷却水", "钥匙"],
    "开机": ["startup", "检查", "checklist"],
    "采购": ["供应商", "价格", "库存"],
}


def _cjk_ngrams(token: str) -> list[str]:
    pieces: list[str] = []
    chars = list(token)
    pieces.extend(chars)
    pieces.extend("".join(chars[i : i + 2]) for i in range(len(chars) - 1))
    if len(chars) >= 3:
        pieces.extend("".join(chars[i : i + 3]) for i in range(len(chars) - 2))
    return pieces


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    text = text.replace("≥", ">=").replace("≤", "<=").replace("：", ":")
    tokens: list[str] = []
    tokens.extend(token for token in ASCII_TOKEN_RE.findall(text) if len(token) > 1)
    for cjk in CJK_RE.findall(text):
        tokens.extend(_cjk_ngrams(cjk))

    expanded = list(tokens)
    joined = " ".join(tokens) + " " + text
    for key, values in SYNONYMS.items():
        if key in joined:
            expanded.extend(v.lower() for v in values)
    return expanded


def embed_text(text: str) -> dict[str, float]:
    tokens = tokenize(text)
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return {token: count / total for token, count in counts.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left).intersection(right)
    dot = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
