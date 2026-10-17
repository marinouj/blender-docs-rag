"""Retrieval eval: for each query, at what rank does a correct chunk first appear?

Measures retrieval only, so it runs offline and costs nothing. An expected
entry is an API symbol, or a page name (`*.html`) for prose answers. A chunk
counts as a symbol when it contains that entry's name line, so chunks from the
generic chunkers, which have no symbol of their own, are scored the same way.
"""

import json

from . import config
from .retrieve import Retriever

QUERIES = config.ROOT / "eval" / "queries.jsonl"
DEPTH = 10
CONTEXT_K = 8  # chunks `ask` sends to Claude
MODES = ("bm25", "dense", "hybrid")


def is_hit(chunk: dict, expected: list[str]) -> bool:
    symbols = json.loads(chunk["symbols"])
    return any(e in symbols or (e.endswith(".html") and e in chunk["url"]) for e in expected)


def first_hit_rank(chunks: list[dict], expected: list[str]) -> int | None:
    return next((rank for rank, c in enumerate(chunks, 1) if is_hit(c, expected)), None)


def score(chunks_name: str, queries: list[dict]) -> dict[str, dict]:
    """Print the per-query table for one chunking method and return its summary per mode."""
    retriever = Retriever(chunks_name)
    ranks, context = {}, {}
    for mode in MODES:
        results = [retriever.search(q["query"], DEPTH, mode) for q in queries]
        ranks[mode] = [first_hit_rank(r, q["expected"]) for r, q in zip(results, queries)]
        context[mode] = sum(len(c["text"]) for r in results for c in r[:CONTEXT_K]) / len(queries)
    n_chunks = retriever.db.execute("SELECT count(*) FROM chunks").fetchone()[0]

    print(f"== {config.chunks_name(chunks_name)}  ({n_chunks} chunks)\n")
    print(f"{'bm25':>5} {'dense':>5} {'hybrid':>6}  query   (rank of first correct chunk, - = not in top {DEPTH})")
    for i, q in enumerate(queries):
        cells = [str(ranks[m][i] or "-") for m in MODES]
        print(f"{cells[0]:>5} {cells[1]:>5} {cells[2]:>6}  {q['query']}")

    summary = {}
    for mode, rs in ranks.items():
        n = len(rs)
        hit = lambda k: sum(r is not None and r <= k for r in rs) / n
        summary[mode] = {
            "hit@1": hit(1),
            "hit@5": hit(5),
            "hit@10": hit(10),
            "MRR": sum(1 / r for r in rs if r) / n,
            f"chars@{CONTEXT_K}": context[mode],
        }
    print_summary({config.chunks_name(chunks_name): summary})
    return summary


def print_summary(results: dict[str, dict]):
    print(f"\n{'chunks':20} {'mode':8} {'hit@1':>6} {'hit@5':>6} {'hit@10':>6} {'MRR':>6} {f'chars@{CONTEXT_K}':>8}")
    for name, summary in results.items():
        for mode, m in summary.items():
            print(
                f"{name:20} {mode:8} {m['hit@1']:6.2f} {m['hit@5']:6.2f} {m['hit@10']:6.2f} {m['MRR']:6.2f}"
                f" {m[f'chars@{CONTEXT_K}']:8.0f}"
            )
    print()


def run(chunks_names: list[str] = [config.DEFAULT_CHUNKS]):
    queries = [json.loads(line) for line in QUERIES.open()]
    results = {config.chunks_name(name): score(name, queries) for name in chunks_names}
    if len(results) > 1:
        print(f"== comparison   (chars@{CONTEXT_K}: mean characters in the top {CONTEXT_K} chunks, what `ask` sends)")
        print_summary(results)
