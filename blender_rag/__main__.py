import argparse

MODES = ["hybrid", "bm25", "dense"]
CHUNKS_HELP = "chunking method: structured (default), fixed[-SIZE-OVERLAP] or recursive[-SIZE-OVERLAP]"


def main():
    parser = argparse.ArgumentParser(prog="blender_rag", description="RAG over the Blender Python API docs")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("chunk", "download the docs and split them into chunks"), ("index", "build the keyword and vector indexes")):
        sub.add_parser(name, help=text).add_argument("--chunks", default="structured", help=CHUNKS_HELP)
    for name, text in (("search", "show the retrieved chunks"), ("ask", "answer a question with Claude")):
        p = sub.add_parser(name, help=text)
        p.add_argument("query")
        p.add_argument("-k", type=int, default=8, help="number of chunks")
        p.add_argument("--mode", choices=MODES, default="hybrid")
        p.add_argument("--chunks", default="structured", help=CHUNKS_HELP)
    p = sub.add_parser("eval", help="score each retrieval mode on eval/queries.jsonl")
    p.add_argument("--chunks", nargs="+", default=["structured"], help=CHUNKS_HELP + "; several to compare")
    args = parser.parse_args()

    if args.command == "chunk":
        from . import chunk

        chunk.build(args.chunks)
    elif args.command == "index":
        from . import index

        index.build(args.chunks)
    elif args.command == "search":
        from .retrieve import Retriever

        for i, c in enumerate(Retriever(args.chunks).search(args.query, args.k, args.mode), 1):
            print(f"[{i}] {c['symbol'] or c['title']}  ({c['kind']})\n    {c['url']}")
            print("    " + c["text"][:300].replace("\n", "\n    ") + "\n")
    elif args.command == "ask":
        from .answer import ask

        chunks = ask(args.query, args.k, args.mode, args.chunks)
        print("\nSources:")
        for i, c in enumerate(chunks, 1):
            print(f"[{i}] {c['url']}")
    elif args.command == "eval":
        from . import evaluate

        evaluate.run(args.chunks)


if __name__ == "__main__":
    main()
