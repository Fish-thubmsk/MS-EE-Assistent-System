"""
mock_notes 目录增量监控脚本

用法：
    python knowledge_base/note_watcher.py [--notes-dir mock_notes] [--once]

选项：
    --notes-dir   指定要监控的笔记目录（默认 mock_notes/）
    --once        扫描一次后退出（不持续监控）

功能：
    - 扫描目录下全部 .md 文件，检测新增/变更（通过 mtime 比对）
    - 变更文件自动向量化后存入 ChromaDB
    - 持久化状态记录于 chroma_userdata/.watcher_state.json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from knowledge_base.chroma_manager import ChromaManager

STATE_FILE_NAME = ".watcher_state.json"
SCAN_INTERVAL = 5  # 秒


def _load_state(state_path: Path) -> dict[str, float]:
    """从 JSON 文件加载已处理文件的 mtime 记录。"""
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state_path: Path, state: dict[str, float]) -> None:
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_and_update(
    notes_dir: str,
    manager: ChromaManager,
    state: dict[str, float],
) -> dict[str, float]:
    """
    扫描 notes_dir 中的 .md 文件，将新增/变更的文件存入 ChromaDB。

    Args:
        notes_dir: 要扫描的目录路径。
        manager: ChromaManager 实例。
        state: 已处理文件 {abs_path: mtime} 的字典（会被修改并返回）。

    Returns:
        更新后的 state 字典。
    """
    notes_path = Path(notes_dir)
    if not notes_path.is_dir():
        print(f"[watcher] 目录不存在，跳过：{notes_dir}")
        return state

    for md_file in sorted(notes_path.rglob("*.md")):
        abs_path = str(md_file.resolve())
        mtime = md_file.stat().st_mtime
        if state.get(abs_path) != mtime:
            print(f"[watcher] 检测到变更，正在处理：{md_file.name}")
            try:
                doc_id = manager.add_note_from_file(abs_path)
                state[abs_path] = mtime
                print(f"[watcher] 已存入 ChromaDB，doc_id={doc_id}")
            except (OSError, ValueError, RuntimeError) as exc:
                print(f"[watcher] 处理失败：{md_file.name} → {exc}")
    return state


def watch(
    notes_dir: str = "mock_notes",
    persist_dir: str | None = None,
    once: bool = False,
) -> None:
    """
    启动监控循环。

    Args:
        notes_dir: 笔记目录路径（相对或绝对）。
        persist_dir: ChromaDB 持久化目录；默认读取 CHROMA_PERSIST_DIRECTORY
                     环境变量，若未设置则使用当前工作目录下的 chroma_userdata/。
        once: 若为 True，扫描一次后退出。
    """
    if persist_dir is None:
        persist_dir = os.path.abspath(
            os.environ.get(
                "CHROMA_PERSIST_DIRECTORY",
                os.path.join(os.getcwd(), "chroma_userdata"),
            )
        )

    manager = ChromaManager(persist_dir=persist_dir)
    state_path = Path(persist_dir) / STATE_FILE_NAME
    state = _load_state(state_path)

    print(f"[watcher] 开始监控目录：{os.path.abspath(notes_dir)}")
    print(f"[watcher] ChromaDB 持久化路径：{persist_dir}")

    while True:
        state = scan_and_update(notes_dir, manager, state)
        _save_state(state_path, state)
        if once:
            print(f"[watcher] 扫描完成，当前共 {manager.count()} 条记录。")
            break
        time.sleep(SCAN_INTERVAL)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="mock_notes 增量监控脚本")
    parser.add_argument(
        "--notes-dir",
        default="mock_notes",
        help="笔记目录（默认：mock_notes）",
    )
    parser.add_argument(
        "--persist-dir",
        default=None,
        help="ChromaDB 持久化目录（默认：chroma_userdata/）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="扫描一次后退出（不持续监控）",
    )
    args = parser.parse_args()
    watch(notes_dir=args.notes_dir, persist_dir=args.persist_dir, once=args.once)
