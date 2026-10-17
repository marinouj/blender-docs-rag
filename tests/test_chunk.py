import random

import pytest

from blender_rag.chunk import fixed_spans, generic_chunks, recursive_spans


def sample_text(seed: int) -> str:
    rng = random.Random(seed)
    words = ["mesh", "bevel", "offset.", "width", "segments", "x" * 70]
    paragraphs = []
    for _ in range(rng.randint(1, 30)):
        lines = [" ".join(rng.choices(words, k=rng.randint(1, 40))) for _ in range(rng.randint(1, 8))]
        paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs)


def test_fixed_spans_cover_text_with_overlap():
    spans = fixed_spans(0, 2500, 1000, 150)
    assert spans == [(0, 1000), (850, 1850), (1700, 2500)]


def test_fixed_spans_short_text_is_one_chunk():
    assert fixed_spans(0, 300, 1000, 150) == [(0, 300)]


@pytest.mark.parametrize("seed", range(50))
def test_recursive_spans_respect_size_and_cover_text(seed):
    text = sample_text(seed)
    spans = recursive_spans(text, 0, len(text), 300, 50)
    assert all(end - start <= 300 for start, end in spans)
    covered = set()
    for start, end in spans:
        covered.update(range(start, end))
    assert covered == set(range(len(text)))


def test_recursive_spans_split_between_entries_first():
    entries = ["function a\n" + "a" * 100, "function b\n" + "b" * 100, "function c\n" + "c" * 100]
    text = "\n\n".join(entries)
    spans = recursive_spans(text, 0, len(text), 250, 0)
    assert [text[s:e].strip() for s, e in spans] == ["\n\n".join(entries[:2]), entries[2]]


def test_generic_chunks_credit_entries_whose_name_line_they_contain():
    units = [
        ("function", "bpy.ops.mesh.bevel", "", "", "function bpy.ops.mesh.bevel\n" + "b" * 60),
        ("function", "bpy.ops.mesh.fill", "", "", "function bpy.ops.mesh.fill\n" + "f" * 60),
    ]
    chunks = list(generic_chunks(units, "bpy.ops.mesh.html", "Mesh Operators", "fixed", 100, 20))
    assert [c[5] for c in chunks] == [["bpy.ops.mesh.bevel"], ["bpy.ops.mesh.fill"]]
