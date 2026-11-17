"""Build the glossary + dictionary search index for the active dataset.

    uv run python scripts/build_search_index.py                 # fake embeddings, free
    EMBEDDING_PROVIDER=openai uv run python scripts/build_search_index.py         # shows cost, asks
    EMBEDDING_PROVIDER=openai uv run python scripts/build_search_index.py --yes   # pre-approved

With a paid provider it ALWAYS prints the estimated cost first and refuses to call
the API unless you confirm (or pass --yes).
"""

import argparse

from agent.config import get_settings
from agent.embeddings import estimate_cost_usd, index_model_name
from agent.search_index import build_index, collect_documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args()

    settings = get_settings()
    docs = collect_documents()
    print(f"Dataset '{settings.dataset}': {len(docs)} documents, model '{index_model_name()}'")

    if settings.embedding_provider != "fake":
        estimate = estimate_cost_usd([d["body"] for d in docs])
        print(f"PAID API CALL: 1 request to {settings.embedding_provider}, "
              f"estimated cost ${estimate:.5f}")
        if not args.yes:
            try:
                answer = input("Continue? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() != "y":
                raise SystemExit("Cancelled. No API call was made.")

    summary = build_index()
    print(f"Indexed {summary['documents']} documents "
          f"({summary['tokens']} tokens, actual cost ${summary['cost_usd']:.5f})")


if __name__ == "__main__":
    main()
