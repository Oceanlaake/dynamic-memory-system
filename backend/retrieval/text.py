"""检索文本构造与分词。

这是 Retrieval 与 Memory Schema 之间唯一的耦合点：schema 里新增或改名语义字段时，
只需要改这个文件。
"""

from __future__ import annotations

import re

from backend.schemas import Memory

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# 极小的停用词表，避免 how/long/did/take 这类词主导短文本打分
_STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those
    is are was were be been being am
    do does did doing done
    have has had having
    how what when where which who whom why
    for from with without about into over under again further once
    his her their its our your my me him them us you i he she it we they
    of on in at to by as so such not no nor only own same too very can will just
    """.split()
)


def build_index_text(memory: Memory) -> str:
    """把一条 Memory 拼成用于检索的文本。

    不含 evidence：原文引用只用于追溯，不参与相似度，否则会放大同一 turn 的权重。
    """
    parts = [memory.subject, memory.type]
    if memory.attribute:
        parts.append(memory.attribute.replace("_", " ").replace(".", " "))
    if memory.value:
        parts.append(memory.value.replace("_", " "))
    parts.append(memory.content)
    return " ".join(part for part in parts if part)


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]
