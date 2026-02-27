"""
RAG QA Agent 最小链路 Demo 脚本

演示 RAG 问答流程（含 mock 笔记 + 可选真实 FAISS + 可选 LLM）。

使用方法：
    # 仅用 mock 数据（无需 API Key）
    python knowledge_base/rag_demo.py

    # 使用真实 FAISS 索引（需先运行 build_faiss_index.py）
    python knowledge_base/rag_demo.py --use-faiss

    # 使用 Chroma 动态笔记库（从 mock_notes/ 导入）
    python knowledge_base/rag_demo.py --use-chroma

    # 同时使用 LLM 生成（需配置 SILICONFLOW_API_KEY）
    SILICONFLOW_API_KEY=your_key python knowledge_base/rag_demo.py --use-llm

    # 完整模式
    SILICONFLOW_API_KEY=your_key python knowledge_base/rag_demo.py \\
        --use-faiss --use-chroma --use-llm --question "什么是极限？"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_REPO_ROOT = str(Path(__file__).parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.rag_agent import run_rag  # noqa: E402

# ---------------------------------------------------------------------------
# Mock FAISS 检索器（当没有真实索引时使用）
# ---------------------------------------------------------------------------

_MOCK_FAISS_DATA = [
    {
        "id": 1,
        "subject": "数学",
        "year": 2023,
        "question_type": "选择题",
        "content": "设函数 f(x) 在点 x₀ 的某去心邻域内有定义，若 lim(x→x₀) f(x) = L，则下列说法正确的是？",
        "correct_answer": "B. f(x₀) 不一定等于 L",
        "score": 0.91,
        "vector_id": 0,
    },
    {
        "id": 2,
        "subject": "数学",
        "year": 2022,
        "question_type": "计算题",
        "content": "计算极限 lim(x→0) sin(x)/x",
        "correct_answer": "1",
        "score": 0.88,
        "vector_id": 1,
    },
    {
        "id": 3,
        "subject": "数学",
        "year": 2021,
        "question_type": "选择题",
        "content": "数列 {aₙ} 收敛的充要条件是？",
        "correct_answer": "C. 数列有界且单调",
        "score": 0.75,
        "vector_id": 2,
    },
]


def _mock_searcher(query: str, top_k: int) -> list[dict]:
    """使用 mock 数据的 FAISS 检索器（不需要索引文件或 API Key）。"""
    print(f"  [Mock FAISS] 检索 query={query!r}, top_k={top_k}")
    return _MOCK_FAISS_DATA[:top_k]


# ---------------------------------------------------------------------------
# 加载 Chroma 笔记（从 mock_notes/ 目录）
# ---------------------------------------------------------------------------

_MOCK_NOTES_DIR = Path(_REPO_ROOT) / "mock_notes"


def _setup_chroma_with_mock_notes(persist_dir: str) -> "ChromaManager":
    """将 mock_notes/ 目录下的 Markdown 文件导入 Chroma 并返回 ChromaManager。"""
    from knowledge_base.chroma_manager import ChromaManager  # noqa: PLC0415

    # 使用 mock embedding 函数（无需 API Key），用于演示
    import hashlib

    def _demo_embed(text: str) -> list[float]:
        h = int(hashlib.md5(text.encode()).hexdigest(), 16)
        dim = 8
        return [(h >> (i * 4) & 0xF) / 15.0 for i in range(dim)]

    manager = ChromaManager(
        collection_name="demo_notes",
        persist_dir=persist_dir,
        embedding_fn=_demo_embed,
    )

    md_files = list(_MOCK_NOTES_DIR.glob("*.md"))
    if not md_files:
        print("  [Chroma] mock_notes/ 目录下没有 .md 文件")
        return manager

    for md_file in md_files:
        try:
            doc_id = manager.add_note_from_file(str(md_file))
            print(f"  [Chroma] 导入笔记: {md_file.name} (id={doc_id[:8]}…)")
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"  [Chroma] 导入失败 {md_file.name}: {exc}")

    print(f"  [Chroma] 共导入 {manager.count()} 条笔记")
    return manager


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RAG QA Agent 最小链路 Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--question",
        default="什么是极限？请结合知识库解释。",
        help="用户问题（默认：什么是极限？）",
    )
    parser.add_argument(
        "--use-faiss",
        action="store_true",
        default=False,
        help="使用真实 FAISS 索引（需先运行 build_faiss_index.py）",
    )
    parser.add_argument(
        "--use-chroma",
        action="store_true",
        default=False,
        help="使用 Chroma 动态笔记库（自动导入 mock_notes/）",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        default=False,
        help="调用 LLM 生成答案（需配置 SILICONFLOW_API_KEY）",
    )
    parser.add_argument(
        "--n-faiss",
        type=int,
        default=3,
        help="FAISS 检索返回数量（默认 3）",
    )
    parser.add_argument(
        "--n-chroma",
        type=int,
        default=2,
        help="Chroma 检索返回数量（默认 2）",
    )
    return parser.parse_args()


def _print_separator(char: str = "─", width: int = 60) -> None:
    print(char * width)


def main() -> None:
    args = _parse_args()

    print("\n🔍 RAG QA Agent Demo")
    _print_separator("═")
    print(f"问题：{args.question}")
    _print_separator()

    # --- FAISS 检索器 ---
    faiss_searcher = None
    if args.use_faiss:
        print("📚 使用真实 FAISS 索引")
        # 使用默认检索器（knowledge_base.search_demo.search）
        try:
            from knowledge_base.search_demo import search  # noqa: PLC0415

            faiss_searcher = search
        except (ImportError, FileNotFoundError, RuntimeError) as exc:
            print(f"  [警告] FAISS 索引加载失败，回退到 mock：{exc}")
            faiss_searcher = _mock_searcher
    else:
        print("📚 使用 Mock FAISS 数据（无需索引文件）")
        faiss_searcher = _mock_searcher

    # --- Chroma 笔记库 ---
    chroma_manager = None
    if args.use_chroma:
        print("📝 加载 Chroma 动态笔记库 (mock_notes/)…")
        import tempfile

        _tmp_chroma = tempfile.mkdtemp(prefix="rag_demo_chroma_")
        chroma_manager = _setup_chroma_with_mock_notes(_tmp_chroma)

    # --- LLM ---
    api_key = ""
    if args.use_llm:
        api_key = os.environ.get("SILICONFLOW_API_KEY", "")
        if not api_key:
            print("⚠️  未找到 SILICONFLOW_API_KEY，将使用模板回复（降级模式）")
        else:
            print("🤖 将调用 DeepSeek-V3 (SiliconFlow) 生成答案")

    _print_separator()
    print("🔄 执行 RAG 流程…\n")

    result = run_rag(
        args.question,
        faiss_searcher=faiss_searcher,
        chroma_manager=chroma_manager,
        api_key=api_key,
        use_faiss=True,
        use_chroma=args.use_chroma,
        n_faiss_results=args.n_faiss,
        n_chroma_results=args.n_chroma,
    )

    # --- 输出结果 ---
    _print_separator("═")
    print("✅ 答案：\n")
    print(result["answer"])

    if result["citations"]:
        _print_separator()
        print(f"📎 溯源引用（共 {len(result['citations'])} 条）：\n")
        for c in result["citations"]:
            source_label = "知识库题目" if c["source"] == "faiss" else "个人笔记"
            meta = c.get("metadata", {})
            subject = meta.get("subject", "")
            year = meta.get("year", "")
            snippet = c["content_snippet"].replace("\n", " ")[:100]
            print(f"  [{c['index']}] {source_label}", end="")
            if subject:
                print(f" | {subject}", end="")
            if year:
                print(f" | {year}", end="")
            print(f"\n      {snippet}…")

    if result["recommendations"]:
        _print_separator()
        print(f"💡 相似题目推荐（共 {len(result['recommendations'])} 条）：\n")
        for i, rec in enumerate(result["recommendations"][:3], 1):
            snippet = rec["content_snippet"].replace("\n", " ")[:100]
            print(f"  {i}. [{rec.get('subject', '')} {rec.get('year', '')}]")
            print(f"     {snippet}…")

    _print_separator("═")
    print(f"🔧 调试信息：FAISS 结果 {len(result['faiss_results'])} 条，"
          f"Chroma 结果 {len(result['chroma_results'])} 条，"
          f"融合后 {len(result['fused_context'])} 条")
    print()


if __name__ == "__main__":
    main()
