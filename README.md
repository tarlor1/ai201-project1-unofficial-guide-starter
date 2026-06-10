# The Unofficial Guide — Project 1

> **How to use this template:**
> Complete each section *after* you've built and tested the corresponding part of your system.
> Do not write placeholder text — if a section isn't done yet, leave it blank and come back.
> Every section below is required for submission. One-liners will not receive full credit.

---

## Domain

I chose student reviews of professors at Stony Brook University. This knowledge is valuable because it helps students pick the best professors for certain courses. It’s hard to find through official channels because you need to read through a lot of reviews in order to form an opinion on a certain professor.

---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

| # | Source | Description | URL or location |
|---|--------|-------------|-----------------|
| 1 | RateMyProfessor | RateMyProfessors — Marco Martens | https://www.ratemyprofessors.com/professor/1125597 |
| 2 | RateMyProfessor | RateMyProfessors — Erlend Graf | https://www.ratemyprofessors.com/professor/603668 |
| 3 | Coursicle | Coursicle ISE 300 | https://www.coursicle.com/stonybrook/courses/ISE/300/ |
| 4 | Reddit | "Worst Professors at SBU" Thread | https://www.reddit.com/r/SBU/comments/1dmym7l/worst_professors_at_sbu/ |
| 5 | Reddit | The "Best and Worst" Professor Thread | https://www.reddit.com/r/SBU/comments/j0n2ff/who_is_the_best_and_worst_professor_in_stony_brook/ |
| 6 | Reddit | "Best / Most Interesting Professor" Recommendations | https://www.reddit.com/r/SBU/comments/dmqhc6/who_is_the_bestmost_interesting_professor_youve/ |
| 7 | Reddit | Professor & Class Recommendations Thread | https://www.reddit.com/r/SBU/comments/i36oi3/you_recommend_sbus_best_professors_and_classes/ |
| 8 | Reddit | Physics and Math Department Best Professors | https://www.reddit.com/r/SBU/comments/1c8ab9h/best_professors_in_physicsmath_departments_at_sbu/ |
| 9 | Reddit | SBU Professor Quality Discussion | https://www.reddit.com/r/SBU/comments/16rueqm/are_there_any_good_teachers_at_this_establishment/ |
| 10 | Reddit | Semester Professor Opinions Evaluation | https://www.reddit.com/r/SBU/comments/1jz08ga/fall_25_professors/ |

---

## Chunking Strategy

<!-- Describe your chunking approach with enough specificity that someone else could reproduce it.
     Include:
     - Chunk size (characters or tokens) and why that size fits your documents
     - Overlap size and why (or why not) you used overlap
     - Any preprocessing you did before chunking (e.g., stripping HTML, removing headers)
     - What your final chunk count was across all documents -->

**Chunk size:** At most 1000 characters per chunk.

**Overlap:** 0 characters.

**Why these choices fit your documents:** The corpus is almost entirely made up of short, self-contained opinion units — a Reddit comment is typically 50–400 characters, a RateMyProfessors review 100–600 characters. Each unit expresses one student's complete take on one professor, so splitting across units would blend different students' opinions into a single vector, making retrieval semantically noisy. Message-based chunking treats every review, comment, and reply as its own atomic chunk. The 1000-character ceiling handles the rare long comment without splitting it unless necessary; the vast majority of records fit entirely within one chunk. I did not use overlap as it would only introduce duplicate content when consecutive chunks come from different students, which is harmful rather than helpful here.

Before chunking, every record goes through HTML entity decoding (`&amp;`, `&nbsp;`, etc.), whitespace normalization, Reddit markdown stripping (links, emphasis, bullets), and boilerplate removal (nav/cookie/footer text). For Reddit replies, a context header — `[Thread: title] In reply to u/parent: "..."` — is prepended to each chunk so that the reply's meaning is recoverable without the surrounding thread, and that parent context is also stored as ChromaDB metadata (`parent_author`, `parent_text`).

**Final chunk count:** 354 chunks across all 10 sources (126 replies, 114 top-level comments, 104 RMP reviews, 7 Reddit posts, 3 Coursicle review-page blocks).

---

## Embedding Model

<!-- Name the embedding model you used and explain your choice.
     Then answer: if you were deploying this system for real users and cost wasn't a constraint,
     what tradeoffs would you weigh in choosing a different model?
     Consider: context length limits, multilingual support, accuracy on domain-specific text,
     latency, and local vs. API-hosted. -->

**Model used:** `all-MiniLM-L6-v2`

