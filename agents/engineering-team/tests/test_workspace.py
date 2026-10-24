from __future__ import annotations

import pytest

from shared_memory.workspace import list_files, read_file, task_dir, write_file

from conftest import tool_context


def test_write_list_read_round_trip():
    ctx = tool_context()
    assert write_file("pkg/a.py", "x = 1\n", ctx)["status"] == "ok"
    assert list_files(ctx)["files"] == ["pkg/a.py"]
    assert read_file("pkg/a.py", ctx)["content"] == "x = 1\n"


def test_tasks_do_not_see_each_others_files():
    write_file("a.py", "1", tool_context("task-one"))
    assert list_files(tool_context("task-two"))["files"] == []
    assert read_file("a.py", tool_context("task-two"))["status"] == "error"


def test_the_tool_itself_refuses_escapes():
    ctx = tool_context()
    assert write_file("../outside.py", "x", ctx)["status"] == "denied"
    assert read_file("../../README.md", ctx)["status"] == "error"


def test_a_bad_task_id_is_rejected():
    with pytest.raises(ValueError):
        task_dir("../task")


def test_reads_are_truncated():
    ctx = tool_context()
    write_file("big.txt", "y" * 50_000, ctx)
    out = read_file("big.txt", ctx)
    assert out["truncated"] is True and len(out["content"]) == 20_000
