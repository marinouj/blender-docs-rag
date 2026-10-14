"""Retrieval eval: for each query, at what rank does a correct chunk first appear?

Measures retrieval only, so it runs offline and costs nothing. An expected
entry is an API symbol, or a page name (`*.html`) for prose answers.
"""

import json

from . import config
from .retrieve import Retriever

QUERIES = config.ROOT / "eval" / "queries.jsonl"
DEPTH = 10


def is_hit(chunk: dict, expected: list[str]) -> bool:
    return chunk["symbol"] in expected or any(e.endswith(".html") and e in chunk["url"] for e in expected)


def first_hit_rank(chunks: list[dict], expected: list[str]) -> int | None:
    return next((rank for rank, c in enumerate(chunks, 1) if is_hit(c, expected)), None)


def run():
    queries = [json.loads(line) for line in QUERIES.open()]
    retriever = Retriever()
    ranks = {
        mode: [first_hit_rank(retriever.search(q["query"], DEPTH, mode), q["expected"]) for q in queries]
        for mode in ("bm25", "dense", "hybrid")
    }

    print(f"{'bm25':>5} {'dense':>5} {'hybrid':>6}  query   (rank of first correct chunk, - = not in top {DEPTH})")
    for i, q in enumerate(queries):
        cells = [str(ranks[m][i] or "-") for m in ranks]
        print(f"{cells[0]:>5} {cells[1]:>5} {cells[2]:>6}  {q['query']}")

    print(f"\n{'mode':8} {'hit@1':>6} {'hit@5':>6} {'hit@10':>6} {'MRR':>6}")
    for mode, rs in ranks.items():
        n = len(rs)
        hit = lambda k: sum(r is not None and r <= k for r in rs) / n
        mrr = sum(1 / r for r in rs if r) / n
        print(f"{mode:8} {hit(1):6.2f} {hit(5):6.2f} {hit(10):6.2f} {mrr:6.2f}")
