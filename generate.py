"""Stage 5 -- Grounded Generation.

Retrieves the top-k chunks for a question and asks the LLM to answer using ONLY
those chunks. Grounding is enforced (not merely suggested) in three ways:

  1. System prompt: hard rules -- answer only from the numbered documents, no
     outside knowledge, and if the documents are insufficient respond with the
     exact refusal string. temperature=0 to minimise improvisation.
  2. A relevance gate: if retrieval finds nothing close enough (all distances
     above WEAK_DISTANCE), we don't even call the LLM -- we return the refusal.
     The model can't hallucinate from context it was never given.
  3. Source attribution is appended PROGRAMMATICALLY from the retrieved chunks'
     metadata after generation, so attribution is guaranteed and accurate
     regardless of what the model writes. (We also ask it to cite [n] inline.)

Public API: answer(query, k) -> dict with keys 'answer', 'sources', 'chunks'.

Run:  python generate.py            # runs the eval-query smoke test
      python generate.py "..."      # answer a single question
"""
import os
import sys

from dotenv import load_dotenv
from groq import Groq

import config
from retrieve import retrieve

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

REFUSAL = "I don't have enough information on that."

# Distances above this are treated as "no real match" -> refuse without calling
# the LLM. Cosine distance; ~<0.5 is strong, >0.6-0.7 is weak (see embed.py).
WEAK_DISTANCE = 0.65

SYSTEM_PROMPT = f"""You are a question-answering assistant for an "unofficial \
guide" to professors at Stony Brook University. Your knowledge comes ONLY from \
the numbered documents provided in each user message. These are real student \
reviews and Reddit comments.

STRICT RULES:
1. Answer using ONLY the information in the provided documents. Do NOT use any \
outside or prior knowledge about these professors, courses, or the university.
2. If the documents do not contain enough information to answer the question, \
reply with EXACTLY this sentence and nothing else: "{REFUSAL}"
3. Do not invent professor names, ratings, courses, or opinions that are not in \
the documents.
4. Cite the documents you used inline with their bracketed numbers, e.g. [1], \
[3]. Only cite documents you actually used.
5. These are student opinions, not official facts -- attribute them as what \
students say (e.g. "students say...", "one commenter notes...").

Keep the answer concise and grounded in the documents."""

_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key or key == "your_key_here":
            raise SystemExit(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add "
                "your key from https://console.groq.com")
        _client = Groq(api_key=key)
    return _client


def format_context(chunks):
    """Render retrieved chunks as numbered documents for the prompt."""
    blocks = []
    for i, c in enumerate(chunks, 1):
        origin = c["source_desc"] or c["source"]
        who = f"u/{c['author']}" if c["author"] else "unknown"
        blocks.append(
            f"[{i}] (source: {origin}; {c['type']} by {who})\n{c['text']}")
    return "\n\n".join(blocks)


def format_sources(chunks):
    """Programmatic, guaranteed source attribution from chunk metadata.

    Deduplicated by (thread/source, url) but keeps the [n] numbers so they line
    up with the model's inline citations.
    """
    lines, seen = [], set()
    for i, c in enumerate(chunks, 1):
        origin = c["source_desc"] or c["source"]
        who = f"u/{c['author']}" if c["author"] else ""
        key = (origin, c["url"])
        marker = "" if key not in seen else " (same source as above)"
        seen.add(key)
        url = f" - {c['url']}" if c["url"] else ""
        lines.append(f"[{i}] {origin} ({c['type']} {who}){url}{marker}")
    return "\n".join(lines)


def answer(query, k=config.N_RESULTS):
    """Run the full RAG pipeline for one query.

    Returns {'answer', 'sources', 'chunks', 'grounded'}. 'answer' already has the
    programmatic Sources block appended (when grounded).
    """
    chunks = retrieve(query, k)

    # Relevance gate: nothing close enough -> refuse without inventing anything.
    if not chunks or min(c["distance"] for c in chunks) > WEAK_DISTANCE:
        return {"answer": REFUSAL, "sources": "", "chunks": chunks,
                "grounded": False}

    user_msg = (
        f"Documents:\n{format_context(chunks)}\n\n"
        f"Question: {query}\n\n"
        f"Answer using only the documents above, citing them as [n].")

    resp = _get_client().chat.completions.create(
        model=config.LLM_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    body = resp.choices[0].message.content.strip()

    if body.strip().rstrip(".") == REFUSAL.rstrip("."):
        return {"answer": REFUSAL, "sources": "", "chunks": chunks,
                "grounded": False}

    # Guarantee attribution regardless of whether the model cited anything.
    sources = format_sources(chunks)
    full = f"{body}\n\nSources:\n{sources}"
    return {"answer": full, "sources": sources, "chunks": chunks,
            "grounded": True}


# Three of the five evaluation-plan questions (see planning.md).
EVAL_QUERIES = [
    "Is Thomas Hemmick a good physics professor for intro physics, and what do "
    "students criticize about him?",
    "Which professor should I avoid for Calculus 1 and 2, and who should I take "
    "the AMS calculus sequence with instead?",
    "Why do students call Marco Martens both the best and worst MAT professor?",
]


def _smoke_test():
    for q in EVAL_QUERIES:
        print("\n" + "#" * 76)
        print("Q:", q)
        print("#" * 76)
        res = answer(q)
        print(res["answer"])
        print(f"\n[grounded={res['grounded']}; "
              f"best distance={min((c['distance'] for c in res['chunks']), default=None):.3f}]")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(answer(" ".join(sys.argv[1:]))["answer"])
    else:
        _smoke_test()
