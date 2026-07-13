from __future__ import annotations

from dataclasses import dataclass
from sklearn.feature_extraction.text import TfidfVectorizer


@dataclass
class KnowledgeIndex:
    rows: list[dict]
    vectorizer: TfidfVectorizer
    matrix: object


def build_index(rows: list[dict]) -> KnowledgeIndex | None:
    if not rows:
        return None
    texts = [f"{row['title']} {row['content']} {row.get('tags', '')}" for row in rows]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 2), min_df=1)
    return KnowledgeIndex(rows=rows, vectorizer=vectorizer, matrix=vectorizer.fit_transform(texts))

