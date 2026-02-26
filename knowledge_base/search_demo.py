"""
Demo: search for similar questions using the FAISS vector index.

Usage:
    python knowledge_base/search_demo.py "马克思主义基本原理" --top-k 5

Environment variables:
    SILICONFLOW_API_KEY  — required; your SiliconFlow API key

Prerequisites:
    Run build_faiss_index.py first to populate the index.
"""

import argparse
import json
import os
import sqlite3

import faiss
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths (mirror build_faiss_index.py)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "..", "datebase", "knowledge_base.db")
INDEX_DIR = os.path.join(_HERE, "faiss_index")
INDEX_FILE = os.path.join(INDEX_DIR, "questions.index")
ID_MAP_FILE = os.path.join(INDEX_DIR, "id_map.json")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_API_URL = os.getenv(
    "SILICONFLOW_API_URL", "https://api.siliconflow.cn/v1/embeddings"
)
EMBEDDING_MODEL = "BAAI/bge-m3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_query_embedding(text: str) -> np.ndarray:
    """Return a L2-normalized embedding vector for *text*."""
    if not SILICONFLOW_API_KEY:
        raise ValueError(
            "SILICONFLOW_API_KEY is not set. "
            "Export it as an environment variable or add it to .env."
        )

    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": [text],
        "encoding_format": "float",
    }
    resp = requests.post(SILICONFLOW_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    vec = np.array([resp.json()["data"][0]["embedding"]], dtype=np.float32)
    faiss.normalize_L2(vec)
    return vec


def _load_index():
    """Load the FAISS index and id_map from disk.

    Raises FileNotFoundError if either file is missing.
    """
    if not os.path.exists(INDEX_FILE) or not os.path.exists(ID_MAP_FILE):
        raise FileNotFoundError(
            f"FAISS index not found in {INDEX_DIR}.\n"
            "Run  python knowledge_base/build_faiss_index.py  first."
        )
    index = faiss.read_index(INDEX_FILE)
    with open(ID_MAP_FILE, "r", encoding="utf-8") as fh:
        id_map = json.load(fh)
    return index, id_map


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search(query: str, top_k: int = 5) -> list:
    """Search the FAISS index for questions similar to *query*.

    Args:
        query:  Natural-language query string.
        top_k:  Number of results to return.

    Returns:
        List of dicts with keys:
            id, subject, year, question_type, content, correct_answer,
            score (cosine similarity), vector_id (FAISS position).
    """
    index, id_map = _load_index()
    query_vec = _get_query_embedding(query)

    scores, indices = index.search(query_vec, top_k)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(id_map):
            continue
        qid = id_map[idx]
        cursor.execute(
            "SELECT id, subject, year, question_type, content, correct_answer "
            "FROM questions WHERE id = ?",
            (qid,),
        )
        row = cursor.fetchone()
        if row:
            results.append(
                {
                    "id": row[0],
                    "subject": row[1],
                    "year": row[2],
                    "question_type": row[3],
                    "content": row[4],
                    "correct_answer": row[5],
                    "score": float(score),
                    "vector_id": int(idx),
                }
            )

    conn.close()
    return results


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Search for similar exam questions using FAISS vector index."
    )
    parser.add_argument("query", help="Natural-language query string.")
    parser.add_argument(
        "--top-k", type=int, default=5, help="Number of results to return (default: 5)."
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    print(f'Searching for: {args.query!r}  (top-{args.top_k})\n{"─" * 60}')

    results = search(args.query, top_k=args.top_k)
    if not results:
        print("No results found.")
    else:
        for rank, r in enumerate(results, 1):
            snippet = r["content"][:120].replace("\n", " ")
            print(
                f'{rank}. [{r["subject"]} {r["year"]}] '
                f'score={r["score"]:.4f}  id={r["id"]}'
            )
            print(f'   {snippet}…\n')
