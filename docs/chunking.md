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
| Fixed-size with overlap | Cut every N characters, overlapping 10–20% | Default for unstructured text. Here it splits signatures from parameters and merges unrelated neighbours. Built for comparison, see below. |
| Recursive splitting | Split on paragraphs, then sentences, until under a limit | Still blind to which entry a paragraph belongs to. A simple form is used for long prose sections. Built for comparison, see below. |
| One chunk per page | A whole module page as one chunk | `bpy.ops.mesh.html` has 167 operators: far past the embedding model's 512-token input, and costly to send to the model. |
| One chunk per class with members | `Object` and all 159 of its members together | Good context, but large and unfocused. |
| Semantic chunking | Embed sentences, cut where the topic shifts | For text with no structure. The HTML already marks topic boundaries more reliably. |
| Parent–child (small-to-big) | Search small chunks, give the model the larger parent | Not built yet. A candidate improvement, see below. |
| Contextual chunks | Prepend context to each chunk before embedding | Not built yet. A candidate improvement, see below. |

## Measured against generic chunkers

Fixed-size and recursive splitting are built in for comparison
(`--chunks fixed` / `--chunks recursive`, see the README). Both split the same
text the structured chunker keeps, the units of a page joined in order, so only
the boundaries differ. Results on the 25 eval queries, at 1,000 characters with
150 overlap and 500 with 75:

| Chunks | Count | Mode | hit@1 | hit@5 | hit@10 | MRR | chars in top 8 |
|---|---|---|---|---|---|---|---|
| structured | 24,697 | bm25 | 0.28 | 0.72 | 0.84 | 0.47 | 4,348 |
| | | dense | 0.52 | 0.72 | 0.88 | 0.61 | 6,025 |
| | | hybrid | 0.44 | 0.80 | 0.92 | 0.61 | 5,968 |
| fixed-1000-150 | 7,972 | bm25 | 0.28 | 0.72 | 0.80 | 0.45 | 7,946 |
| | | dense | 0.24 | 0.56 | 0.64 | 0.37 | 7,925 |
| | | hybrid | 0.32 | 0.76 | 0.80 | 0.49 | 7,956 |
| fixed-500-75 | 15,514 | bm25 | 0.24 | 0.68 | 0.76 | 0.39 | 3,988 |
| | | dense | 0.28 | 0.48 | 0.52 | 0.36 | 3,981 |
| | | hybrid | 0.32 | 0.52 | 0.72 | 0.42 | 3,981 |
| recursive-1000-150 | 8,636 | bm25 | 0.28 | 0.68 | 0.76 | 0.45 | 6,615 |
| | | dense | 0.44 | 0.56 | 0.76 | 0.51 | 6,107 |
| | | hybrid | 0.32 | 0.76 | 0.80 | 0.49 | 6,502 |
| recursive-500-75 | 16,826 | bm25 | 0.36 | 0.64 | 0.64 | 0.47 | 3,136 |
| | | dense | 0.40 | 0.52 | 0.60 | 0.45 | 2,858 |
| | | hybrid | 0.40 | 0.60 | 0.68 | 0.49 | 3,037 |

A generic chunk is scored as an API entry when it contains that entry's name
line. Without the name, the text cannot be turned into a call.

What the numbers show:

- **Structured is best on every metric and sends the least text.** Hybrid MRR
  is 0.61 against 0.49, and hit@10 is 23 queries against 20, with 25–35% fewer
  characters reaching Claude.
- **Dense retrieval suffers most.** Fixed-size dense drops from 0.61 to 0.37
  MRR. A window holding five unrelated entries, cut mid-word, gives a blurred
  vector. BM25 barely changes, since it counts words wherever they are.
- **Recursive finds the right text but loses its name.** For "convert a curve
  to a mesh" the top recursive chunk is the parameter list of
  `bpy.ops.object.convert`; the name and signature are in the chunk before it,
  because the entry is over 1,000 characters. Fixed-size does the same with
  "join several objects into one".
- **Neighbours help where a member chunk is too thin.** "mirror modifier axis
  settings" misses in structured hybrid but ranks 1 (fixed) and 3 (recursive),
  because the window also holds the modifier's class description. This is the
  case for the contextual chunks experiment below.
- **Smaller chunks do not close the gap.** At 500 characters hit@10 falls for
  both (hybrid 0.80 to 0.72 fixed, 0.68 recursive). The entries people ask
  about are the long ones: 22 of the 48 expected entries are over 500
  characters, against 6% of all entries, so more of them are cut away from
  their name line. Recursive at 500 does rank better at the top (hybrid hit@1
  0.40, near structured's 0.44), because a chunk is then often just one or two
  short entries, which is close to what the structured chunker does by design.

With 25 queries, one query is 0.04, so the gaps in hit@k are a few queries
each. The direction is the same in every mode, but this is not a large sample.

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
