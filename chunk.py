"""Stage 2 -- Chunking (message-based).

Reads the per-source record files in ./documents and turns them into chunks
ready for embedding. Strategy from planning.md:

  * chunk size <= 1000 characters, 0 overlap
  * each review / comment / reply is chunked on its OWN -- chunks never span
    two different people's opinions
  * every chunk is made self-contained by prepending context:
      - the thread title (so a comment is tied to its discussion)
      - for a reply, the parent comment's author + a snippet (so the reply's
        "he" / "that class" still resolves)
    This context is also written to each chunk's metadata, so it travels into
    ChromaDB and can be shown as source attribution / used in `where` filters.

Boilerplate that survived ingestion (e.g. Coursicle's alphabetical list of
professor names, RateMyProfessors rating widgets) is dropped here by a prose
filter, since name lists are off-domain noise for a review corpus.

Output: ./chunks.jsonl  (one JSON object per line: id, text, metadata)
Run:    python chunk.py
"""
import json
import re
import sys
from pathlib import Path

import config

# Windows consoles default to cp1252 and crash when printing emoji/curly quotes
# that appear in real reviews. Force UTF-8 so verification output never dies.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCS_DIR = Path(config.DOCS_PATH)
CHUNK_SIZE = config.CHUNK_SIZE
OVERLAP = config.CHUNK_OVERLAP

# Keep context headers from eating the whole budget; body always gets >= this.
MIN_BODY_BUDGET = 600
PARENT_SNIPPET_CHARS = 200
TITLE_CHARS = 120

