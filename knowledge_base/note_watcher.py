"""
mock_notes 目录增量监控脚本

用法：
    python knowledge_base/note_watcher.py [--notes-dir mock_notes] [--once]

选项：
    --notes-dir   指定要监控的笔记目录（默认读取 NOTES_WATCH_DIR 环境变量，回退为 mock_notes/）
    --once        扫描一次后退出（不持续监控）

功能：
    - 扫描目录下全部 .md 文件，检测新增/变更/删除（通过 mtime 比对）
    - 新增/变更文件自动向量化后存入 ChromaDB
    - 删除文件对应的 ChromaDB 索引自动移除
    - 持久化状态记录于 chroma_userdata/.watcher_state.json
    - 扫描间隔由 WATCHER_SCAN_INTERVAL 环境变量控制（默认 5 秒）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from knowledge_base.chroma_manager import ChromaManager

# 加载 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)

STATE_FILE_NAME = ".watcher_state.json"


def _get_scan_interval() -> int:
    """从环境变量 WATCHER_SCAN_INTERVAL 读取扫描间隔（秒），默认 5。"""
    try:
        return int(os.environ.get("WATCHER_SCAN_INTERVAL", "5"))
    except ValueError:
        return 5


def _load_state(state_path: Path) -> dict[str, dict]:
    """
    从 JSON 文件加载已处理文件的状态记录。

    状态格式：
        {
            "/absolute/path/to/file.md": {
                "mtime": 1712578800.123,
                "doc_id": "d4c7f8a2b1e9..."
            }
        }

    兼容旧格式 {path: mtime}，自动迁移为新格式（doc_id 置为 None）。
    """
    if state_path.exists():
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            # 迁移旧格式：值为 float 表示旧的 {path: mtime} 格式
            migrated: dict[str, dict] = {}
            for path, value in raw.items():
                if isinstance(value, (int, float)):
                    migrated[path] = {"mtime": float(value), "doc_id": None}
                else:
                    migrated[path] = value
            return migrated
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state_path: Path, state: dict[str, dict]) -> None:
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_and_update(
    notes_dir: str,
    manager: ChromaManager,
    state: dict[str, dict],
) -> dict[str, dict]:
    """
    扫描 notes_dir 中的 .md 文件，将新增/变更的文件存入 ChromaDB，
    并删除已从目录中移除的文件对应的 ChromaDB 索引。

    Args:
        notes_dir: 要扫描的目录路径。
        manager: ChromaManager 实例。
        state: 已处理文件的状态字典 {abs_path: {mtime, doc_id}}（会被修改并返回）。

    Returns:
        更新后的 state 字典。
    """
    notes_path = Path(notes_dir)
    if not notes_path.is_dir():
        logger.warning("目录不存在，跳过：%s", notes_dir)
        return state

    # 当前目录中所有 .md 文件的绝对路径集合
    current_files = {str(md_file.resolve()) for md_file in notes_path.rglob("*.md")}

    # 检测已删除的文件（在状态记录中但不在当前目录中）
    deleted_paths = set(state.keys()) - current_files
    for abs_path in deleted_paths:
        doc_id = state[abs_path].get("doc_id")
        if doc_id:
            logger.info("检测到文件删除，移除索引：%s（doc_id=%s）", abs_path, doc_id)
            try:
                manager.delete_note(doc_id)
            except (OSError, ValueError, RuntimeError) as exc:
                logger.error("删除索引失败：%s → %s", abs_path, exc)
        else:
            logger.info("检测到文件删除（无 doc_id），跳过索引删除：%s", abs_path)
        del state[abs_path]

    # 处理新增 / 变更的文件
    for md_file in sorted(notes_path.rglob("*.md")):
        abs_path = str(md_file.resolve())
        mtime = md_file.stat().st_mtime
        entry = state.get(abs_path)
        if entry is None or entry.get("mtime") != mtime:
            logger.info("检测到变更，正在处理：%s", md_file.name)
            try:
                doc_id = manager.add_note_from_file(abs_path)
                state[abs_path] = {"mtime": mtime, "doc_id": doc_id}
                logger.info("已存入 ChromaDB，doc_id=%s", doc_id)
            except (OSError, ValueError, RuntimeError) as exc:
                logger.error("处理失败：%s → %s", md_file.name, exc)
    
    # 清理：如果 doc_id 对应的文档在 ChromaDB 中不存在，删除该记录
    # （防止 ChromaDB 被手动删除后，状态文件仍保留旧记录）
    orphaned_paths = []
    total_state_entries = len(state)
    for abs_path, entry in state.items():
        doc_id = entry.get("doc_id")
        if doc_id:
            if not manager.doc_exists(doc_id):
                logger.warning("孤立检测：状态记录中的 doc_id 在 ChromaDB 中不存在，移除：%s（doc_id=%s）", 
                              abs_path, doc_id)
                orphaned_paths.append(abs_path)
    
    if orphaned_paths:
        logger.info("共检测到 %d 个孤立记录，当前状态记录总数：%d", len(orphaned_paths), total_state_entries)
        for abs_path in orphaned_paths:
            del state[abs_path]
        logger.info("孤立清理完成，状态记录现有：%d 条", len(state))
    
    return state


def watch(
    notes_dir: str | None = None,
    persist_dir: str | None = None,
    once: bool = False,
) -> None:
    """
    启动监控循环。

    Args:
        notes_dir: 笔记目录路径（相对或绝对）；默认读取 NOTES_WATCH_DIR 环境变量，
                   若未设置则使用 mock_notes/。
        persist_dir: ChromaDB 持久化目录；默认读取 CHROMA_PERSIST_DIRECTORY
                     环境变量，若未设置则使用当前工作目录下的 chroma_userdata/。
        once: 若为 True，扫描一次后退出。
    """
    if notes_dir is None:
        notes_dir = os.environ.get("NOTES_WATCH_DIR", "mock_notes")

    if persist_dir is None:
        persist_dir = os.path.abspath(
            os.environ.get(
                "CHROMA_PERSIST_DIRECTORY",
                os.path.join(os.getcwd(), "chroma_userdata"),
            )
        )

    scan_interval = _get_scan_interval()

    manager = ChromaManager(persist_dir=persist_dir)
    state_path = Path(persist_dir) / STATE_FILE_NAME
    state = _load_state(state_path)

    logger.info("开始监控目录：%s", os.path.abspath(notes_dir))
    logger.info("ChromaDB 持久化路径：%s", persist_dir)
    logger.info("扫描间隔：%d 秒", scan_interval)

    while True:
        state = scan_and_update(notes_dir, manager, state)
        _save_state(state_path, state)
        if once:
            logger.info("扫描完成，当前共 %d 条记录。", manager.count())
            break
        time.sleep(scan_interval)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[watcher] %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="mock_notes 增量监控脚本")
    parser.add_argument(
        "--notes-dir",
        default=None,
        help="笔记目录（默认：NOTES_WATCH_DIR 环境变量，回退为 mock_notes）",
    )
    parser.add_argument(
        "--persist-dir",
        default=None,
        help="ChromaDB 持久化目录（默认：CHROMA_PERSIST_DIRECTORY 环境变量，回退为 chroma_userdata/）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="扫描一次后退出（不持续监控）",
    )
    args = parser.parse_args()
    watch(notes_dir=args.notes_dir, persist_dir=args.persist_dir, once=args.once)
