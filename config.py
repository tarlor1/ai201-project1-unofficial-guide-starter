import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = "llama-3.3-70b-versatile"

# --- Embeddings ---
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# --- Vector store ---
CHROMA_COLLECTION = "unofficial_guide"
CHROMA_PATH = "./chroma_db"

# --- Retrieval ---
N_RESULTS = 5

# --- Documents ---
DOCS_PATH = "./documents"

# --- Chunking (see planning.md "Chunking Strategy") ---
# Message-based: each review/comment/reply is chunked on its own, no overlap,
# because each is a self-contained opinion and most are under 1000 chars.
CHUNK_SIZE = 1000      # max characters per chunk
CHUNK_OVERLAP = 0      # no overlap -- avoids blending different students' opinions
CHUNKS_PATH = "./chunks.jsonl"