# How search works

What `blender_rag/retrieve.py` does with a query. For how the indexes it
searches are built, see [indexing.md](indexing.md).

A query goes through two independent rankers, one matching words and one
matching meaning. Their two ranked lists are merged into one.

```
                 ┌─> keyword ranker (BM25) ──> top 50 ─┐
query ───────────┤                                     ├─> fusion ──> top k chunks
                 └─> embedding ranker ───────> top 50 ─┘
```

The examples below trace the real query `bevel edges of a mesh`.

## 1. Keyword ranker (BM25)

`Retriever.bm25`

1. Lowercase the query, split it into runs of letters and digits, and drop
   stopwords. `bevel edges of a mesh` becomes `bevel`, `edges`, `mesh`.
2. Ask SQLite FTS5 for every chunk containing any of those words (the terms are
   joined with OR).
3. Score each match with BM25, which rewards three things:
   - **Rare words count more.** `bevel` is in few chunks, `mesh` in thousands.
   - **Repeats count, with diminishing returns.** The tenth occurrence adds
     much less than the first.
   - **Short chunks beat long ones** for the same number of matches.
4. Weigh a match in the `symbol` column 5 times a match in `text`.

For the example, `SolidifyModifier.bevel_convex` ranks first and
`bpy.ops.mesh.bevel` fifth. The operator's chunk is long, which BM25 penalises.

## 2. Embedding ranker (dense)

`Retriever.dense`

1. Turn the query into a 384-number vector with the same model that embedded
   the chunks.
2. Multiply it against the matrix of all 24,697 chunk vectors in one operation.
   Because every vector has length 1, each result is a cosine similarity:
   vectors pointing in a similar direction mean similar meaning.
3. Keep the 50 highest.

For the example, `bpy.ops.mesh.bevel` ranks first. Matching on meaning is not
affected by the chunk's length.

## 3. Fusion (reciprocal rank fusion)

`Retriever.hybrid`

BM25 scores and cosine similarities are on unrelated scales, so the merge
ignores scores and uses only positions. A chunk gets `1 / (60 + rank)` from
each list it appears in, and the contributions are added.

| Chunk | Keyword rank | Embedding rank | Fused score | Hybrid rank |
|---|---|---|---|---|
| `bpy.ops.mesh.bevel` | 5 | 1 | 0.0318 | 1 |
| `bpy.types.Mesh.edges` | 4 | 2 | 0.0318 | 2 |
| `bpy.types.SolidifyModifier.bevel_convex` | 1 | 6 | 0.0315 | 3 |
| `bpy.types.BevelModifier.limit_method` | 3 | 10 | 0.0302 | 4 |
| `bpy_extras.mesh_utils.edge_loops_from_edges` | 10 | 5 | 0.0297 | 5 |

Two things to notice:

- **Agreement wins.** A chunk ranked reasonably by both rankers beats one ranked
  first by only one of them.
- **The scores are close together.** The constant 60 flattens the curve, so
  being 1st rather than 5th matters little. The top three here are separated by
  0.0003, which is why hybrid ordering near the top is fragile.

## 4. Returning results

`Retriever.search`

The top `k` chunk ids (8 by default) are looked up in SQLite for their text,
symbol and URL, and returned in ranked order. `search` prints them; `ask`
passes them to Claude as numbered excerpts.

## Where it goes wrong

The merge is only as good as its two inputs. When one ranker is badly wrong, it
pulls a correct answer from the other one down. On the eval, hybrid puts the
right chunk first for 44% of queries against 52% for embeddings alone, while
getting it into the top 5 more often (80% against 72%).

## Seeing each stage

```sh
uv run python -m blender_rag search "bevel edges of a mesh" --mode bm25
uv run python -m blender_rag search "bevel edges of a mesh" --mode dense
uv run python -m blender_rag search "bevel edges of a mesh" --mode hybrid
```
