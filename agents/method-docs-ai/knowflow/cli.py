import argparse
from dotenv import load_dotenv
load_dotenv()

from knowflow.indexer import build_index
from knowflow.agent import answer_question

def main():
    parser = argparse.ArgumentParser(prog="knowflow", description="Documentation Q&A agent using Gemini API")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="Index documents from KNOWLEDGE_DIR")
    ask_parser = sub.add_parser("ask", help="Ask a question against the local index")
    ask_parser.add_argument("question", nargs="+")
    args = parser.parse_args()

    if args.command == "index":
        count = build_index()
        print(f"Index built successfully: {count} passages.")
    elif args.command == "ask":
        result = answer_question(" ".join(args.question))
        print("\nANSWER\n======\n")
        print(result["answer"])
        if result["sources"]:
            print("\nSOURCES\n=======")
            for i, source in enumerate(result["sources"], start=1):
                print(f"\n[{i}] {source['file']} (passage {source['chunk_id']}, similarity {source['score']:.3f})")
                print(source["text"][:600])

if __name__ == "__main__":
    main()
