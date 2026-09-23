"""Small TF-IDF vector index; not a semantic embedding model."""

import math
import re
from collections import Counter


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def search(documents: list[dict], query: str, limit: int) -> list[dict]:
    # The caller filters permissions BEFORE indexing, including IDF statistics.
    if not documents:
        return []
    counts = [Counter(tokens(d["title"] + " " + d["text"])) for d in documents]
    vocabulary = set().union(*(c.keys() for c in counts))
    idf = {
        t: math.log((1 + len(counts)) / (1 + sum(t in c for c in counts))) + 1 for t in vocabulary
    }

    def vector(counter):
        raw = {t: count * idf[t] for t, count in counter.items() if t in idf}
        norm = math.sqrt(sum(v * v for v in raw.values()))
        return {t: v / norm for t, v in raw.items()} if norm else {}

    q = vector(Counter(tokens(query)))
    hits = []
    for document, count in zip(documents, counts, strict=True):
        d = vector(count)
        score = sum(value * d.get(term, 0) for term, value in q.items())
        if score > 0:
            hits.append(
                {
                    "id": document["id"],
                    "title": document["title"],
                    "text": document["text"],
                    "score": round(score, 6),
                    "source": "demo://documents/" + document["id"],
                }
            )
    return sorted(hits, key=lambda h: (-h["score"], h["id"]))[:limit]
