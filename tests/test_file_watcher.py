from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from rangkai.event_bus import EventBus, ISSUES_UPDATED, LOG_APPEND, METRICS_UPDATED, RUNS_UPDATED
from rangkai.file_watcher import FileWatcherService


@pytest.mark.asyncio
async def test_run_state_change_emits_runs_issues_and_metrics_events(tmp_path: Path) -> None:
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[tmp_path])
    run_state_path = tmp_path / "issue-18" / "run-state.json"
    run_state_path.parent.mkdir(parents=True)
    run_state_path.write_text('{"status":"running", "prd_branch": "prd/7-some-prd"}', encoding="utf-8")

    async with bus.subscribe() as subscriber:
        await watcher.handle_changes({(None, str(run_state_path))})

        first = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)
        second = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)
        third = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)

    assert first.type == RUNS_UPDATED
    assert first.data == {"repo": tmp_path.name, "issue_number": 18}
    assert second.type == ISSUES_UPDATED
    assert second.data == {"repo": tmp_path.name, "issue_number": 18}
    assert third.type == METRICS_UPDATED
    assert third.data == {"repo": tmp_path.name, "issue_number": 18, "prd_number": 7}


@pytest.mark.asyncio
async def test_harness_log_append_emits_only_new_lines(tmp_path: Path) -> None:
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[tmp_path])
    log_path = tmp_path / "issue-18" / "harness.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("line 1\n", encoding="utf-8")

    await watcher.handle_changes({(None, str(log_path))})

    log_path.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    async with bus.subscribe() as subscriber:
        await watcher.handle_changes({(None, str(log_path))})
        event = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)

    assert event.type == LOG_APPEND
    assert event.data == {
        "repo": tmp_path.name,
        "issue_number": 18,
        "lines": ["line 2", "line 3"],
    }


@pytest.mark.asyncio
async def test_harness_log_truncate_resets_offset_and_does_not_emit_old_lines(tmp_path: Path) -> None:
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[tmp_path])
    log_path = tmp_path / "issue-18" / "harness.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("line 1\nline 2\n", encoding="utf-8")

    await watcher.handle_changes({(None, str(log_path))})

    log_path.write_text("fresh line\n", encoding="utf-8")

    async with bus.subscribe() as subscriber:
        await watcher.handle_changes({(None, str(log_path))})
        event = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)

    assert event.type == LOG_APPEND
    assert event.data == {
        "repo": tmp_path.name,
        "issue_number": 18,
        "lines": ["fresh line"],
    }


@pytest.mark.asyncio
async def test_watcher_ignores_paths_without_issue_number(tmp_path: Path) -> None:
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[tmp_path])
    path = tmp_path / "not-an-issue" / "run-state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    async with bus.subscribe() as subscriber:
        await watcher.handle_changes({(None, str(path))})

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(subscriber.__anext__(), timeout=0.05)


@pytest.mark.asyncio
async def test_run_state_without_prd_branch_emits_metrics_without_prd_number(tmp_path: Path) -> None:
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[tmp_path])
    run_state_path = tmp_path / "issue-42" / "run-state.json"
    run_state_path.parent.mkdir(parents=True)
    run_state_path.write_text('{"status":"running"}', encoding="utf-8")

    async with bus.subscribe() as subscriber:
        await watcher.handle_changes({(None, str(run_state_path))})

        # consume RUNS_UPDATED and ISSUES_UPDATED
        await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)
        await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)
        third = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)

    assert third.type == METRICS_UPDATED
    assert third.data == {"repo": tmp_path.name, "issue_number": 42}
    assert "prd_number" not in third.data


@pytest.mark.asyncio
async def test_start_and_stop_manage_background_task() -> None:
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[Path("/tmp/demo")])

    watcher.start()

    assert watcher._task is not None

    watcher.stop()

    await asyncio.sleep(0)

    assert watcher._task.cancelled()


@pytest.mark.asyncio
async def test_quality_gate_result_change_emits_quality_gate_updated_event(tmp_path: Path) -> None:
    from rangkai.event_bus import QUALITY_GATE_UPDATED
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[tmp_path])
    result_path = tmp_path / "issue-18" / "quality-gate" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text('{"status":"passed"}', encoding="utf-8")

    async with bus.subscribe() as subscriber:
        await watcher.handle_changes({(None, str(result_path))})
        event = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)

    assert event.type == QUALITY_GATE_UPDATED
    assert event.data == {"repo": tmp_path.name, "issue_number": 18}


@pytest.mark.asyncio
async def test_judge_layer_artifact_change_emits_quality_gate_updated_event(tmp_path: Path) -> None:
    from rangkai.event_bus import QUALITY_GATE_UPDATED
    bus = EventBus()
    watcher = FileWatcherService(event_bus=bus, worktree_roots=[tmp_path])
    judge_path = tmp_path / "issue-18" / "quality-gate" / "judge.json"
    judge_path.parent.mkdir(parents=True)
    judge_path.write_text('{"status":"running"}', encoding="utf-8")

    async with bus.subscribe() as subscriber:
        await watcher.handle_changes({(None, str(judge_path))})
        event = await asyncio.wait_for(subscriber.__anext__(), timeout=1.0)

    assert event.type == QUALITY_GATE_UPDATED
    assert event.data == {"repo": tmp_path.name, "issue_number": 18}

