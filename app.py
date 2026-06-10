"""Stage 5 -- Query Interface (Gradio web UI).

A small web app over the full RAG pipeline: type a question, get a grounded
answer with guaranteed source attribution, and (optionally) inspect the exact
chunks that were retrieved along with their cosine distances.

Run:  python app.py
Then open the printed http://127.0.0.1:7860 URL.
"""
import sys

import gradio as gr

import config
from generate import WEAK_DISTANCE, answer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXAMPLES = [
    "Is Thomas Hemmick a good physics professor for intro physics?",
    "Which professor should I avoid for Calculus 1 and 2?",
    "Why do students call Marco Martens both the best and worst MAT professor?",
    "What do students think of Matt Reuter?",
    "Is Erlend Graf a good professor?",
]


def _format_retrieved(chunks):
    """Markdown view of the retrieved chunks + distances, for transparency."""
    lines = []
    for i, c in enumerate(chunks, 1):
        weak = " ⚠️ weak" if c["distance"] > WEAK_DISTANCE else ""
        who = f"u/{c['author']}" if c["author"] else "unknown"
        parent = (f"\n  ↳ *reply to u/{c['parent_author']}*"
                  if c.get("parent_author") else "")
        lines.append(
            f"**[{i}]** `distance={c['distance']:.3f}`{weak} — "
            f"*{c['source_desc']}* · {c['type']} by {who}{parent}\n\n"
            f"> {c['text'].strip().replace(chr(10), ' ')}")
    return "\n\n---\n\n".join(lines) if lines else "_No chunks retrieved._"


def ask(query, k):
    query = (query or "").strip()
    if not query:
        return "Please enter a question.", ""
    res = answer(query, int(k))
    retrieved = _format_retrieved(res["chunks"])
    return res["answer"], retrieved


with gr.Blocks(title="The Unofficial Guide — SBU Professors") as demo:
    gr.Markdown(
        "# 🎓 The Unofficial Guide — SBU Professors\n"
        "Ask about Stony Brook professors and courses. Answers are grounded "
        "**only** in student reviews and r/SBU comments that were retrieved for "
        "your question — if the corpus doesn't cover it, the system says so.")

    with gr.Row():
        query = gr.Textbox(
            label="Your question", scale=4,
            placeholder="e.g. Which professor should I avoid for Calculus 1 and 2?")
        k = gr.Slider(1, 10, value=config.N_RESULTS, step=1,
                      label="Chunks to retrieve (top-k)", scale=1)

    ask_btn = gr.Button("Ask", variant="primary")
    answer_box = gr.Markdown(label="Answer")

    with gr.Accordion("Retrieved chunks (with distance scores)", open=False):
        retrieved_box = gr.Markdown()

    gr.Examples(examples=EXAMPLES, inputs=query)

    ask_btn.click(ask, inputs=[query, k], outputs=[answer_box, retrieved_box])
    query.submit(ask, inputs=[query, k], outputs=[answer_box, retrieved_box])


if __name__ == "__main__":
    demo.launch()
