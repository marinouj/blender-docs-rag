# blender-docs-rag

A hand-built RAG pipeline over the Blender 5.2 Python API reference. No
framework and no vector database, so every stage is readable.

```
docs HTML ──chunk──> chunks.jsonl ──index──> SQLite FTS5 (BM25) + embeddings.npy
                                                        │
question ──retrieve (bm25 | dense | hybrid)─────────────┘──> top-k chunks ──> Claude ──> cited answer
```

| Stage | File | What it does |
|---|---|---|
| Chunk | `blender_rag/chunk.py` | One chunk per API entry (operator, method, attribute, class) plus prose sections |
| Index | `blender_rag/index.py` | BM25 keyword index in SQLite, `bge-small-en-v1.5` embeddings in a NumPy matrix |
| Retrieve | `blender_rag/retrieve.py` | BM25, dense, and hybrid (reciprocal rank fusion) |
| Answer | `blender_rag/answer.py` | Sends the top chunks to Claude and asks for a cited answer |
| Eval | `blender_rag/evaluate.py` | Scores each retrieval mode on `eval/queries.jsonl` |

## Usage

```sh
uv sync
uv run python -m blender_rag chunk     # download docs (100 MB) and chunk them, ~2 min
uv run python -m blender_rag index     # embed ~25k chunks on CPU, ~7 min
uv run python -m blender_rag search "bevel edges of a mesh" --mode hybrid
uv run python -m blender_rag eval
cp .env.example .env                   # add ANTHROPIC_API_KEY, needed for `ask` only
uv run python -m blender_rag ask "How do I bevel selected edges with 3 segments?"
```

### Comparing chunking methods

Every command takes `--chunks`, and each method gets its own folder under
`data/`. The default is `structured`. `fixed` and `recursive` default to
1,000 characters with 150 overlap; set both with `fixed-800-100`.

```sh
uv run python -m blender_rag chunk --chunks fixed
uv run python -m blender_rag index --chunks fixed
uv run python -m blender_rag eval --chunks structured fixed recursive
uv run python -m blender_rag search "bevel edges of a mesh" --chunks recursive
```

## Baseline retrieval scores

25 queries, rank of the first correct chunk:

| mode | hit@1 | hit@5 | hit@10 | MRR |
|---|---|---|---|---|
| bm25 | 0.28 | 0.72 | 0.84 | 0.47 |
| dense | 0.52 | 0.72 | 0.88 | 0.61 |
| hybrid | 0.44 | 0.80 | 0.92 | 0.61 |

## Known limits

- The embedding model reads the first 512 tokens of a chunk. 196 chunks are
  longer than that; BM25 still indexes them in full.
- Attribute chunks do not carry their class description, so a query like
  "mirror modifier axis settings" has little to match on.
- Queries that need two hops ("add a subdivision surface modifier" →
  `ObjectModifiers.new(type='SUBSURF')`) rank poorly.

## Docs

- [docs/chunking.md](docs/chunking.md): how the docs are chunked, why, and the alternatives
- [docs/indexing.md](docs/indexing.md): indexing choices and known issues
- [docs/search.md](docs/search.md): how a query is ranked, with a worked example
- [docs/ask.md](docs/ask.md): how an answer is generated from the retrieved chunks, and its limits
- [docs/eval.md](docs/eval.md): what the retrieval eval measures, how to read it, and its limits
