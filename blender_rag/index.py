"""Stage 2: build the two indexes the retriever searches.

- keyword index: SQLite FTS5 (BM25), good at exact names like `bevel` or `ray_cast`
- vector index: one embedding per chunk in a NumPy matrix, good at paraphrases

At ~25k chunks a brute-force dot product over the matrix takes a few
milliseconds, so there is no vector database here.
"""

import json
import sqlite3

import numpy as np
from fastembed import TextEmbedding

from . import config


def load_chunks(name: str) -> list[dict]:
    with config.chunks_jsonl(name).open() as f:
        return [json.loads(line) for line in f]


def build_keyword_index(chunks: list[dict], path):
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE chunks (id INTEGER PRIMARY KEY, kind TEXT, symbol TEXT, title TEXT, url TEXT, text TEXT, symbols TEXT)"
    )
    db.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(symbol, text)")
    db.executemany(
        "INSERT INTO chunks VALUES (:id, :kind, :symbol, :title, :url, :text, :symbols)",
        [{**c, "symbols": json.dumps(c["symbols"])} for c in chunks],
    )
    db.executemany(
        "INSERT INTO chunks_fts (rowid, symbol, text) VALUES (:id, :symbol, :text)", chunks
    )
    db.commit()
    db.close()


def build_vector_index(chunks: list[dict], path):
    model = TextEmbedding(config.EMBED_MODEL)
    vectors = np.empty((len(chunks), 384), dtype=np.float32)
    texts = (c["text"] for c in chunks)
    for i, vector in enumerate(model.embed(texts, batch_size=64)):
        vectors[i] = vector
        if i % 2000 == 0:
            print(f"  embedded {i}/{len(chunks)}", flush=True)
    # Unit length, so a dot product is the cosine similarity.
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    np.save(path, vectors)


def build(name: str = config.DEFAULT_CHUNKS):
    chunks = load_chunks(name)
    print(f"keyword index over {len(chunks)} chunks")
    build_keyword_index(chunks, config.index_db(name))
    print(f"embedding with {config.EMBED_MODEL}")
    build_vector_index(chunks, config.embeddings_npy(name))
    print(f"done -> {config.index_db(name).parent}")
