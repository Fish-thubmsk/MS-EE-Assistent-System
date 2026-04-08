"""
note_watcher 单元测试

验证：
- 状态文件的加载/保存（含旧格式迁移）
- 新增/变更文件的检测与入库
- 删除文件的检测与索引清理
- 环境变量配置（NOTES_WATCH_DIR、WATCHER_SCAN_INTERVAL）
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from knowledge_base.chroma_manager import ChromaManager, _doc_id_from_path
from knowledge_base.note_watcher import (
    _get_scan_interval,
    _load_state,
    _save_state,
    scan_and_update,
)

# ---------------------------------------------------------------------------
# 固定 mock embedding（与 test_chroma_manager.py 一致，维度 8）
# ---------------------------------------------------------------------------

_DIM = 8


def _mock_embed(text: str) -> list[float]:
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return [(h >> (i * 4) & 0xF) / 15.0 for i in range(_DIM)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_chroma(tmp_path: Path) -> str:
    return str(tmp_path / "chroma_test")


@pytest.fixture()
def manager(tmp_chroma: str) -> ChromaManager:
    return ChromaManager(
        collection_name="test_notes",
        persist_dir=tmp_chroma,
        embedding_fn=_mock_embed,
    )


@pytest.fixture()
def notes_dir(tmp_path: Path) -> Path:
    d = tmp_path / "notes"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# _load_state / _save_state
# ---------------------------------------------------------------------------


class TestStateIO:
    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        state = _load_state(tmp_path / "nonexistent.json")
        assert state == {}

    def test_save_and_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        data = {"/a/b.md": {"mtime": 1.23, "doc_id": "abc"}}
        _save_state(path, data)
        assert _load_state(path) == data

    def test_load_migrates_old_float_format(self, tmp_path: Path) -> None:
        """旧格式 {path: mtime (float)} 应迁移为新格式 {path: {mtime, doc_id: None}}。"""
        path = tmp_path / "old_state.json"
        old = {"/a/b.md": 1234567890.5}
        path.write_text(json.dumps(old), encoding="utf-8")
        state = _load_state(path)
        assert state == {"/a/b.md": {"mtime": 1234567890.5, "doc_id": None}}

    def test_load_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        assert _load_state(path) == {}


# ---------------------------------------------------------------------------
# _get_scan_interval
# ---------------------------------------------------------------------------


class TestGetScanInterval:
    def test_default_is_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WATCHER_SCAN_INTERVAL", raising=False)
        assert _get_scan_interval() == 5

    def test_reads_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WATCHER_SCAN_INTERVAL", "10")
        assert _get_scan_interval() == 10

    def test_invalid_env_var_falls_back_to_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WATCHER_SCAN_INTERVAL", "not_a_number")
        assert _get_scan_interval() == 5


# ---------------------------------------------------------------------------
# scan_and_update: 新增 / 变更
# ---------------------------------------------------------------------------


class TestScanAddAndUpdate:
    def test_new_file_added_to_chroma(
        self, notes_dir: Path, manager: ChromaManager
    ) -> None:
        md = notes_dir / "a.md"
        md.write_text("# 极限\n极限是微积分的基础。", encoding="utf-8")
        state: dict = {}
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 1
        abs_path = str(md.resolve())
        assert abs_path in state
        assert state[abs_path]["doc_id"] == _doc_id_from_path(abs_path)

    def test_unchanged_file_not_reprocessed(
        self, notes_dir: Path, manager: ChromaManager
    ) -> None:
        md = notes_dir / "b.md"
        md.write_text("内容不变", encoding="utf-8")
        state: dict = {}
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 1
        # 再次扫描，文件 mtime 未变，不重复处理
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 1

    def test_modified_file_reprocessed(
        self, notes_dir: Path, manager: ChromaManager
    ) -> None:
        md = notes_dir / "c.md"
        md.write_text("初始内容", encoding="utf-8")
        state: dict = {}
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 1
        old_mtime = state[str(md.resolve())]["mtime"]

        # 修改文件（强制 mtime 不同）
        md.write_text("修改后的内容", encoding="utf-8")
        time.sleep(0.01)
        md.touch()

        state = scan_and_update(str(notes_dir), manager, state)
        # upsert 不会增加数量（相同 doc_id）
        assert manager.count() == 1
        new_mtime = state[str(md.resolve())]["mtime"]
        assert new_mtime != old_mtime

    def test_nonexistent_dir_returns_state_unchanged(
        self, manager: ChromaManager
    ) -> None:
        state = {"/fake/path.md": {"mtime": 1.0, "doc_id": "x"}}
        result = scan_and_update("/nonexistent_dir_xyz", manager, state)
        assert result == state


# ---------------------------------------------------------------------------
# scan_and_update: 删除
# ---------------------------------------------------------------------------


class TestScanDelete:
    def test_deleted_file_removed_from_chroma(
        self, notes_dir: Path, manager: ChromaManager
    ) -> None:
        md = notes_dir / "del.md"
        md.write_text("将被删除的笔记", encoding="utf-8")
        state: dict = {}
        # 首次扫描：添加入库
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 1

        # 删除文件
        md.unlink()

        # 再次扫描：应检测到删除并移除索引
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 0
        assert str(md.resolve()) not in state

    def test_deleted_file_without_doc_id_does_not_raise(
        self, notes_dir: Path, manager: ChromaManager
    ) -> None:
        """状态中存在 doc_id=None 的条目（旧格式迁移），删除时不应抛出异常。"""
        abs_path = str((notes_dir / "ghost.md").resolve())
        state = {abs_path: {"mtime": 1.0, "doc_id": None}}
        # 文件本身不存在，模拟"孤立"记录
        result = scan_and_update(str(notes_dir), manager, state)
        # 条目应被清除
        assert abs_path not in result
        # ChromaDB 应保持空
        assert manager.count() == 0

    def test_only_deleted_files_removed_others_preserved(
        self, notes_dir: Path, manager: ChromaManager
    ) -> None:
        md1 = notes_dir / "keep.md"
        md2 = notes_dir / "remove.md"
        md1.write_text("保留的笔记", encoding="utf-8")
        md2.write_text("将被删除的笔记", encoding="utf-8")
        state: dict = {}
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 2

        md2.unlink()
        state = scan_and_update(str(notes_dir), manager, state)
        assert manager.count() == 1
        assert str(md1.resolve()) in state
        assert str(md2.resolve()) not in state
