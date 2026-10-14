# Indexing choices

How `blender_rag/index.py` and `blender_rag/retrieve.py` index the chunks, why,
and the known issues. For how the chunks themselves are made, see
[chunking.md](chunking.md).

## Summary

| Decision | Choice | Main reason |
|---|---|---|
| Index type | Keyword (BM25) and vector, merged at query time | Queries are a mix of exact names and paraphrases |
| Embedding model | `BAAI/bge-small-en-v1.5`, local, 384 dimensions | Free, offline, adequate for short chunks |
| Vector storage | NumPy matrix, brute-force search | 24,697 chunks is too few to need an approximate index |
| Keyword storage | SQLite FTS5 | Built into Python, also holds chunk text and metadata |
| Fusion | Reciprocal rank fusion | Needs only ranks, so the two score scales never have to match |

## 1. Keyword, vector, or both

API docs get two kinds of query:

- **Exact names** (`ray_cast`, `bpy.ops.object.origin_set`). BM25 is best here;
  embeddings treat rare identifiers loosely.
- **Paraphrases** ("find where a ray hits a surface"). Embeddings are best here;
  the query words may not appear in the docs.

Both indexes are built and their rankings merged. On the 25 eval queries the
right chunk is in the top 5 for 80% with hybrid, against 72% for either alone.

## 2. Embedding model

| Option | For | Against |
|---|---|---|
| Small local model (chosen) | Free, no key, offline | Lower quality; 512-token input limit |
| Larger local model (`bge-large`, `nomic-embed-text`, `bge-m3`) | Better quality, some take ~8,000 tokens | Several times slower; indexing already takes about 7 minutes |
| Hosted API (Voyage, OpenAI) | Best quality, long inputs, code-tuned variants | Needs a key, costs money, sends the text out |

The median chunk is 55 tokens, so a small model with a short input limit fits
almost all of them.

## 3. Vector storage and search

| Scale | Sensible choice |
|---|---|
| Up to ~100k chunks | Plain matrix, brute-force dot product (chosen). Exact, a few milliseconds. |
| ~100k to a few million | Approximate index (HNSW, IVF) via FAISS, LanceDB, Chroma or `sqlite-vec`. Faster, can miss true matches. |
| Larger, multi-user, or often updated | A vector database server (Qdrant, pgvector) for filtering, updates and concurrency. |

The matrix is 36 MB (`data/embeddings.npy`). Row `i` is the vector for chunk
id `i`.

## 4. What goes into each index

- **Embedded text:** the full chunk text, which starts with the kind and
  qualified name, then the signature, then the description.
- **Keyword index:** two columns, `symbol` and `text`. A match in `symbol`
  weighs 5 times a match in `text`, so `bevel` ranks `bpy.ops.mesh.bevel` above
  an attribute that only mentions bevelling.
- **Tokenisation:** FTS5 splits on punctuation and underscores, so `ray_cast`
  is indexed as `ray` and `cast`. Queries are split the same way, stopwords are
  removed, and the remaining terms are joined with OR.
- **Normalisation:** vectors are scaled to unit length, so a dot product is the
  cosine similarity.
- **Query prefix:** `bge` models expect an instruction prefix on queries but not
  on documents; `query_embed` adds it.

## 5. Fusion

Each ranker returns its top 50. A chunk's hybrid score is the sum of
`1 / (60 + rank)` over the rankers that returned it. A chunk ranked well by
both beats one ranked first by only one.

## Known issues

### Long chunks are truncated in the vector index

The embedding model reads at most 512 tokens and silently drops the rest.
196 chunks (0.8%) are longer:

| Kind | Chunks over 512 tokens |
|---|---|
| Operators and functions | 109 |
| Prose sections | 72 |
| Methods | 10 |
| Classes, data, attributes | 5 |

- The median long chunk loses 21% of its tokens.
- The worst cases are import and export operators.
  `bpy.ops.export_scene.gltf` is 5,685 tokens, so its vector covers about 9%
  of it; `wm.usd_export` (3,204) and `export_scene.fbx` (2,686) are similar.
- `bpy.ops.mesh.bevel` is 978 tokens. Its vector stops inside the
  `clamp_overlap` parameter, so the parameters documented after it are not
  represented.

Effect: the name, signature and one-line description always come first, so
finding an operator by what it does is unaffected. Finding it by a parameter
documented late in the entry relies on BM25 alone, which needs a shared word
between query and docs. The keyword index and the text sent to Claude are
never truncated.

Fixes, in order of preference:

1. Split long entries into a signature chunk plus per-parameter chunks, each
   prefixed with the operator name.
2. Embed long chunks in windows and score a chunk by its best window.
3. Switch to a model with a longer input. Simple, but one vector for thousands
   of tokens is a blurred average.

### Hybrid finds the right chunk but often does not rank it first

| Mode | hit@1 | hit@5 | hit@10 | MRR |
|---|---|---|---|---|
| bm25 | 0.28 | 0.72 | 0.84 | 0.47 |
| dense | 0.52 | 0.72 | 0.88 | 0.61 |
| hybrid | 0.44 | 0.80 | 0.92 | 0.61 |

Hybrid has the best top-5 and top-10 rates but a lower top-1 rate than dense
alone. The usual fix is a reranker: a second model that re-scores the top 50
candidates against the query.

### BM25 uses OR over all query terms

A query for a full name such as `bpy.ops.object.origin_set` is split into five
terms, and `bpy`, `ops` and `object` match thousands of chunks. The exact
operator ranks second in BM25 rather than first. Matching the whole name against
the `symbol` column first would fix this.

### Untuned constants

The 5x symbol weight, the fusion constant of 60 and the 50 candidates per
ranker are defaults or guesses. None has been tuned against the eval.

### No metadata filters

`kind` and `symbol` are stored but not used to filter, so a search cannot be
limited to operators or to one module.

### The eval is small

25 queries, written by the same person who built the pipeline. Treat the
numbers as a rough yardstick; a difference of one query moves a score by 0.04.

### Rebuilding is all-or-nothing

Any change to chunk text means re-running `chunk` (about 2 minutes) and `index`
(about 7 minutes). There is no incremental update.
