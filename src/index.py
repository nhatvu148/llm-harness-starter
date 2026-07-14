"""Index the example docs into the vector store. Run: ``task index``."""

import os

from retrieval import Retriever

DOCS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "examples", "docs")
)


def main():
    retriever = Retriever()
    n = retriever.index(DOCS_DIR)
    print(f"Indexed {n} chunks from {DOCS_DIR}")


if __name__ == "__main__":
    main()
