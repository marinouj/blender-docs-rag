"""Stage 1: turn the Sphinx HTML docs into chunks.

The docs are already structured, so chunking follows that structure instead of
cutting every N characters:

- one chunk per API entry (operator, function, method, attribute, class), which
  keeps a signature together with its parameter docs
- one chunk per prose section (quickstart, gotchas, examples above a class)
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
    symbol: str  # qualified API name, or "" for prose
    title: str
    url: str
    text: str


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


def build():
    download()
    html_dir = next(config.RAW_HTML.iterdir())
    pages = sorted(p for p in html_dir.glob("*.html") if not SKIP_PAGES.match(p.name))
    kinds: dict[str, int] = {}
    n = 0
    with config.CHUNKS_JSONL.open("w") as out:
        for path in pages:
            soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
            article = soup.find("article", id="furo-main-content")
            if article is None:
                continue
            h1 = article.find("h1")
            page_title = clean_text(h1) if h1 else path.stem
            found = [*api_chunks(article, path.name), *prose_chunks(article, path.name, page_title)]
            for kind, symbol, title, url, text in found:
                chunk = Chunk(n, kind, symbol, title, config.DOCS_BASE_URL + url, text)
                out.write(json.dumps(asdict(chunk)) + "\n")
                kinds[kind] = kinds.get(kind, 0) + 1
                n += 1
    print(f"{n} chunks from {len(pages)} pages -> {config.CHUNKS_JSONL}")
    for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:12} {count}")
