"""Stage 3 -- Embedding + Vector Store.

Loads chunks.jsonl, embeds each chunk's text with all-MiniLM-L6-v2, and stores
the vectors in a persistent ChromaDB collection together with their metadata.

Two things matter for this corpus:
  * The text we embed already carries its context header (thread title, and for
    a reply the parent author + snippet), so the parent<->reply relationship is
    baked into the vector -- a reply like "but they are unavoidable" embeds with
    its parent "Spikes and Garcia are hell spawn".
  * That same parent context is also stored in metadata, so it survives into
    ChromaDB for source attribution and `where` filtering.

Cosine distance is used (hnsw:space = cosine) so scores fall in [0, 2], with
0 = identical; ~<0.5 is a strong match, >0.6-0.7 is weak.

Run:  python embed.py
"""
import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_chunks(path):
    chunks = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def main():
    chunks = load_chunks(config.CHUNKS_PATH)
    if not chunks:
        raise SystemExit(f"No chunks in {config.CHUNKS_PATH}. Run chunk.py first.")
    print(f"Loaded {len(chunks)} chunks from {config.CHUNKS_PATH}")

    print(f"Loading embedding model: {config.EMBEDDING_MODEL} ...")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    texts = [c["text"] for c in chunks]
    print("Embedding chunks ...")
    embeddings = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        normalize_embeddings=True,
    ).tolist()

    client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    # Rebuild from scratch so re-runs don't accumulate stale/duplicate vectors.
    try:
        client.delete_collection(config.CHROMA_COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        ids=[c["id"] for c in chunks],
        documents=texts,
        metadatas=[c["metadata"] for c in chunks],
        embeddings=embeddings,
    )

    print(f"\nStored {collection.count()} vectors in collection "
          f"'{config.CHROMA_COLLECTION}' at {config.CHROMA_PATH}")


if __name__ == "__main__":
    main()
