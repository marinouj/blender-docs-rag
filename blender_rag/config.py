from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BLENDER_VERSION = "5.2"
DOCS_ZIP_URL = f"https://docs.blender.org/api/{BLENDER_VERSION}/blender_python_reference_{BLENDER_VERSION.replace('.', '_')}.zip"
DOCS_BASE_URL = f"https://docs.blender.org/api/{BLENDER_VERSION}/"

RAW_ZIP = DATA / "raw" / "reference.zip"
RAW_HTML = DATA / "raw" / "html"
CHUNKS_JSONL = DATA / "chunks.jsonl"
INDEX_DB = DATA / "index.sqlite"
EMBEDDINGS_NPY = DATA / "embeddings.npy"

# Small local model: 384 dims, 512-token input limit, runs on CPU via ONNX.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

ANSWER_MODEL = "claude-opus-5-5"
