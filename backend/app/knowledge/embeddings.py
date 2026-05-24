"""Embedding providers and vector scoring.

The default local provider is deterministic and test-friendly. Production
deployments can switch to OpenAI embeddings without changing the retrieval API;
stored embeddings remain JSON so SQLite and Postgres both work.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from ..config import get_settings


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


def _local_sparse_embedding(text: str) -> dict[str, Any]:
    tokens = tokenize(text)
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return {
        "kind": "sparse",
        "provider": "local",
        "dimensions": len(counts),
        "values": {token: count / total for token, count in counts.items()},
    }


def _openai_dense_embedding(text: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed. Run pip install -r requirements.txt.") from exc

    client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    response = OpenAI(**client_kwargs).embeddings.create(model=settings.embedding_model, input=text[:24000])
    vector = response.data[0].embedding
    return {
        "kind": "dense",
        "provider": "openai",
        "model": settings.embedding_model,
        "dimensions": len(vector),
        "values": vector,
    }


def _sentence_transformer_dense_embedding(text: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "EMBEDDING_PROVIDER=sentence_transformers requires sentence-transformers. "
            "Install it in the backend environment and set EMBEDDING_MODEL, for example BAAI/bge-m3."
        ) from exc

    model = SentenceTransformer(settings.embedding_model)
    vector = model.encode(text, normalize_embeddings=True).tolist()
    return {
        "kind": "dense",
        "provider": "sentence_transformers",
        "model": settings.embedding_model,
        "dimensions": len(vector),
        "values": vector,
    }


def embed_text(text: str) -> dict[str, Any]:
    settings = get_settings()
    provider = settings.embedding_provider.lower()
    if provider == "openai":
        return _openai_dense_embedding(text)
    if provider in {"sentence_transformers", "sentence-transformers", "local_dense"}:
        return _sentence_transformer_dense_embedding(text)
    return _local_sparse_embedding(text)


def _legacy_values(embedding: dict[str, Any]) -> dict[str, float] | list[float]:
    if "values" in embedding:
        return embedding["values"]
    return embedding


def cosine_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    if not left or not right:
        return 0.0

    left_values = _legacy_values(left)
    right_values = _legacy_values(right)

    if isinstance(left_values, list) and isinstance(right_values, list):
        if len(left_values) != len(right_values):
            return 0.0
        dot = sum(float(a) * float(b) for a, b in zip(left_values, right_values))
        left_norm = math.sqrt(sum(float(value) * float(value) for value in left_values))
        right_norm = math.sqrt(sum(float(value) * float(value) for value in right_values))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    if not isinstance(left_values, dict) or not isinstance(right_values, dict):
        return 0.0

    shared = set(left_values).intersection(right_values)
    dot = sum(float(left_values[token]) * float(right_values[token]) for token in shared)
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left_values.values()))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right_values.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def lexical_similarity(query: str, text: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    text_tokens = set(tokenize(text))
    if not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    return overlap / math.sqrt(len(query_tokens) * len(text_tokens))
