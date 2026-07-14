"""Procedures seam — curated "how-to" injected into the prompt ("specialize").

The "skill-like" layer: your domain's steps and rules. For a small curated set
(the common case) every procedure is included. Once the set outgrows the
character budget, procedures are ranked by keyword overlap with the query and
the most relevant are kept — swap in embeddings or an LLM router for smarter
selection at scale.
"""

import glob
import os
import pathlib
import re

_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "to",
    "for",
    "and",
    "or",
    "in",
    "on",
    "at",
    "it",
    "this",
    "that",
    "what",
    "how",
    "do",
    "does",
    "with",
    "you",
    "your",
    "i",
    "my",
    "can",
    "be",
    "as",
    "by",
}


def _keywords(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) >= 3 and w not in _STOPWORDS
    }


def load(procedures_dir: str, query: str, max_chars: int = 4000) -> str:
    """Return curated procedure text to inject into the system prompt."""
    paths = sorted(glob.glob(os.path.join(procedures_dir, "*.md")))
    if not paths:
        return ""
    texts = [pathlib.Path(p).read_text(encoding="utf-8") for p in paths]

    # Small curated set (the common case): include everything.
    if sum(len(t) for t in texts) <= max_chars:
        return "\n\n---\n\n".join(texts)

    # Larger set: rank by keyword overlap and keep the most relevant.
    q = _keywords(query)
    ranked = sorted(texts, key=lambda t: len(q & _keywords(t)), reverse=True)
    out, total = [], 0
    for t in ranked:
        if total + len(t) > max_chars:
            break
        out.append(t)
        total += len(t)
    return "\n\n---\n\n".join(out)
