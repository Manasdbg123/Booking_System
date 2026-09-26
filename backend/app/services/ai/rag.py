"""RAG over static platform-knowledge documents (cancellation/refund/booking
policies), kept deliberately separate from real-time transactional data.

Design decision: a TF-IDF retriever over a few dozen markdown chunks, not a
vector database. The corpus here is small (~3 static policy docs) and
changes only when someone edits a markdown file and restarts the process —
there is no user-generated or fast-changing content to index. A vector DB
(pgvector, a dedicated embedding index) earns its cost when the corpus is
large, growing, or needs semantic (not just lexical) matching; none of that
applies here, and pulling one in would be complexity added to look
impressive rather than to solve a real problem. If the knowledge base grows
into hundreds of documents, swap this module's `retrieve()` for an
embedding-based one without touching any caller — the RAG surface is a
single function.

Chunking: split each doc on markdown `##` headings, since each heading is
already a self-contained policy statement — exactly the granularity we want
to hand the model as a citation-able passage.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Chunk:
    doc: str
    heading: str
    text: str


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _load_chunks() -> list[Chunk]:
    knowledge_dir = Path(settings.ai_knowledge_dir)
    if not knowledge_dir.is_absolute():
        knowledge_dir = Path(__file__).resolve().parents[3] / settings.ai_knowledge_dir
    chunks: list[Chunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        sections = re.split(r"\n(?=## )", raw)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            heading_match = re.match(r"^#{1,2} (.+)", section)
            heading = heading_match.group(1) if heading_match else path.stem
            chunks.append(Chunk(doc=path.stem, heading=heading, text=section))
    return chunks


class _TfidfIndex:
    """Built once at import time; the corpus is static within a process."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._doc_tokens = [_tokenize(c.text) for c in chunks]
        self._doc_freq: Counter[str] = Counter()
        for tokens in self._doc_tokens:
            for term in set(tokens):
                self._doc_freq[term] += 1
        self._n_docs = max(len(chunks), 1)
        self._doc_vectors = [self._vectorize(tokens) for tokens in self._doc_tokens]

    def _idf(self, term: str) -> float:
        df = self._doc_freq.get(term, 0)
        return math.log((self._n_docs + 1) / (df + 1)) + 1.0

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        return {term: count * self._idf(term) for term, count in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        common = a.keys() & b.keys()
        if not common:
            return 0.0
        dot = sum(a[t] * b[t] for t in common)
        norm_a = math.sqrt(sum(v * v for v in a.values())) or 1.0
        norm_b = math.sqrt(sum(v * v for v in b.values())) or 1.0
        return dot / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 3) -> list[tuple[Chunk, float]]:
        query_vec = self._vectorize(_tokenize(query))
        scored = [(chunk, self._cosine(query_vec, vec)) for chunk, vec in zip(self.chunks, self._doc_vectors)]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [pair for pair in scored[:top_k] if pair[1] > 0]


_index: _TfidfIndex | None = None


def _get_index() -> _TfidfIndex:
    global _index
    if _index is None:
        _index = _TfidfIndex(_load_chunks())
    return _index


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    """Returns the top-k policy passages relevant to `query`, each with a
    similarity score, for the AI agent's search_policies tool. Never touches
    booking/inventory tables — this is knowledge retrieval only."""
    results = _get_index().search(query, top_k=top_k)
    return [
        {"doc": chunk.doc, "heading": chunk.heading, "text": chunk.text, "score": round(score, 4)}
        for chunk, score in results
    ]
