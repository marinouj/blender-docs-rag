"""Stage 3: find the chunks most relevant to a query.

Three modes, so they can be compared: `bm25` (keywords), `dense` (embeddings)
and `hybrid`, which merges the two rankings with reciprocal rank fusion.
"""

import re
import sqlite3
from functools import cached_property

import numpy as np
from fastembed import TextEmbedding

from . import config

CANDIDATES = 50  # how many results each ranker contributes to the fusion
RRF_K = 60
STOPWORDS = set(
    "a an and are as at be by can do does for from how i in is it my of on or "
    "that the this to what when which with".split()
)


class Retriever:
    def __init__(self, chunks: str = config.DEFAULT_CHUNKS):
        if not config.index_db(chunks).exists():
            raise SystemExit(f"no index for {chunks!r}: run `chunk --chunks {chunks}` and `index --chunks {chunks}`")
        self.db = sqlite3.connect(config.index_db(chunks))
        self.db.row_factory = sqlite3.Row
        self.vectors = np.load(config.embeddings_npy(chunks))

    @cached_property
    def model(self):
        return TextEmbedding(config.EMBED_MODEL)

    def bm25(self, query: str, n: int = CANDIDATES) -> list[int]:
        # FTS5 splits `ray_cast` into `ray` + `cast`, so split the query the same way.
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in STOPWORDS]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        # A hit in the symbol name counts 5x a hit in the body text.
        rows = self.db.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY bm25(chunks_fts, 5.0, 1.0) LIMIT ?",
            (match, n),
        )
        return [r[0] for r in rows]

    def dense(self, query: str, n: int = CANDIDATES) -> list[int]:
        q = next(iter(self.model.query_embed(query)))
        scores = self.vectors @ (q / np.linalg.norm(q))
        top = np.argpartition(-scores, n)[:n]
        return top[np.argsort(-scores[top])].tolist()

    def hybrid(self, query: str, n: int = CANDIDATES) -> list[int]:
        # Reciprocal rank fusion: score = sum of 1 / (k + rank) over the rankers.
        # It uses ranks only, so BM25 and cosine scores never need a common scale.
        scores: dict[int, float] = {}
        for ranking in (self.bm25(query, n), self.dense(query, n)):
            for rank, chunk_id in enumerate(ranking):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        return sorted(scores, key=scores.get, reverse=True)[:n]

    def search(self, query: str, k: int = 8, mode: str = "hybrid") -> list[dict]:
        ids = getattr(self, mode)(query)[:k]
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = {r["id"]: dict(r) for r in self.db.execute(f"SELECT * FROM chunks WHERE id IN ({marks})", ids)}
        return [rows[i] for i in ids]
