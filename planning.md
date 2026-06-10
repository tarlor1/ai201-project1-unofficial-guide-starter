# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

<!-- What domain did you choose? Why is this knowledge valuable and hard to find through official channels? -->
I chose student reviews of professors at Stony Brook University. This knowledge is valuable because it helps students pick the best professors for certain courses. It’s hard to find through official channels because you need to read through a lot of reviews in order to form an opinion on a certain professor.
---

## Documents

<!-- List your specific sources: URLs, subreddit names, forum threads, or file descriptions.
     Aim for at least 10 sources that together cover different subtopics or perspectives within your domain. -->

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

<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

**Chunk size:** At most 1000 characters

**Overlap:** 0

**Reasoning:**
Every review/comment will be chunked into at most 1000 character chunks without overlapping between different reviews and comments. This is because each review/comment is self contained and most review/comments are below 1000 characters in length.

---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->

**Embedding model:** all-MiniLM-L6-v2

**Top-k:** 5

**Production tradeoff reflection:**
If this system were scaled for production and cost isn't a constraint, I would trade the lightweight all-MiniLM-L6-v2 embedding model for a more enterprise embedding model like text-embedding-3-large since it would allows to ingest highly nested Reddit replies as single chunks without worrying about dilluting the vector representing that chunk. We include 0 overlap because then it would blend different students opinions together.
---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

<!-- Rewritten 2026-06-09 so every question is answerable from the corpus that
     was actually collected. The originals referenced Dmitri Tsybychev and Pramod
     Ganapathi, who appear in zero of the saved r/SBU threads, so Q1 was refocused
     on Hemmick + Graf, Q4 was replaced with Graf, and Q5 was replaced with the
     Reuter debate. Q2 (Starr/Bernhard) and Q3 (Martens) are now supported by the
     added "Worst Professors at SBU" thread and the physics/math thread. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | What do students say about physics professor Thomas Hemmick's intro physics (PHY 131/132) courses, and what criticisms surface despite his popularity? | Praised for engagement and easy grades (~90% get an A). No real criticisms. |
| 2 | For Calculus 1 and 2, which professor do students warn against, and what alternative do they recommend? | Avoid Jason Starr; take AMS 151 and 161 with Bernhard (William Bernard) instead. |
| 3 | Why do students label MAT professor Marco Martens both the "best and worst" professor? | Terrible lecturer but extremely kind and understanding; survive MAT 324 and you'll be "cracked at measure theory." |
| 4 | What is the consensus on physics professor Erlend Graf? | Overall strongly negative opinion on professor Erlend Graf. Entirely inaccessible and cannot teach well. Hard tests. |
| 5 | What are the opposing opinions on AMS professor Matt Reuter? | Fans: "great professor," "Daddy Reuter." Critics: "Reuter is hell on earth. That man is devious." |

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1. Chunks from a reply to a comment may lose some context from the parent comments.
2. Different sources may require different chunking strategies.

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion → Chunking → Embedding + Vector Store → Retrieval → Generation
     Label each stage with the tool or library you're using.
     You can use ASCII art, a Mermaid diagram, or embed a sketch as an image.
     You'll use this diagram as context when prompting AI tools to implement each stage. -->
```text
  +--------------------------------+
  |                                |
  |     1. Document Ingestion      |
  |                                |
  |  [ Custom Python Scripts ]     |
  |  Using: `PRAW` (Reddit),       |
  |        `BeautifulSoup`         |
  |                                |
  +-------------+------------------+
                |
                | (Raw Text, Metadata)
                v
  +-------------+------------------+
  |                                |
  |         2. Chunking            |
  |                                |
  |  [ Text Linearization ]        |
  |  Strategy: Message-Based       |
  |  Specs: 1000 char max,         |
  |        0 overlap               |
  |                                |
  +-------------+------------------+
                |
                | (Atomic, Context-Aware Chunks)
                v
  +-------------+------------------+
  |                                |
  |   3. Embedding + Vector Store  |
  |                                |
  |  [ ChromaDB ]                  |
  |  Model: `all-MiniLM-L6-v2`     |
  |                                |
  +-------------+------------------+
                |
                | (Stored as dense vectors)
                v
  +-------------+------------------+
  |                                |
  |        4. Retrieval            |
  |                                |
  |  [ ChromaDB Vector Search ]    |
  |  Logic: `where` filters +      |
  |        Semantic similarity     |
  |  Top-k: 5 Chunks               |
  |                                |
  +-------------+------------------+
                |
                | (Top-5 Context Blocks)
                v
  +-------------+------------------+
  |                                |
  |       5. Generation            |
  |                                |
  |  [ Generative Language Model ] |
  |  (e.g., GPT-3.5-Turbo, Llama 3)|
  |  Task: Answer query based only |
  |        on retrieved context.   |
  |                                |
  +-------------+------------------+
```
---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:**
Claude
I'll give it the chunking strategy and url sources from the planning.md. I expect it to produce the appropriate code to be able to parse the websites and create readable chunks. In order to verify the output matches my spec, I would print out chunks it has generate and see if they are good or bad.

**Milestone 4 — Embedding and retrieval:**
Claude
I'll give it the Retrieval Approach and the architecture from the planning.md. I expect it to produce code that is able to create embeddings for the chunks. I will then verify that the chunks it has produced are relevant to the question.

**Milestone 5 — Generation and interface:**
Claude
I'll give the architecture section from the planning.md and tell it to write the interface using Gradio. I expect it to produce a workable interface and to be able to use my Groq Api key to produce relevant responses to my question. I will test the frontend and ask it questions to see if it works.