from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BLENDER_VERSION = "5.2"
DOCS_ZIP_URL = f"https://docs.blender.org/api/{BLENDER_VERSION}/blender_python_reference_{BLENDER_VERSION.replace('.', '_')}.zip"
DOCS_BASE_URL = f"https://docs.blender.org/api/{BLENDER_VERSION}/"

RAW_ZIP = DATA / "raw" / "reference.zip"
RAW_HTML = DATA / "raw" / "html"

# Each chunking method gets its own folder under data/, so indexes can be compared.
# A name is `structured`, or `fixed-<size>-<overlap>` / `recursive-<size>-<overlap>`
# in characters. `fixed` and `recursive` alone use the default size and overlap.
CHUNKERS = ("structured", "fixed", "recursive")
DEFAULT_CHUNKS = "structured"
DEFAULT_SIZE = 1000  # ~300 tokens, under the embedding model's 512-token input
DEFAULT_OVERLAP = 150


def parse_chunks(name: str) -> tuple[str, int, int]:
    """`fixed-800-100` -> ("fixed", 800, 100). Size and overlap are 0 for `structured`."""
    method, *numbers = name.split("-")
    if method not in CHUNKERS or (method == "structured" and numbers) or len(numbers) not in (0, 2):
        raise SystemExit(f"bad chunks name {name!r}: use structured, fixed[-SIZE-OVERLAP] or recursive[-SIZE-OVERLAP]")
    if method == "structured":
        return method, 0, 0
    size, overlap = map(int, numbers) if numbers else (DEFAULT_SIZE, DEFAULT_OVERLAP)
    if not 0 <= overlap < size:
        raise SystemExit(f"overlap must be smaller than size in {name!r}")
    return method, size, overlap


def chunks_name(name: str) -> str:
    method, size, overlap = parse_chunks(name)
    return method if method == "structured" else f"{method}-{size}-{overlap}"


def chunks_jsonl(name: str) -> Path:
    return DATA / chunks_name(name) / "chunks.jsonl"


def index_db(name: str) -> Path:
    return DATA / chunks_name(name) / "index.sqlite"


def embeddings_npy(name: str) -> Path:
    return DATA / chunks_name(name) / "embeddings.npy"


# Small local model: 384 dims, 512-token input limit, runs on CPU via ONNX.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

ANSWER_MODEL = "claude-opus-5-5"
