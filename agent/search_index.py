"""Hybrid search over the dataset's glossary and dictionary.

    exact match (term or synonym)        ─┐
    keyword search (Postgres full-text)  ─┼─► reciprocal rank fusion ─► results
    vector search (pgvector)             ─┘

Exact match exists because the glossary's synonyms are authoritative: "sales" IS
Revenue here, even though "Gross sales" has the word in its title.

Everything lives in one table, semantic.documents. Each row stores which embedding
model made its vector; search only compares vectors from the CURRENT model.

Build:   scripts/build_search_index.py
Search:  search("how much did we sell?", kinds=["glossary"])
"""

import json
from contextlib import closing

from pydantic import BaseModel

from agent.config import get_settings
from agent.dataset import load_dictionary, load_glossary
from agent.db import connect
from agent.embeddings import embed_texts, index_model_name

RRF_K = 60           # standard constant for reciprocal rank fusion
CANDIDATES = 20      # how many results each half returns before merging

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS semantic;
CREATE TABLE IF NOT EXISTS semantic.documents (
    dataset          TEXT NOT NULL,
    embedding_model  TEXT NOT NULL,
    doc_id           TEXT NOT NULL,     -- e.g. 'glossary:Revenue', 'table:orders'
    kind             TEXT NOT NULL,     -- 'glossary' or 'table'
    title            TEXT NOT NULL,
    body             TEXT NOT NULL,     -- the text that was embedded
    payload          JSONB NOT NULL,    -- the full original entry, returned to the agent
    embedding        vector({dims}) NOT NULL,
    -- title words weigh more (A) than body words (B) in keyword ranking
    tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', body), 'B')
    ) STORED,
    PRIMARY KEY (dataset, embedding_model, doc_id)
);
-- Lower-cased term + synonyms, for exact matching. (ADD COLUMN: older indexes lacked it.)
ALTER TABLE semantic.documents
    ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
CREATE INDEX IF NOT EXISTS documents_tsv_idx ON semantic.documents USING gin (tsv);
-- No vector index: with ~100 rows an exact scan is instant and perfectly accurate.
"""

# plainto_tsquery joins words with AND ("late & supplier & ..."), which almost never
# matches a whole question. Swapping & for | makes it "any of these words".
KEYWORD_SQL = """
SELECT doc_id
FROM semantic.documents
WHERE dataset = :dataset AND embedding_model = :model AND kind = ANY(:kinds)
  AND tsv @@ replace(plainto_tsquery('english', :query)::text, '&', '|')::tsquery
ORDER BY ts_rank(tsv, replace(plainto_tsquery('english', :query)::text, '&', '|')::tsquery) DESC
LIMIT :limit
"""

EXACT_SQL = """
SELECT doc_id
FROM semantic.documents
WHERE dataset = :dataset AND embedding_model = :model AND kind = ANY(:kinds)
  AND :query_lower = ANY(aliases)
