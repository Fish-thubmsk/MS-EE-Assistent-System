"""
Build a FAISS vector index from questions in knowledge_base.db.

Usage:
    python knowledge_base/build_faiss_index.py [--subject 政治] [--batch-size 32]

Environment variables:
    SILICONFLOW_API_KEY  — required; your SiliconFlow API key
    SILICONFLOW_API_URL  — optional; defaults to https://api.siliconflow.cn/v1/embeddings

The script supports incremental (checkpoint) builds: already-indexed documents
(those whose doc_id already appears in the saved id_map.json) are skipped.

Tables indexed (new schema):
    questions_math      — math questions      (doc_id prefix: qm_<id>)
    questions_politics  — politics questions  (doc_id prefix: qp_<id>)
    questions_english   — English questions   (doc_id prefix: qe_<id>)
    sub_questions       — sub-questions       (doc_id prefix: sq_<id>)

id_map.json format: list of dicts
    {"doc_id": "qm_<id>" | "qp_<id>" | "qe_<id>" | "sq_<id>",
     "source_table": "questions_math" | "questions_politics" | "questions_english" | "sub_questions"}
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

# ---------------------------------------------------------------------------
# Embedding API config
# ---------------------------------------------------------------------------
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_API_URL = os.getenv(
    "SILICONFLOW_API_URL", "https://api.siliconflow.cn/v1/embeddings"
)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")

def _parse_embedding_dim() -> int:
    """从 EMBEDDING_DIM 环境变量读取维度，失败时使用默认值 1024。"""
    raw = os.environ.get("EMBEDDING_DIM", "1024")
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError("must be positive")
        return value
    except (ValueError, TypeError):
        print(
            f"[warn] EMBEDDING_DIM 的值 {raw!r} 无效（应为正整数），使用默认值 1024。"
        )
        return 1024

EMBEDDING_DIM = _parse_embedding_dim()

DEFAULT_BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))
MAX_RETRIES = int(os.getenv("SF_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "5"))  # seconds

# ---------------------------------------------------------------------------
# Table configurations for the new normalized schema
# ---------------------------------------------------------------------------
# Each entry: (table_name, text_column, doc_id_prefix)
QUESTION_TABLES = [
    ("questions_math",     "stem",    "qm"),
    ("questions_politics", "stem",    "qp"),
    ("questions_english",  "content", "qe"),
    ("sub_questions",      "stem",    "sq"),
]

# Map subject name → tables to index for that subject
SUBJECT_TO_TABLES = {
    "数学": [("questions_math",     "stem",    "qm")],
    "政治": [("questions_politics", "stem",    "qp")],
    "英语": [("questions_english",  "content", "qe")],
}


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
            if resp.status_code != 200:
                print(f"  [debug] API response status: {resp.status_code}")
                print(f"  [debug] Response text: {resp.text[:200]}")
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
        (faiss.Index, list[dict]) — index and ordered list of
        {"doc_id": "q_<id>" | "p_<id>", "source_table": "questions" | "passages"} entries.
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
                    *None* means all subjects (all four question tables).
        batch_size: Number of documents sent to the embedding API per request.
        api_key:    Override SILICONFLOW_API_KEY env var.
        api_url:    Override SILICONFLOW_API_URL env var.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Load (or create) the index
    index, id_map = load_or_create_index()
    indexed_ids: set = {entry["doc_id"] for entry in id_map}

    # Determine which tables to query based on subject filter
    if subject:
        tables = SUBJECT_TO_TABLES.get(subject, [])
        if not tables:
            print(
                f"[warn] Unknown subject {subject!r}. "
                f"Valid values: {list(SUBJECT_TO_TABLES)}"
            )
            conn.close()
            return
    else:
        tables = QUESTION_TABLES

    # Build combined list of (doc_id, text, source_table, raw_db_id) to index.
    # Validate table_name and text_col against the allowlist before use in SQL.
    _allowed_tables = {t[0] for t in QUESTION_TABLES}
    _allowed_cols = {t[1] for t in QUESTION_TABLES}
    to_index = []
    total_fetched = 0
    for table_name, text_col, doc_prefix in tables:
        if table_name not in _allowed_tables or text_col not in _allowed_cols:
            raise ValueError(
                f"Unexpected table/column ({table_name!r}, {text_col!r}) — "
                "must be declared in QUESTION_TABLES."
            )
        cursor.execute(
            f"SELECT id, {text_col} FROM {table_name} "
            f"WHERE {text_col} IS NOT NULL ORDER BY id"
        )
        rows = cursor.fetchall()
        total_fetched += len(rows)
        for row_id, text in rows:
            doc_id = f"{doc_prefix}_{row_id}"
            if doc_id not in indexed_ids:
                to_index.append((doc_id, text, table_name, row_id))

    print(
        f"Total questions fetched: {total_fetched} "
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
        batch_doc_ids = [row[0] for row in batch]
        batch_texts = [row[1] for row in batch]
        batch_sources = [row[2] for row in batch]
        batch_raw_ids = [row[3] for row in batch]

        print(
            f"Batch {batch_num}/{total_batches} "
            f"(doc_ids {batch_doc_ids[0]}–{batch_doc_ids[-1]}) …"
        )

        embeddings = get_embeddings(batch_texts, api_key=api_key, api_url=api_url)
        vectors = np.array(embeddings, dtype=np.float32)

        # L2-normalize for cosine similarity via inner product
        faiss.normalize_L2(vectors)

        start_vid = index.ntotal
        index.add(vectors)

        # Update in-memory id_map with source metadata
        new_entries = [
            {"doc_id": doc_id, "source_table": src}
            for doc_id, src in zip(batch_doc_ids, batch_sources)
        ]
        id_map.extend(new_entries)

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
