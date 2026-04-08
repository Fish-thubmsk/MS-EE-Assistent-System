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
# Paths  (env-var overrideable; fall back to CWD-relative defaults so the
#         project works regardless of how the script is packaged or moved)
# ---------------------------------------------------------------------------
_REPO_ROOT = os.getcwd()
DB_PATH = os.path.abspath(
    os.environ.get(
        "KNOWLEDGE_DB_PATH",
        os.path.join(_REPO_ROOT, "datebase", "knowledge_base.db"),
    )
)
INDEX_DIR = os.path.abspath(
    os.environ.get(
        "FAISS_INDEX_DIR",
        os.path.join(_REPO_ROOT, "knowledge_base", "faiss_index"),
    )
)
INDEX_FILE = os.path.join(INDEX_DIR, "questions.index")
ID_MAP_FILE = os.path.join(INDEX_DIR, "id_map.json")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_API_URL = os.getenv(
    "SILICONFLOW_API_URL", "https://api.siliconflow.cn/v1/embeddings"
)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")


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

def search(query: str, top_k: int = 5, source_table: str = None) -> list:
    """Search the FAISS index for documents similar to *query*.

    Args:
        query:        Natural-language query string.
        top_k:        Number of results to return.
        source_table: Optional filter; one of "questions_math",
                      "questions_politics", "questions_english",
                      "sub_questions".

    Returns:
        List of dicts. Each result includes:
            doc_id, source_table, id, subject, question_type, content,
            score, vector_id.
        Additional fields where available: year, correct_answer, analysis.
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
        entry = id_map[idx]
        # Support both new dict format and legacy int format
        if isinstance(entry, dict):
            doc_id = entry["doc_id"]
            src_table = entry["source_table"]
        else:
            doc_id = f"q_{entry}"
            src_table = "questions"

        if source_table and src_table != source_table:
            continue

        try:
            raw_id = int(doc_id.split("_", 1)[1])  # "qm_5" -> 5, "sq_10" -> 10
        except (IndexError, ValueError):
            continue

        if src_table == "questions_math":
            cursor.execute(
                "SELECT id, question_type, stem FROM questions_math WHERE id = ?",
                (raw_id,),
            )
            row = cursor.fetchone()
            if row:
                results.append(
                    {
                        "doc_id": doc_id,
                        "source_table": src_table,
                        "id": row[0],
                        "subject": "数学",
                        "year": None,
                        "question_type": row[1],
                        "content": row[2],
                        "score": float(score),
                        "vector_id": int(idx),
                    }
                )

        elif src_table == "questions_politics":
            cursor.execute(
                "SELECT id, year, question_type, stem, correct_answer, analysis "
                "FROM questions_politics WHERE id = ?",
                (raw_id,),
            )
            row = cursor.fetchone()
            if row:
                results.append(
                    {
                        "doc_id": doc_id,
                        "source_table": src_table,
                        "id": row[0],
                        "subject": "政治",
                        "year": row[1],
                        "question_type": row[2],
                        "content": row[3],
                        "correct_answer": row[4],
                        "analysis": row[5],
                        "score": float(score),
                        "vector_id": int(idx),
                    }
                )

        elif src_table == "questions_english":
            cursor.execute(
                "SELECT id, year, question_type, content "
                "FROM questions_english WHERE id = ?",
                (raw_id,),
            )
            row = cursor.fetchone()
            if row:
                results.append(
                    {
                        "doc_id": doc_id,
                        "source_table": src_table,
                        "id": row[0],
                        "subject": "英语",
                        "year": row[1],
                        "question_type": row[2],
                        "content": row[3],
                        "score": float(score),
                        "vector_id": int(idx),
                    }
                )

        elif src_table == "sub_questions":
            cursor.execute(
                "SELECT id, subject_type, question_id, question_number, stem, answer, analysis "
                "FROM sub_questions WHERE id = ?",
                (raw_id,),
            )
            row = cursor.fetchone()
            if row:
                results.append(
                    {
                        "doc_id": doc_id,
                        "source_table": src_table,
                        "id": row[0],
                        "subject": row[1],
                        "year": None,
                        "question_type": None,
                        "content": row[4],
                        "question_id": row[2],
                        "question_number": row[3],
                        "answer": row[5],
                        "analysis": row[6],
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
        description="Search for similar exam questions and passages using FAISS vector index."
    )
    parser.add_argument("query", help="Natural-language query string.")
    parser.add_argument(
        "--top-k", type=int, default=5, help="Number of results to return (default: 5)."
    )
    parser.add_argument(
        "--source-table",
        default=None,
        choices=["questions_math", "questions_politics", "questions_english", "sub_questions"],
        help="Restrict results to a specific source table.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    print(f'Searching for: {args.query!r}  (top-{args.top_k})\n{"─" * 60}')

    results = search(args.query, top_k=args.top_k, source_table=args.source_table)
    if not results:
        print("No results found.")
    else:
        for rank, r in enumerate(results, 1):
            snippet = r["content"][:120].replace("\n", " ")
            subject = r.get("subject", "阅读材料")
            src = r.get("source_table", "questions")
            print(
                f'{rank}. [{subject} {r["year"]}] [{src}] '
                f'score={r["score"]:.4f}  id={r["id"]}'
            )
            print(f'   {snippet}…\n')
