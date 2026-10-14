# How the eval works

What `blender_rag/evaluate.py` measures, how to read it, and its limits.

The eval answers one question: **when I ask something, does the right chunk
come back, and how high up?** It measures retrieval only. It does not call
Claude, so it is free, offline and gives the same result every run.

## The test set

`eval/queries.jsonl` has 25 lines. Each is a question and the answers that
count as correct:

```json
{"query": "bevel edges of a mesh", "expected": ["bpy.ops.mesh.bevel", "bmesh.ops.bevel"]}
```

- `expected` lists every acceptable answer. Several are allowed because Blender
  often has more than one right way (`bpy.ops` and `bmesh`).
- An entry ending in `.html` matches any chunk from that page. This is for
  questions answered by prose, such as the operator gotchas page.

The queries are a deliberate mix: plain-language tasks ("join several objects
into one"), exact names (`bpy.ops.object.origin_set`), and one conceptual
question.

## What it does

For each query and each mode (`bm25`, `dense`, `hybrid`):

1. Run the search and take the top 10 chunks.
2. Find the position of the first chunk that is in `expected`. That position is
   the query's **rank**; if none is in the top 10, the query is a miss.

## Reading the output

The first table has one row per query, showing the rank in each mode (`-` is a
miss):

```
 bm25 dense hybrid  query
    5     1      1  bevel edges of a mesh
    -    10      7  set the render engine to Cycles
    -     7      -  mirror modifier axis settings
```

The second table summarises:

| Metric | Meaning |
|---|---|
| hit@1 | Share of queries where the first result is correct |
| hit@5 | Share where a correct result is in the top 5 |
| hit@10 | Share where a correct result is in the top 10 |
| MRR | Mean reciprocal rank: the average of `1 / rank`, with a miss counting as 0. Rank 1 scores 1, rank 2 scores 0.5, rank 10 scores 0.1 |

Which one matters depends on the use. `ask` sends 8 chunks to Claude, so hit@5
and hit@10 say whether the answer was in the prompt at all. hit@1 and MRR
matter more for `search`, where a person reads from the top.

## Current results

| Mode | hit@1 | hit@5 | hit@10 | MRR |
|---|---|---|---|---|
| bm25 | 0.28 | 0.72 | 0.84 | 0.47 |
| dense | 0.52 | 0.72 | 0.88 | 0.61 |
| hybrid | 0.44 | 0.80 | 0.92 | 0.61 |

Hybrid misses two queries entirely: "mirror modifier axis settings" and "get
the mesh with all modifiers evaluated".

## Using it

The eval exists to make changes measurable:

1. Run `uv run python -m blender_rag eval` and note the numbers.
2. Change one thing (chunk text, a weight, the embedding model).
3. Re-run `chunk` and `index` if the change affects them, then `eval`.
4. Compare the per-query table as well as the summary. A change that fixes two
   queries and breaks two looks like no change in the summary.

## Limits

- **Small.** With 25 queries, one query is worth 0.04. Differences of one or
  two queries are noise.
- **Written by the builder.** The queries were written by the same author as
  the pipeline, after seeing the docs, so they likely use the docs' own
  vocabulary more than a real user would.
- **Expected lists may be incomplete.** If search returns a correct chunk that
  is not listed, it is scored as wrong. Check misses by hand before trusting
  them.
- **First hit only.** A query needing two chunks (the method and the enum
  value) scores as a success when either one is found.
- **No tuning split.** If constants are tuned against these 25 queries, the
  scores will overstate real quality. Keep some queries aside before tuning.
- **Retrieval only.** Nothing measures whether `ask` produces correct answers,
  cites the right excerpts, or admits when the excerpts do not cover a question.

## Extending it

- **More queries from real use.** Each time a search disappoints, add the
  question and the chunk that should have been found.
- **An answer eval.** Run `ask` over the queries and check each answer, for
  example that code in it uses only names present in the excerpts. This needs
  an API key and costs money per run.