# A line that's just a person's name (e.g. Coursicle's directory): up to 4
# capitalised words, no sentence punctuation.
_NAME_LINE = re.compile(r"^[A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3}$")
# A list of academic terms ("Fall 2026, Spring 2026, ...") -- page chrome.
_SEMESTER_LIST = re.compile(
    r"^((Fall|Spring|Summer|Winter)\s+\d{4}\s*,?\s*)+$", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


# --------------------------------------------------------------------------- #
# Low-level text splitting
# --------------------------------------------------------------------------- #
def split_text(text, max_size):
    """Split text into <= max_size pieces with no overlap.

    Prefers paragraph boundaries, then sentence boundaries, and only hard-cuts
    a piece if a single sentence is itself longer than max_size.
    """
    text = text.strip()
    if len(text) <= max_size:
        return [text] if text else []

    chunks, buf = [], ""

    def flush():
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for para in re.split(r"\n{2,}", text):
        units = _SENTENCE.split(para) if len(para) > max_size else [para]
        for unit in units:
            unit = unit.strip()
            if not unit:
                continue
            if len(unit) > max_size:
                # A single sentence longer than the budget: hard-split it.
                flush()
                for i in range(0, len(unit), max_size):
                    chunks.append(unit[i:i + max_size])
                continue
            candidate = f"{buf} {unit}".strip() if buf else unit
            if len(candidate) <= max_size:
                buf = candidate
            else:
                flush()
                buf = unit
        # Paragraph break -> prefer to start a new chunk on the next iteration.
        if len(buf) > max_size * 0.7:
            flush()
    flush()
    return chunks


# --------------------------------------------------------------------------- #
# Prose filter (drops name-lists / rating widgets)
# --------------------------------------------------------------------------- #
def keep_prose(line):
    """True only for blocks that read like an actual review/opinion.

    Filters out the chrome that HTML review pages carry: professor name lists,
    semester lists, and page-title headers ("ISE 300 at SBU - Reviews ...").
    """
    line = line.strip()
    if len(line) < 40 or _NAME_LINE.match(line) or _SEMESTER_LIST.match(line):
        return False
    words = len(line.split())
    has_sentence = bool(re.search(r"[.!?]", line))
    # Long blocks are reviews; shorter ones must look like a real sentence.
    # Page-title headers are short and lack sentence punctuation, so they fail.
    if len(line) >= 120:
        return True
    return has_sentence and words >= 12


def review_paragraphs(text):
    """Yield the prose blocks of an HTML review page, dropping name-list noise."""
    for block in re.split(r"\n+", text):
        if keep_prose(block):
            yield block.strip()


# --------------------------------------------------------------------------- #
# Build self-contained, context-carrying chunks from one record
# --------------------------------------------------------------------------- #
def context_header(rec):
    """Human-readable context prefix prepended to every chunk of this record."""
    title = (rec.get("thread_title") or "").strip()[:TITLE_CHARS]
    rtype = rec["type"]

    if rtype == "post":
        return f"[r/SBU thread] {title}"
    if rtype == "comment":
        return f"[Thread: {title}]"
    if rtype == "reply":
        pa = rec.get("parent_author") or "a commenter"
        pt = (rec.get("parent_text") or "").strip()[:PARENT_SNIPPET_CHARS]
        head = f"[Thread: {title}] In reply to {pa}"
        return f'{head}: "{pt}"' if pt else head
    # review_page
    return f"[{rec.get('source')} - {rec.get('thread_title')}]"


def record_bodies(rec):
    """The opinion text(s) of a record, before context is attached."""
    if rec["type"] == "review_page":
        return list(review_paragraphs(rec["text"]))
    body = rec["text"].strip()
    return [body] if body else []


def chunks_from_record(rec, doc_id):
    header = context_header(rec)
    # Reserve room for the header so header+body stays within CHUNK_SIZE.
    body_budget = max(MIN_BODY_BUDGET, CHUNK_SIZE - len(header) - 2)

    out = []
    for body in record_bodies(rec):
        for piece in split_text(body, body_budget):
            text = f"{header}\n{piece}" if header else piece
            out.append((text, piece))
    return out


def build_metadata(rec, doc_id, chunk_index, n_chunks, body_piece):
    """Flat metadata for ChromaDB. Parent context is preserved here so the
    reply->parent relationship survives into the vector store."""
    meta = {
        "doc_id": doc_id,
        "source": rec.get("source", ""),
        "source_desc": rec.get("source_desc", ""),
        "url": rec.get("url", ""),
        "type": rec["type"],
        "author": rec.get("author", ""),
        "score": rec.get("score", 0),
        "thread_title": rec.get("thread_title", ""),
        "depth": rec.get("depth", -1),
        "chunk_index": chunk_index,
        "n_chunks": n_chunks,
    }
    if rec["type"] == "reply":
        meta["parent_author"] = rec.get("parent_author", "")
        meta["parent_text"] = rec.get("parent_text", "")
    return meta


def main():
    record_files = sorted(DOCS_DIR.glob("*.json"))
    if not record_files:
        raise SystemExit(f"No record files in {DOCS_DIR}. Run scrape.py first.")

    out_lines = []
    per_source, per_type = {}, {}

    for path in record_files:
        records = json.loads(path.read_text(encoding="utf-8"))
        for ri, rec in enumerate(records):
            doc_id = f"{path.stem}-{ri}"
            pieces = chunks_from_record(rec, doc_id)
            for ci, (text, body_piece) in enumerate(pieces):
                chunk = {
                    "id": f"{doc_id}-c{ci}",
                    "text": text,
                    "metadata": build_metadata(
                        rec, doc_id, ci, len(pieces), body_piece),
                }
                out_lines.append(json.dumps(chunk, ensure_ascii=False))
                src = rec.get("source_desc", path.stem)
                per_source[src] = per_source.get(src, 0) + 1
                per_type[rec["type"]] = per_type.get(rec["type"], 0) + 1

    Path(config.CHUNKS_PATH).write_text("\n".join(out_lines) + "\n",
                                        encoding="utf-8")

    print(f"Wrote {len(out_lines)} chunks -> {config.CHUNKS_PATH}\n")
    print("By type:")
    for t, n in sorted(per_type.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {t}")
    print("\nBy source:")
    for s, n in sorted(per_source.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {s}")

    # Verification: print one full chunk so it can be eyeballed for leftovers.
    if out_lines:
        sample = json.loads(out_lines[len(out_lines) // 2])
        print("\n" + "=" * 64)
        print("SAMPLE CHUNK (middle of corpus) -- read this for leftover noise")
        print("=" * 64)
        print("id:", sample["id"])
        print("metadata:", json.dumps(sample["metadata"], ensure_ascii=False))
        print("-" * 64)
        print(sample["text"])
        print("=" * 64)


if __name__ == "__main__":
    main()
