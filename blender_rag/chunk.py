"""Stage 1: turn the Sphinx HTML docs into chunks.

The default `structured` method follows the structure of the docs:

- one chunk per API entry (operator, function, method, attribute, class), which
  keeps a signature together with its parameter docs
- one chunk per prose section (quickstart, gotchas, examples above a class)

Two generic methods are here for comparison. Both split the same text: the
structured units of a page joined in order, so only the boundaries differ.

- `fixed`: cut every `size` characters, each window overlapping the last
- `recursive`: split on blank lines, then lines, sentences, words, and pack the
  pieces into chunks of up to `size` characters
"""

import copy
import json
import re
import urllib.request
import zipfile
from dataclasses import asdict, dataclass

from bs4 import BeautifulSoup, Tag

from . import config

SKIP_PAGES = re.compile(r"^(genindex|search|py-modindex|index|change_log)")
BLOCK_TAGS = ["p", "li", "dt", "dd", "pre", "div", "section", "h1", "h2", "h3", "h4", "tr"]
MAX_PROSE_CHARS = 1500
MIN_PROSE_CHARS = 40
# Auto-generated link lists on every bpy.types page: all names, no explanation.
NOISE_SECTIONS = {"Inherited Properties", "Inherited Functions", "References"}
HIERARCHY = re.compile(r"^(base classes|subclasses) —")


@dataclass
class Chunk:
    id: int
    kind: str  # function | method | attribute | data | class | prose | ...
    symbol: str  # qualified API name, or "" for prose and generic chunks
    title: str
    url: str
    text: str
    # API entries whose name line is in the chunk. Used by the eval only, so the
    # generic methods are scored on the same terms without searching on it.
    symbols: list[str]


def download():
    if not config.RAW_HTML.exists():
        config.RAW_ZIP.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {config.DOCS_ZIP_URL}")
        urllib.request.urlretrieve(config.DOCS_ZIP_URL, config.RAW_ZIP)
        with zipfile.ZipFile(config.RAW_ZIP) as z:
            z.extractall(config.RAW_HTML)


def clean_text(node: Tag) -> str:
    """Flatten HTML to text, keeping line breaks only at block boundaries."""
    node = copy.copy(node)
    for a in node.select("a.headerlink"):
        a.decompose()
    for block in node.find_all(BLOCK_TAGS):
        block.insert_before("\n")
        block.insert_after("\n")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in node.get_text().split("\n"))
    return "\n".join(line for line in lines if line)


def hierarchy_lines(article: Tag) -> list[Tag]:
    return [p for p in article.find_all("p") if HIERARCHY.match(p.get_text())]


def api_chunks(article: Tag, page: str):
    hierarchy = "\n".join(clean_text(p) for p in hierarchy_lines(article))
    for dl in article.select("dl.py"):
        dts = dl.find_all("dt", recursive=False)
        dd = dl.find("dd", recursive=False)
        if not dts or not dts[0].get("id"):
            continue
        kind = dl["class"][1]
        symbol = dts[0]["id"]
        signature = "\n".join(clean_text(dt).replace("\n", " ") for dt in dts)

        body = ""
        if dd is not None:
            dd = copy.copy(dd)
            for nested in dd.select("dl.py"):  # members become their own chunks
                nested.decompose()
            body = clean_text(dd)
        if kind == "class" and hierarchy:
            body = f"{hierarchy}\n{body}"

        text = f"{kind} {symbol}\n{signature}"
        if body:
            text += f"\n\n{body}"
        yield kind, symbol, symbol, f"{page}#{symbol}", text


def split_long(text: str):
    if len(text) <= MAX_PROSE_CHARS:
        yield text
        return
    part = ""
    for line in text.split("\n"):
        if part and len(part) + len(line) > MAX_PROSE_CHARS:
            yield part
            part = ""
        part += line + "\n"
    if part.strip():
        yield part


def prose_chunks(article: Tag, page: str, page_title: str):
    article = copy.copy(article)
    for node in [*article.select("dl.py"), *hierarchy_lines(article)]:
        node.decompose()
    for section in article.find_all("section"):
        section = copy.copy(section)
        for child in section.find_all("section"):  # nested sections are handled on their own
            child.decompose()
        heading = section.find(re.compile(r"^h[1-6]$"))
        heading_text = clean_text(heading) if heading else ""
        title = page_title if heading_text in ("", page_title) else f"{page_title} > {heading_text}"
        text = clean_text(section)
        if heading_text in NOISE_SECTIONS or len(text) - len(heading_text) < MIN_PROSE_CHARS:
            continue
        anchor = f"#{section['id']}" if section.get("id") else ""
        for part in split_long(text):
            yield "prose", "", title, f"{page}{anchor}", f"{title}\n\n{part.strip()}"


