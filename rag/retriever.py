from __future__ import annotations

from sklearn.metrics.pairwise import cosine_similarity

from rag.indexer import build_index


def retrieve(query: str, knowledge_rows: list[dict], limit: int = 3) -> list[dict]:
    index = build_index(knowledge_rows)
    if index is None:
        return []
    scores = cosine_similarity(index.vectorizer.transform([query]), index.matrix).ravel()
    ordered = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:limit]
    return [{"id": index.rows[i]["id"], "title": index.rows[i]["title"], "content": index.rows[i]["content"],
             "score": round(float(score), 4), "source_type": index.rows[i]["source_type"]}
            for i, score in ordered if score > 0]

