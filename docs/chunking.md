# Chunking strategy

How `blender_rag/chunk.py` splits the Blender 5.2 Python API reference, why,
and what the alternatives were.

## What the chunker does

The source is the official Sphinx HTML reference (1,949 pages after skipping
the index, search and changelog pages). It produces 24,697 chunks:

| Kind | Count | Source |
|---|---|---|
| attribute | 9,195 | `<dl class="py attribute">` |
| method | 7,854 | `<dl class="py method">` |
| function | 2,907 | `<dl class="py function">` (includes every `bpy.ops` operator) |
| data | 2,160 | `<dl class="py data">` |
| class | 2,123 | `<dl class="py class">` |
| prose | 458 | `<section>` elements with no API entry |

Sizes: median 182 characters, 95th percentile 585, maximum 21,064. 102 chunks
are longer than 2,000 characters; these are operators with many parameters.

Each chunk records `kind`, `symbol` (the qualified name, e.g.
`bpy.ops.mesh.bevel`), `title`, `url` (a deep link to the entry) and `text`.

The rules:

1. **One chunk per API entry.** The text is the kind and qualified name, the
   signature, then the description with its parameter and return docs.
2. **Class chunks hold only the class description** and its base-class line.
   Members are removed and become their own chunks.
3. **Prose is split by section heading**, with the heading path as the title
   (`Quickstart > Operators`). Sections longer than 1,500 characters are split
   on line boundaries; sections under 40 characters are dropped.
4. **Auto-generated lists are dropped.** Every `bpy.types` page ends with
   "Inherited Properties", "Inherited Functions" and "References" sections that
   are only lists of names. They added about 4,000 chunks of noise that matched
   keyword searches without explaining anything.

## Why chunk by API entry

- **A chunk should be the smallest unit that answers a question on its own.**
  An operator with its signature, defaults and parameter descriptions is that
  unit. Splitting it separates a signature from the meaning of its parameters.
- **The structure is already in the HTML.** Sphinx gives every entry a tag, a
  kind and a unique id, so boundaries, qualified names and citation links need
  no guesswork.
- **Each embedding stays about one thing.** An embedding is one vector for the
  whole chunk. One operator gives a sharp vector; fifteen unrelated attributes
  give a blurred average.
- **Small chunks keep the prompt small.** Eight retrieved chunks are usually
  under 2,000 characters in total.

## Alternatives considered

| Approach | How it works | Why it was not used |
|---|---|---|
| Fixed-size with overlap | Cut every N tokens, overlapping 10–20% | Default for unstructured text. Here it splits signatures from parameters and merges unrelated neighbours. |
| Recursive splitting | Split on paragraphs, then sentences, until under a limit | Still blind to which entry a paragraph belongs to. A simple form is used for long prose sections only. |
| One chunk per page | A whole module page as one chunk | `bpy.ops.mesh.html` has 167 operators: far past the embedding model's 512-token input, and costly to send to the model. |
| One chunk per class with members | `Object` and all 159 of its members together | Good context, but large and unfocused. |
| Semantic chunking | Embed sentences, cut where the topic shifts | For text with no structure. The HTML already marks topic boundaries more reliably. |
| Parent–child (small-to-big) | Search small chunks, give the model the larger parent | Not built yet. A candidate improvement, see below. |
| Contextual chunks | Prepend context to each chunk before embedding | Not built yet. A candidate improvement, see below. |

## Known weaknesses

- **Member chunks lose their surroundings.** `bpy.types.MirrorModifier.use_axis`
  contains only "Enable axis mirror", with nothing describing a mirror
  modifier. The eval query "mirror modifier axis settings" misses the top 10 in
  hybrid mode for this reason.
- **Long entries are only partly embedded.** The embedding model reads the first
  512 tokens. 196 chunks are longer; BM25 indexes them in full but the vector
  covers only their beginning. Details in [indexing.md](indexing.md).
- **Two-hop questions rank poorly.** "Add a subdivision surface modifier" needs
  `ObjectModifiers.new` plus the knowledge that the type is `'SUBSURF'`, which
  live in different chunks.

## Experiments to try

Run `uv run python -m blender_rag eval` before and after each change. Changing
chunk text requires re-running `chunk` and `index` (about 9 minutes).

1. **Contextual chunks:** prepend the class description to each attribute and
   method chunk.
2. **Parent–child:** when a member matches, also return its class chunk.
3. **Split long operators** into a signature chunk and per-parameter chunks, so
   the embedding covers all of them.