**Production tradeoff reflection:** For a real deployment, I would consider replacing `all-MiniLM-L6-v2` with a model like `text-embedding-3-large`. The main tradeoff is context length: `all-MiniLM-L6-v2` caps at 256 tokens, which is enough for individual reviews but would truncate any chunk that includes a long parent-comment context header. A larger model would handle those longer inputs without the truncation risk. Accuracy on domain-specific informal text (Reddit slang, abbreviations like "PHY 131", "AMS 151") would also improve with a model trained on broader web data. The latency cost of a larger model matters less here since this is a query-time lookup, not a batch pipeline. Multilingual support is not a concern — the entire corpus is English. Local hosting vs. API depends on data sensitivity; since these are public posts, either is acceptable, but API hosting reduces infrastructure complexity.

---

## Grounded Generation

<!-- Explain how your system enforces grounding — how does it prevent the LLM from answering
     beyond the retrieved documents?
     Describe both your system prompt (what instruction you gave the model) and any structural
     choices (e.g., how you formatted the context, whether you filtered low-relevance chunks).
     Do not just say "I told it to use the documents" — show the actual instruction or explain
     the mechanism. -->

**System prompt grounding instruction:** The system prompt gives the LLM five hard rules, not soft suggestions: (1) answer using *only* the numbered documents provided; (2) if the documents are insufficient, reply with exactly the refusal string `"I don't have enough information on that."` and nothing else; (3) do not invent professor names, ratings, courses, or opinions not present in the documents; (4) cite documents inline with their bracketed numbers `[1]`, `[3]`, etc.; (5) attribute claims as student opinions, not facts. Temperature is set to 0 to minimize improvisation. Additionally, a **relevance gate** runs before the LLM is called at all: if the best cosine distance among the retrieved chunks exceeds 0.65 (the `WEAK_DISTANCE` threshold), the system returns the refusal string without ever invoking the LLM — so the model literally cannot hallucinate from context it was never given. This was verified: a question about a professor not in the corpus returns the refusal even though the LLM would know that professor from its training data.

**How source attribution is surfaced in the response:** Source attribution is **programmatically appended** to every grounded answer by `format_sources()` in `generate.py`, after the LLM call, using only the retrieved chunks' metadata. The function deduplicates by `(source_desc, url)` and produces a numbered list that corresponds to the `[n]` inline citations. This attribution is guaranteed regardless of what the model writes.

---

## Evaluation Report

<!-- Run your 5 test questions from planning.md through your system and record the results.
     Be honest — a partially accurate or inaccurate result that you explain well is more
     valuable than a suspiciously perfect result. -->

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | What do students say about physics professor Thomas Hemmick's intro physics (PHY 131/132) courses, and what criticisms surface despite his popularity? | Praised for engagement and easy grades (~90% get an A). No real criticisms. | Correctly synthesized praise (engaging, high pass rate) and the cheating-accusation criticism from multiple chunks. | Relevant | Accurate |
| 2 | For Calculus 1 and 2, which professor do students warn against, and what alternative do they recommend? | Avoid Jason Starr; take AMS 151 and 161 with Bernhard (William Bernard) instead. | Could not fetch the relevant chunks and did not answer the question. | Off-target | Neutral |
| 3 | Why do students label MAT professor Marco Martens both the "best and worst" professor? | Terrible lecturer but extremely kind and understanding; survive MAT 324 and you'll be "cracked at measure theory." | Correctly captured the "best and worst" framing, the weak-lectures / kind-person contrast, and the MAT 324 payoff. | Relevant | Accurate |
| 4 | What is the consensus on physics professor Erlend Graf? | Overall strongly negative opinion on professor Erlend Graf. Entirely inaccessible and cannot teach well. Hard tests. | Returned negative consensus, quoted the "run for president" comment. | Relevant | Accurate |
| 5 | What are the opposing opinions on AMS professor Matt Reuter? | Fans: "great professor," "Daddy Reuter." Critics: "Reuter is hell on earth. That man is devious." | Surfaced both poles of the debate accurately | Relevant | Accurate |

**Retrieval quality:** Relevant / Partially relevant / Off-target
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

<!-- Identify at least one question where retrieval or generation did not work as expected.
     Write a specific explanation of *why* it failed, tied to a part of the pipeline.

     "The answer was wrong" is not an explanation.

     "The relevant information was split across a chunk boundary, so retrieval returned
     only half the context — the model didn't have enough to answer correctly" is an explanation.

     "The embedding model treated the professor's nickname as out-of-vocabulary and returned
     results from an unrelated review" is an explanation. -->

**Question that failed:** For Calculus 1 and 2, which professor do students warn against, and what alternative do they recommend?

