# How `ask` works

What `blender_rag/answer.py` does. This is the "generation" half of RAG:
[search](search.md) finds the chunks, `ask` has Claude write an answer from them.

**Status: written but not yet run against the live API.** No API key was
available when it was built. Everything up to the API call is tested.

## `ask` compared with `search`

`search` stops after retrieval and shows the raw chunks. `ask` does the same
retrieval, then has Claude write an answer from them. In RAG terms, `search` is
the "R" alone and `ask` is "R + G".

| | `search` | `ask` |
|---|---|---|
| Steps | Retrieve | Retrieve, then generate |
| Output | Top chunks: symbol, URL, first 300 characters | A written answer with `[1]`-style citations, then the source URLs |
| Uses Claude | No | Yes |
| Needs an API key | No | Yes |
| Cost | Free, offline | Paid per question |
| Tested | Yes | Not yet run live |

Use `search` to look something up yourself, and to debug: when `ask` gives a
bad answer, `search` with the same query shows whether retrieval found the
wrong chunks or the model misused the right ones. Use `ask` when the pieces
need combining, such as a code snippet built from a signature and its
parameter docs.

## Steps

1. **Load the key.** Read `.env` in the project root if it exists, then check
   for `ANTHROPIC_API_KEY`. Exit with a message if there is none.
2. **Retrieve.** Run the same search as the `search` command (hybrid, top 8 by
   default; `-k` and `--mode` change this).
3. **Build the prompt.** Two parts:
   - A fixed **system prompt** with the rules (below).
   - One **user message** holding the chunks as numbered excerpts, then the
     question:

     ```
     <excerpts>
     [1] https://docs.blender.org/api/5.2/bpy.ops.mesh.html#bpy.ops.mesh.bevel
     function bpy.ops.mesh.bevel
     bpy.ops.mesh.bevel(*, offset_type='OFFSET', ...)
     ...

     [2] https://docs.blender.org/api/5.2/...
     ...
     </excerpts>

     How do I bevel selected edges with 3 segments?
     ```
4. **Call Claude** (`claude-opus-5-5`) and print the answer as it streams in.
5. **Print the sources**: the numbered URLs, so `[1]` in the answer can be
   followed to the docs page.

## The system prompt

It tells the model to:

- **Answer from the excerpts and cite them** inline as `[1]`, `[2]`.
- **Use exact names, signatures and defaults** from the excerpts, and pass
  arguments explicitly in code.
- **Say what is missing** when the excerpts do not cover the question, instead
  of answering from memory, because the API changes between Blender versions.

The last rule is the point of RAG here. The model already knows a lot of `bpy`,
but from a mix of versions. The excerpts pin it to 5.2.

## Choices

| Choice | Why |
|---|---|
| Excerpts in the user message, numbered, with URLs | The number gives the model something short to cite; the URL makes the citation checkable |
| Full chunk text, never truncated | The embedding saw only the first 512 tokens of long chunks; the model sees all of it |
| 8 chunks | Enough to survive a wrong top result (the right chunk is in the top 10 for 92% of eval queries); small enough to stay cheap |
| Streaming | The answer appears as it is written rather than after a pause |
| `effort: medium` | Looking up and explaining an API call does not need deep reasoning |
| Server-side fallback (beta) | If a safety classifier declines the request, the API retries on another model |

## Known issues

- **Not run live.** In particular the `fallbacks="default"` parameter is a beta
  feature and unverified here. If the first run fails on it, delete the `betas`
  and `fallbacks` lines.
- **Citations are by instruction only.** Nothing checks that `[2]` really
  supports the sentence it is attached to, or that every claim has a citation.
- **Nothing forces grounding.** The model is told to rely on the excerpts but
  can still answer from memory, most likely when retrieval returns near misses.
- **No retrieval check.** If search returns irrelevant chunks, they are sent
  anyway. There is no minimum score and no "I found nothing" path.
- **Single shot.** One search, one answer. The model cannot search again with
  better terms or look up a second symbol. Questions needing two lookups ("add
  a subdivision surface modifier" needs `ObjectModifiers.new` and the modifier
  type) depend on both landing in the top 8 by luck.
- **No conversation.** Each `ask` is independent; there are no follow-ups.
- **No answer eval.** `eval` measures retrieval only. Answer quality is
  unmeasured.

The single-shot limit is the main thing an agent would fix: give the model
`search` as a tool and let it decide what to look up and when it has enough.
