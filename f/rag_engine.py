"""
RAG Engine for MAD Apartments Complaint Hotline
────────────────────────────────────────────────
Ingests complaint-relevant property documents, stores them as
vector embeddings in ChromaDB, and exposes a single async
search function that the voice agent calls as a tool.

Stack:
  - ChromaDB        : local persistent vector store (no server needed)
  - sentence-transformers (all-MiniLM-L6-v2) : free local embeddings
  - Plain .txt files in knowledge_base/       : document source

Usage:
  from rag_engine import search_knowledge_base, build_index
  await build_index()                         # once at startup
  result = await search_knowledge_base("what counts as emergency")
"""

import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────

ROOT_DIR        = Path(__file__).parent
KNOWLEDGE_DIR   = ROOT_DIR / "knowledge_base"
VECTOR_DB_DIR   = ROOT_DIR / "vector_db"
COLLECTION_NAME = "mad_complaints_kb"

# ─────────────────────────────────────────────
# Chunking config
# ─────────────────────────────────────────────

CHUNK_SIZE    = 400   # target words per chunk
CHUNK_OVERLAP = 80    # words of overlap between adjacent chunks
TOP_K         = 3     # number of chunks to return per query

# ─────────────────────────────────────────────
# Lazy singletons — initialised once at startup
# ─────────────────────────────────────────────

_collection  = None
_embed_model = None


def _get_embed_model():
    """Load the embedding model once and cache it."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model (all-MiniLM-L6-v2)…")
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model ready.")
    return _embed_model


def _get_collection():
    """Open (or create) the ChromaDB collection once and cache it."""
    global _collection
    if _collection is None:
        import chromadb
        VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB collection '{COLLECTION_NAME}' ready "
                    f"({_collection.count()} chunks stored).")
    return _collection


# ─────────────────────────────────────────────
# Document loading and chunking
# ─────────────────────────────────────────────

def _load_documents() -> List[Dict]:
    """Read all .txt files from knowledge_base/ and return as dicts."""
    docs = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8").strip()
        docs.append({
            "filename": path.name,
            "source":   path.stem.replace("_", " ").title(),
            "text":     text,
        })
        logger.info(f"Loaded: {path.name}  ({len(text.split())} words)")
    return docs


def _split_into_chunks(text: str, source: str) -> List[Dict]:
    """
    Split text into overlapping word-based chunks.
    Tries to break on section boundaries (━━━ lines) first,
    then falls back to pure word-count splitting.
    """
    # Split on section dividers to keep sections semantically intact
    sections = re.split(r"━{10,}", text)
    sections = [s.strip() for s in sections if s.strip()]

    chunks  = []
    words   = []
    section_texts = []

    for sec in sections:
        w = sec.split()
        if len(w) <= CHUNK_SIZE:
            section_texts.append(sec)
        else:
            # Section is too long — split it further
            i = 0
            while i < len(w):
                chunk_words = w[i: i + CHUNK_SIZE]
                section_texts.append(" ".join(chunk_words))
                i += CHUNK_SIZE - CHUNK_OVERLAP

    # Build chunk dicts
    for idx, content in enumerate(section_texts):
        if not content.strip():
            continue
        chunk_id = hashlib.md5(f"{source}_{idx}_{content[:40]}".encode()).hexdigest()
        chunks.append({
            "id":      chunk_id,
            "text":    content,
            "source":  source,
            "chunk_n": idx,
        })

    return chunks


# ─────────────────────────────────────────────
# Index build
# ─────────────────────────────────────────────

async def build_index(force_rebuild: bool = False) -> int:
    """
    Ingest all documents in knowledge_base/ into ChromaDB.
    Skips documents already indexed (by chunk ID) unless force_rebuild=True.

    Returns the total number of chunks now in the index.
    """
    collection = _get_collection()
    model      = _get_embed_model()

    if force_rebuild:
        logger.info("Force rebuild — clearing existing index…")
        collection.delete(where={"source": {"$ne": "__never__"}})

    docs    = _load_documents()
    added   = 0

    for doc in docs:
        chunks = _split_into_chunks(doc["text"], doc["source"])
        logger.info(f"{doc['filename']}: {len(chunks)} chunks")

        # Filter to only new chunks
        existing_ids = set(collection.get(ids=[c["id"] for c in chunks])["ids"])
        new_chunks   = [c for c in chunks if c["id"] not in existing_ids]

        if not new_chunks:
            logger.info(f"  → already indexed, skipping.")
            continue

        texts      = [c["text"] for c in new_chunks]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            ids        = [c["id"]     for c in new_chunks],
            embeddings = embeddings,
            documents  = texts,
            metadatas  = [{"source": c["source"], "chunk_n": c["chunk_n"]}
                          for c in new_chunks],
        )
        added += len(new_chunks)
        logger.info(f"  → added {len(new_chunks)} new chunks.")

    total = collection.count()
    logger.info(f"Index ready: {total} total chunks ({added} newly added).")
    return total


# ─────────────────────────────────────────────
# Retrieval
# ─────────────────────────────────────────────

async def search_knowledge_base(query: str, top_k: int = TOP_K) -> Dict:
    """
    Semantic search across the complaint knowledge base.

    Args:
        query:  Natural language question from the tenant / agent.
        top_k:  Number of chunks to retrieve (default 3).

    Returns:
        Dict with 'answer' (synthesised context) and 'sources' (list of doc names).
    """
    collection = _get_collection()

    if collection.count() == 0:
        return {
            "success": False,
            "answer":  "The knowledge base has not been built yet. "
                       "Please run build_index() at startup.",
            "sources": [],
        }

    model      = _get_embed_model()
    query_emb  = model.encode([query], show_progress_bar=False).tolist()[0]

    results = collection.query(
        query_embeddings=[query_emb],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]

    if not docs:
        return {
            "success": False,
            "answer":  "No relevant information found in the knowledge base.",
            "sources": [],
        }

    # Filter out low-relevance results (cosine distance > 0.6 means poor match)
    relevant = [
        (d, m) for d, m, dist in zip(docs, metas, distances)
        if dist < 0.6
    ]

    if not relevant:
        return {
            "success": False,
            "answer":  "I couldn't find specific policy information about that. "
                       "I can still help you file a complaint directly.",
            "sources": [],
        }

    sources = list({m["source"] for _, m in relevant})

    # Concatenate retrieved chunks with source attribution
    context_parts = []
    for text, meta in relevant:
        context_parts.append(f"[From: {meta['source']}]\n{text}")

    answer = "\n\n---\n\n".join(context_parts)

    logger.info(f"[RAG] Query: '{query[:60]}…'  "
                f"→ {len(relevant)} chunks from: {sources}")

    return {
        "success": True,
        "answer":  answer,
        "sources": sources,
    }


# ─────────────────────────────────────────────
# CLI helper — run directly to build/inspect index
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    async def _cli():
        cmd = sys.argv[1] if len(sys.argv) > 1 else "build"

        if cmd == "build":
            n = await build_index(force_rebuild="--rebuild" in sys.argv)
            print(f"\n✓ Index contains {n} chunks.")

        elif cmd == "search":
            query = " ".join(sys.argv[2:]) or "what is an emergency"
            await build_index()
            result = await search_knowledge_base(query)
            print(f"\nQuery: {query}\n")
            if result["success"]:
                print(f"Sources: {result['sources']}\n")
                print(result["answer"])
            else:
                print(f"No result: {result['answer']}")

        elif cmd == "stats":
            col = _get_collection()
            print(f"\nCollection '{COLLECTION_NAME}': {col.count()} chunks")

    asyncio.run(_cli())