**What the system returned:** The refusal — `"I don't have enough information on that."`.

**Root cause (tied to a specific pipeline stage):** This is a retreival error caused by domain-specific vocabulary mismatch. The embedding model did not understand that AMS 151 and 161 as well as MAT 125 and 126 corresponded to Calculus 1 and Calculus, so it fetched irrelevant chunks.

**What you would change to fix it:** We would need to create a seperate collection for SBU's course catalog so we would be able to rewrite queries to also include the appropriate course codes they are referring to. Then after they are rewritten would we query the reviews collection for information.
---

## Spec Reflection

<!-- Reflect on how planning.md shaped your implementation.
     Answer both questions with at least 2–3 sentences each. -->

**One way the spec helped you during implementation:** The Chunking Strategy section's explicit decision — "each review/comment is self-contained, so no overlap between different reviews" — resolved several implementation questions without needing to re-debate them mid-build. When the question of how to handle Reddit replies came up (do they get their own chunk or get merged with their parent?), the "self-contained unit" framing in the spec gave a clear answer: each reply is its own chunk, but context from the parent is carried as a header and stored in metadata.

**One way your implementation diverged from the spec, and why:** The spec listed PRAW as the Reddit ingestion library and Niche.com as source 4. Both were replaced during implementation. Reddit's unauthenticated JSON endpoint now returns 403 (OAuth required), making PRAW unusable without creating a registered app — which was blocked by Reddit's approval process. The workaround was to parse user-saved shreddit HTML files using BeautifulSoup instead of PRAW. Niche.com was blocked by a PerimeterX "Press & Hold" human verification wall that headless Chromium cannot bypass; it was replaced with a Reddit thread ("Worst Professors at SBU") that covered the same domain (negative professor reviews). Additionally, sources 1 and 2 were originally generic RateMyProfessors directory/search pages, which produced no useful review text; they were replaced mid-implementation with specific professor profile pages (Martens and Graf) that actually contain the reviews the system needs.

---

## AI Usage

<!-- Describe at least 2 specific instances where you used an AI tool during this project.
     For each: what did you give the AI as input, what did it produce, and what did you
     change, override, or direct differently?

     "I used Claude to help me code" is not sufficient.
     "I gave Claude my Chunking Strategy section from planning.md and asked it to implement
     chunk_text(). It returned a function using a fixed character split. I overrode the
     chunk size from 500 to 200 because my documents are short reviews, not long guides." -->

**Instance 1**

- *What I gave the AI:* The Chunking Strategy section from `planning.md` (1000-char max, 0 overlap, message-based), the structure of the Reddit `shreddit` HTML web components (author/depth/score/thingid attributes, body in `div#<thingid>-comment-rtjson-content`), and the requirement that parent-comment context must survive into ChromaDB metadata — not just be used as a text header.
- *What it produced:* `chunk.py` with `chunks_from_record()`, `context_header()`, and `build_metadata()`. It implemented message-based chunking with a context header prepended to each reply chunk, stored `parent_author` and `parent_text` as flat primitive fields in the ChromaDB metadata dict, and wrote the full pipeline output to `chunks.jsonl`.
- *What I changed or overrode:* The initial implementation used `networkidle` in Playwright to wait for page load, which caused the scraper to hang indefinitely on ad-heavy pages (RMP, Coursicle). I directed it to switch to `domcontentloaded` plus an explicit settle timeout. I also directed it to replace the initial RateMyProfessors directory-page sources with specific professor profile pages, and to add a "Load More Ratings" click loop with OneTrust cookie-banner dismissal before the loop starts.

**Instance 2**

- *What I gave the AI:* The grounded generation requirements: enforce grounding (not just suggest it), programmatically guarantee source attribution (not leave it to the LLM), and build a Gradio web UI with an accordion showing retrieved chunks and distances.
- *What it produced:* `generate.py` with a three-layer enforcement mechanism (hard system prompt, a `WEAK_DISTANCE=0.65` relevance gate that blocks the LLM call entirely for low-quality retrievals, and a `format_sources()` function that appends attribution after generation from chunk metadata), and `app.py` with the full Gradio `gr.Blocks` interface including a slider for top-k, example queries, and a collapsible chunk-inspector accordion.
- *What I changed or overrode:* The first draft of the system prompt phrased rules as suggestions ("try to answer only from..."). I directed it to rewrite the rules as hard constraints with exact output requirements (e.g., "reply with EXACTLY this sentence"). I also directed it to add the relevance gate as a structural block before the LLM call rather than relying solely on the system prompt — the key insight being that a model cannot hallucinate from context it was never given.