LIMIT :limit
"""

VECTOR_SQL = """
SELECT doc_id
FROM semantic.documents
WHERE dataset = :dataset AND embedding_model = :model AND kind = ANY(:kinds)
ORDER BY embedding <=> CAST(:vector AS vector)   -- <=> is cosine distance
LIMIT :limit
"""


class SearchResult(BaseModel):
    doc_id: str
    kind: str
    title: str
    payload: dict
    score: float
    exact_match: bool         # the query IS this term or one of its synonyms
    keyword_rank: int | None  # 1 = best; None = not found by keyword search
    vector_rank: int | None   # 1 = best; None = not in the vector top results


# --- Build ---------------------------------------------------------------------


def collect_documents(dataset: str | None = None) -> list[dict]:
    """Turn glossary entries and dictionary tables into searchable documents."""
    docs = []

    for entry in load_glossary(dataset).entries:
        parts = [entry.term, f"Also called: {', '.join(entry.synonyms)}.", entry.definition]
        if entry.notes:
            parts.append(entry.notes)
        docs.append({
            "doc_id": f"glossary:{entry.term}",
            "kind": "glossary",
            "title": entry.term,
            "aliases": [a.lower() for a in [entry.term, *entry.synonyms]],
            "body": " ".join(parts),
            "payload": entry.model_dump(exclude_none=True),
        })

    for name, table in load_dictionary(dataset).tables.items():
        column_text = "; ".join(f"{col}: {desc}" for col, desc in table.columns.items())
        docs.append({
            "doc_id": f"table:{name}",
            "kind": "table",
            "title": name,
            "aliases": [name.lower()],
            "body": " ".join([table.description, *table.notes, column_text]),
            "payload": {"table": name, **table.model_dump()},
        })

    return docs


def build_index(dataset: str | None = None) -> dict:
    """(Re)build the index for this dataset + current embedding model. Returns a summary."""
    settings = get_settings()
    dataset = dataset or settings.dataset
    model = index_model_name()

    docs = collect_documents(dataset)
    embedded = embed_texts([d["body"] for d in docs])  # one API call for all documents

    with closing(connect()) as conn:
        conn.execute_simple(SCHEMA_SQL.format(dims=settings.embedding_dimensions))
        conn.run("BEGIN")
        conn.run(
            "DELETE FROM semantic.documents WHERE dataset = :dataset AND embedding_model = :model",
            dataset=dataset, model=model,
        )
        for doc, vector in zip(docs, embedded.vectors, strict=True):
            conn.run(
                """INSERT INTO semantic.documents
                   (dataset, embedding_model, doc_id, kind, title, aliases, body, payload,
                    embedding)
                   VALUES (:dataset, :model, :doc_id, :kind, :title, :aliases, :body,
                           CAST(:payload AS jsonb), CAST(:vector AS vector))""",
                dataset=dataset, model=model, doc_id=doc["doc_id"], kind=doc["kind"],
                title=doc["title"], aliases=doc["aliases"], body=doc["body"],
                payload=json.dumps(doc["payload"]),
                vector=_vector_literal(vector),
            )
        conn.run("COMMIT")

    return {"dataset": dataset, "model": model, "documents": len(docs),
            "tokens": embedded.tokens_used, "cost_usd": embedded.cost_usd}


# --- Search --------------------------------------------------------------------


def search(
    query: str, kinds: list[str] | None = None, limit: int = 5, dataset: str | None = None
) -> list[SearchResult]:
    dataset = dataset or get_settings().dataset
    model = index_model_name()
    kinds = kinds or ["glossary", "table"]
    query_vector = embed_texts([query]).vectors[0]

    with closing(connect()) as conn:
        indexed = conn.run(
            "SELECT count(*) FROM semantic.documents WHERE dataset = :d AND embedding_model = :m",
            d=dataset, m=model,
        )[0][0]
        if indexed == 0:
            raise LookupError(
                f"No search index for dataset '{dataset}' with model '{model}'. "
                "Run: python scripts/build_search_index.py"
            )

        common = {"dataset": dataset, "model": model, "kinds": kinds, "limit": CANDIDATES}
        exact_ids = [row[0] for row in conn.run(
            EXACT_SQL, query_lower=query.strip().lower(), **common)]
        keyword_ids = [row[0] for row in conn.run(KEYWORD_SQL, query=query, **common)]
        vector_ids = [row[0] for row in conn.run(
            VECTOR_SQL, vector=_vector_literal(query_vector), **common)]

        top_ids = _fuse(exact_ids, keyword_ids, vector_ids)[:limit]
        if not top_ids:
            return []
        rows = conn.run(
            """SELECT doc_id, kind, title, payload FROM semantic.documents
               WHERE dataset = :dataset AND embedding_model = :model AND doc_id = ANY(:ids)""",
            dataset=dataset, model=model, ids=[doc_id for doc_id, _ in top_ids],
        )

    by_id = {row[0]: row for row in rows}
    results = []
    for doc_id, score in top_ids:
        _, kind, title, payload = by_id[doc_id]
        results.append(SearchResult(
            doc_id=doc_id, kind=kind, title=title,
            payload=payload if isinstance(payload, dict) else json.loads(payload),
            score=round(score, 5),
            exact_match=doc_id in exact_ids,
            keyword_rank=_rank_of(doc_id, keyword_ids),
            vector_rank=_rank_of(doc_id, vector_ids),
        ))
    return results


def _fuse(*ranked_lists: list[str]) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score = sum of 1 / (RRF_K + rank) across lists."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def _rank_of(doc_id: str, ranked: list[str]) -> int | None:
    return ranked.index(doc_id) + 1 if doc_id in ranked else None


def _vector_literal(vector: list[float]) -> str:
    """pgvector's text format: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"
