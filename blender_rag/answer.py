"""Stage 4: generate an answer grounded in the retrieved chunks."""

import os

import anthropic

from . import config
from .retrieve import Retriever

SYSTEM = f"""You answer questions about the Blender {config.BLENDER_VERSION} Python API (bpy).

Each question comes with numbered excerpts from the official API reference. Base \
the answer on those excerpts and cite them inline as [1], [2]. Use exact names, \
signatures and defaults from the excerpts, and pass arguments explicitly in code.

If the excerpts do not cover the question, say what is missing instead of \
filling the gap from memory: the API changes between Blender versions."""


def load_env():
    env = config.ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip())


def format_context(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{i}] {c['url']}\n{c['text']}" for i, c in enumerate(chunks, 1))


def ask(question: str, k: int = 8, mode: str = "hybrid") -> list[dict]:
    """Stream the answer to stdout and return the chunks it was given."""
    load_env()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("No ANTHROPIC_API_KEY. Copy .env.example to .env and add your key.")
    chunks = Retriever().search(question, k=k, mode=mode)
    client = anthropic.Anthropic()
    try:
        with client.beta.messages.stream(
            model=config.ANSWER_MODEL,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            # If a safety classifier declines the request, retry on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[
                {
                    "role": "user",
                    "content": f"<excerpts>\n{format_context(chunks)}\n</excerpts>\n\n{question}",
                }
            ],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            message = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise SystemExit("No valid ANTHROPIC_API_KEY. Put one in .env or export it.")
    except anthropic.RateLimitError:
        raise SystemExit("Rate limited by the Claude API. Try again shortly.")
    except anthropic.APIStatusError as e:
        raise SystemExit(f"Claude API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise SystemExit("Could not reach the Claude API.")
    print()
    if message.stop_reason == "refusal":
        print("(the model declined to answer)")
    elif message.stop_reason == "max_tokens":
        print("(answer cut off at the token limit)")
    return chunks
