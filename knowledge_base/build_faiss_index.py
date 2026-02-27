"""
Build a FAISS vector index from questions in knowledge_base.db.

Usage:
    python knowledge_base/build_faiss_index.py [--subject 政治] [--batch-size 32]

Environment variables:
    SILICONFLOW_API_KEY  — required; your SiliconFlow API key
    SILICONFLOW_API_URL  — optional; defaults to https://api.siliconflow.cn/v1/embeddings

The script supports incremental (checkpoint) builds: already-indexed questions
(those whose id already appears in the saved id_map.json) are skipped.
"""

import argparse
import json
import os
import sqlite3
import time

import faiss
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "..", "datebase", "knowledge_base.db")
INDEX_DIR = os.path.join(_HERE, "faiss_index")
INDEX_FILE = os.path.join(INDEX_DIR, "questions.index")
ID_MAP_FILE = os.path.join(INDEX_DIR, "id_map.json")

# ---------------------------------------------------------------------------
# Embedding API config
# ---------------------------------------------------------------------------
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_API_URL = os.getenv(
    "SILICONFLOW_API_URL", "https://api.siliconflow.cn/v1/embeddings"
)
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024  # bge-m3 output dimension

DEFAULT_BATCH_SIZE = 32
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # seconds


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def get_embeddings(texts: list, api_key: str = "", api_url: str = "") -> list:
    """Call SiliconFlow embedding API for a batch of texts.

    Returns a list of float vectors in the same order as *texts*.
    Raises on unrecoverable errors after MAX_RETRIES attempts.
    """
    api_key = api_key or SILICONFLOW_API_KEY
    api_url = api_url or SILICONFLOW_API_URL

    if not api_key:
        raise ValueError(
            "SILICONFLOW_API_KEY is not set. "
            "Export it as an environment variable or add it to .env."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": texts,
        "encoding_format": "float",
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                api_url, headers=headers, json=payload, timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            # sort by index to preserve input order
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (attempt + 1)
                print(f"  [warn] API error (attempt {attempt + 1}/{MAX_RETRIES}): {exc}. "
                      f"Retrying in {delay}s …")
                time.sleep(delay)

    raise RuntimeError(
        f"Embedding API failed after {MAX_RETRIES} attempts: {last_error}"
    ) from last_error


# ---------------------------------------------------------------------------
# FAISS index helpers
# ---------------------------------------------------------------------------

def load_or_create_index(dim: int = EMBEDDING_DIM):
    """Load an existing FAISS index + id_map, or create a fresh one.

    Returns:
        (faiss.Index, list[int]) — index and ordered list of question ids
    """
    os.makedirs(INDEX_DIR, exist_ok=True)

    if os.path.exists(INDEX_FILE) and os.path.exists(ID_MAP_FILE):
        print(f"Loading existing index from {INDEX_FILE} …")
        index = faiss.read_index(INDEX_FILE)
        with open(ID_MAP_FILE, "r", encoding="utf-8") as fh:
            id_map = json.load(fh)
        print(f"  Loaded {index.ntotal} vectors, {len(id_map)} id mappings.")
        return index, id_map

    print("Creating new FAISS IndexFlatIP index …")
    # IndexFlatIP + L2-normalized vectors  =>  cosine similarity search
    index = faiss.IndexFlatIP(dim)
    return index, []


def save_index(index, id_map: list) -> None:
    """Persist the FAISS index and id_map to disk."""
    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_FILE)
    with open(ID_MAP_FILE, "w", encoding="utf-8") as fh:
        json.dump(id_map, fh)


# ---------------------------------------------------------------------------
# Main build routine
# ---------------------------------------------------------------------------

def build_index(
    subject: str = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    api_key: str = "",
    api_url: str = "",
) -> None:
    """Build (or incrementally extend) the FAISS index.

    Args:
        subject:    Filter by subject (e.g. '政治', '数学', '英语').
                    *None* means all subjects.
        batch_size: Number of questions sent to the embedding API per request.
        api_key:    Override SILICONFLOW_API_KEY env var.
        api_url:    Override SILICONFLOW_API_URL env var.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Load (or create) the index
    index, id_map = load_or_create_index()
    indexed_ids: set = set(id_map)

    # Fetch active questions that have content
    query = (
        "SELECT id, content FROM questions "
        "WHERE is_active = 1 AND content IS NOT NULL"
    )
    params: list = []
    if subject:
        query += " AND subject = ?"
        params.append(subject)
    query += " ORDER BY id"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Only process questions not yet in our index
    to_index = [(qid, content) for qid, content in rows if qid not in indexed_ids]

    print(
        f"Total active questions: {len(rows)} "
        f"| Already indexed: {len(indexed_ids)} "
        f"| To index now: {len(to_index)}"
    )

    if not to_index:
        print("Nothing new to index.")
        conn.close()
        return

    total_batches = (len(to_index) + batch_size - 1) // batch_size

    for batch_num, batch_start in enumerate(range(0, len(to_index), batch_size), 1):
        batch = to_index[batch_start : batch_start + batch_size]
        batch_ids = [row[0] for row in batch]
        batch_texts = [row[1] for row in batch]

        print(
            f"Batch {batch_num}/{total_batches} "
            f"(question ids {batch_ids[0]}–{batch_ids[-1]}) …"
        )

        embeddings = get_embeddings(batch_texts, api_key=api_key, api_url=api_url)
        vectors = np.array(embeddings, dtype=np.float32)

        # L2-normalize for cosine similarity via inner product
        faiss.normalize_L2(vectors)

        start_vid = index.ntotal
        index.add(vectors)

        # Update in-memory id_map
        id_map.extend(batch_ids)

        # Back-fill vector_id in the database
        updates = [(str(start_vid + i), qid) for i, qid in enumerate(batch_ids)]
        cursor.executemany(
            "UPDATE questions SET vector_id = ? WHERE id = ?", updates
        )
        conn.commit()

        # Checkpoint: save after every batch so progress is not lost on error
        save_index(index, id_map)
        print(f"  ✓ Index size: {index.ntotal} vectors saved.")

    print(f"\nDone! FAISS index contains {index.ntotal} vectors.")
    print(f"Index file : {INDEX_FILE}")
    print(f"ID map file: {ID_MAP_FILE}")
    conn.close()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Build a FAISS vector index from knowledge_base.db questions."
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="Only index questions for this subject (e.g. 政治, 数学, 英语).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Questions per API call (default: {DEFAULT_BATCH_SIZE}).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if not SILICONFLOW_API_KEY:
        print(
            "[error] SILICONFLOW_API_KEY is not set.\n"
            "Set it in your .env file or as an environment variable."
        )
    else:
        build_index(subject=args.subject, batch_size=args.batch_size)