# Separators for recursive splitting, coarsest first. Units on a page are joined
# with a blank line, so the first split falls between API entries.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
UNIT_SEP = "\n\n"


def fixed_spans(start: int, end: int, size: int, overlap: int) -> list[tuple[int, int]]:
    spans = []
    while True:
        spans.append((start, min(start + size, end)))
        if start + size >= end:
            return spans
        start += size - overlap


def merge_spans(pieces: list[tuple[int, int]], size: int, overlap: int) -> list[tuple[int, int]]:
    """Pack consecutive pieces into chunks of up to `size`, starting each chunk
    with the trailing pieces of the last one that fit in `overlap`."""
    chunks, current = [], []
    for piece in pieces:
        if current and piece[1] - current[0][0] > size:
            chunks.append((current[0][0], current[-1][1]))
            while current and (current[-1][1] - current[0][0] > overlap or piece[1] - current[0][0] > size):
                current.pop(0)
        current.append(piece)
    if current:
        chunks.append((current[0][0], current[-1][1]))
    return chunks


def recursive_spans(text: str, start: int, end: int, size: int, overlap: int, seps=SEPARATORS) -> list[tuple[int, int]]:
    if end - start <= size:
        return [(start, end)]
    sep = next(s for s in seps if s == "" or s in text[start:end])
    if sep == "":
        return fixed_spans(start, end, size, overlap)
    pieces, at = [], start
    while (found := text.find(sep, at, end)) != -1:
        pieces.append((at, found + len(sep)))
        at = found + len(sep)
    if at < end:
        pieces.append((at, end))

    # Small pieces are packed together; a piece too big on its own is split on
    # the next separator and never shares a chunk with its neighbours.
    finer = seps[seps.index(sep) + 1 :]
    chunks, small = [], []
    for piece in pieces:
        if piece[1] - piece[0] <= size:
            small.append(piece)
        else:
            chunks += merge_spans(small, size, overlap) + recursive_spans(text, *piece, size, overlap, finer)
            small = []
    return chunks + merge_spans(small, size, overlap)


def generic_chunks(units: list[tuple], page: str, page_title: str, method: str, size: int, overlap: int):
    text = UNIT_SEP.join(u[4] for u in units)
    name_lines, at = [], 0  # (symbol, start, end) of each API entry's first line
    for _, symbol, _, _, unit_text in units:
        if symbol:
            name_lines.append((symbol, at, at + len(unit_text.split("\n", 1)[0])))
        at += len(unit_text) + len(UNIT_SEP)

    if method == "fixed":
        spans = fixed_spans(0, len(text), size, overlap)
    else:
        spans = recursive_spans(text, 0, len(text), size, overlap)
    for start, end in spans:
        if part := text[start:end].strip():
            symbols = [sym for sym, s, e in name_lines if start <= s and e <= end]
            yield method, "", page_title, page, part, symbols


def build(name: str = config.DEFAULT_CHUNKS):
    method, size, overlap = config.parse_chunks(name)
    out_path = config.chunks_jsonl(name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    download()
    html_dir = next(config.RAW_HTML.iterdir())
    pages = sorted(p for p in html_dir.glob("*.html") if not SKIP_PAGES.match(p.name))
    kinds: dict[str, int] = {}
    n = 0
    with out_path.open("w") as out:
        for path in pages:
            soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
            article = soup.find("article", id="furo-main-content")
            if article is None:
                continue
            h1 = article.find("h1")
            page_title = clean_text(h1) if h1 else path.stem
            units = [*api_chunks(article, path.name), *prose_chunks(article, path.name, page_title)]
            if method == "structured":
                found = [(*u, [u[1]] if u[1] else []) for u in units]
            else:
                found = generic_chunks(units, path.name, page_title, method, size, overlap)
            for kind, symbol, title, url, text, symbols in found:
                chunk = Chunk(n, kind, symbol, title, config.DOCS_BASE_URL + url, text, symbols)
                out.write(json.dumps(asdict(chunk)) + "\n")
                kinds[kind] = kinds.get(kind, 0) + 1
                n += 1
    print(f"{n} chunks from {len(pages)} pages -> {out_path}")
    for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:12} {count}")
