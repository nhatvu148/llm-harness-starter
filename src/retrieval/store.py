"""Retrieval seam — the RAG layer ("specialize" with the right facts).

Default store: Chroma (persistent, local). Embeddings use Chroma's built-in
model (downloaded once on first index), so retrieval needs no API key. Swap
this class to use Qdrant, pgvector, etc. — only ``index`` and ``search`` are
called.
"""

import glob
import os
import pathlib
import re


def _chunk(text: str, size: int = 800) -> list[str]:
    """Group paragraphs into ~``size``-char chunks (keeps context together)."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > size:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


class Retriever:
    def __init__(self, persist_dir: str = ".chroma", collection: str = "docs"):
        import chromadb  # imported lazily so importing this module stays cheap

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(collection)

    def index(self, docs_dir: str, chunk_size: int = 800) -> int:
        """(Re)index every .md/.txt file under ``docs_dir``. Returns chunk count."""
        paths = glob.glob(os.path.join(docs_dir, "**", "*.md"), recursive=True)
        paths += glob.glob(os.path.join(docs_dir, "**", "*.txt"), recursive=True)
        ids, docs, metas = [], [], []
        for p in sorted(paths):
            text = pathlib.Path(p).read_text(encoding="utf-8")
            for i, chunk in enumerate(_chunk(text, chunk_size)):
                ids.append(f"{p}::{i}")
                docs.append(chunk)
                metas.append({"source": os.path.basename(p), "chunk": i})
        if ids:
            self.collection.upsert(ids=ids, documents=docs, metadatas=metas)
        return len(ids)

    def search(self, query: str, k: int = 4) -> list[str]:
        if self.collection.count() == 0:
            return []
        res = self.collection.query(query_texts=[query], n_results=k)
        return res.get("documents", [[]])[0]
