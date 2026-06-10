"""Stage 4 -- Retrieval.

`retrieve(query, k)` embeds the query with the same model used at indexing time
and returns the top-k most similar chunks from ChromaDB, each with its text,
cosine distance, and source information (source, thread, author, type, url).

Run directly to smoke-test retrieval against the evaluation-plan questions:
    python retrieve.py
"""
import sys

import chromadb
from sentence_transformers import SentenceTransformer

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Loaded once and reused across queries (model load is the slow part).
_model = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=config.CHROMA_PATH)
        _collection = client.get_collection(config.CHROMA_COLLECTION)
    return _collection


def retrieve(query, k=config.N_RESULTS):
    """Return the top-k chunks for `query` as a list of dicts:
    {id, text, distance, source, source_desc, url, type, author,
     thread_title, parent_author, parent_text}.
    """
    model = _get_model()
    collection = _get_collection()

    q_emb = model.encode([query], normalize_embeddings=True).tolist()
    res = collection.query(
        query_embeddings=q_emb,
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    out = []
    for cid, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0],
        res["metadatas"][0], res["distances"][0],
    ):
        out.append({
            "id": cid,
            "text": doc,
            "distance": dist,
            "source": meta.get("source", ""),
            "source_desc": meta.get("source_desc", ""),
            "url": meta.get("url", ""),
            "type": meta.get("type", ""),
            "author": meta.get("author", ""),
            "thread_title": meta.get("thread_title", ""),
            "parent_author": meta.get("parent_author", ""),
            "parent_text": meta.get("parent_text", ""),
        })
    return out


def print_results(query, k=config.N_RESULTS):
    print("\n" + "#" * 74)
    print(f"QUERY: {query}")
    print("#" * 74)
    for rank, r in enumerate(results := retrieve(query, k), 1):
        flag = "  <-- weak match" if r["distance"] > 0.6 else ""
        print(f"\n[{rank}] distance={r['distance']:.3f}{flag}")
        src = f"{r['source_desc']} | u/{r['author']} | {r['type']}"
        print(f"    source: {src}")
        if r["parent_author"]:
            print(f"    (reply to u/{r['parent_author']})")
        print(f"    url: {r['url']}")
        body = r["text"].replace("\n", " ")
        print(f"    text: {body[:500]}")
    return results


# Three of the five evaluation-plan questions (see planning.md).
EVAL_QUERIES = [
    "Is physics professor Thomas Hemmick a good teacher for PHY 131, "
    "and why do some students criticize him?",
    "Which professor should I avoid for Calculus 1 and 2, and who should "
    "I take the AMS calculus sequence with instead?",
    "Why do students call MAT professor Marco Martens both the best and "
    "worst professor, and what about MAT 324?",
]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print_results(" ".join(sys.argv[1:]))
    else:
        for q in EVAL_QUERIES:
            print_results(q)


