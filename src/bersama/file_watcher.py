from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterable

from watchfiles import awatch

from bersama.event_bus import Event, EventBus, ISSUES_UPDATED, LOG_APPEND, RUNS_UPDATED


class FileWatcherService:
    def __init__(self, *, event_bus: EventBus, worktree_roots: Iterable[Path]) -> None:
        self._event_bus = event_bus
        self._worktree_roots = [Path(root) for root in worktree_roots]
        self._log_offsets: dict[Path, int] = {}
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._watch_loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _watch_loop(self) -> None:
        try:
            async for changes in awatch(*self._worktree_roots, recursive=True):
                await self.handle_changes(changes)
        except asyncio.CancelledError:
            raise

    async def handle_changes(self, changes: Iterable[tuple[object, str]]) -> None:
        for _change, raw_path in changes:
            path = Path(raw_path)
            issue_number = _issue_number_from_path(path)
            repo_name = _repo_name_from_path(path, self._worktree_roots)
            if issue_number is None or repo_name is None:
                continue

            if path.name == "run-state.json":
                payload = {"repo": repo_name, "issue_number": issue_number}
                await self._event_bus.publish(Event(type=RUNS_UPDATED, data=payload))
                await self._event_bus.publish(Event(type=ISSUES_UPDATED, data=payload))
            elif path.name == "harness.log":
                lines = self._read_appended_lines(path)
                if lines:
                    await self._event_bus.publish(
                        Event(
                            type=LOG_APPEND,
                            data={
                                "repo": repo_name,
                                "issue_number": issue_number,
                                "lines": lines,
                            },
                        )
                    )

    def _read_appended_lines(self, path: Path) -> list[str]:
        if not path.exists():
            return []

        file_size = path.stat().st_size
        previous_offset = self._log_offsets.get(path, 0)
        if file_size < previous_offset:
            previous_offset = 0

        with path.open("r", encoding="utf-8") as handle:
            handle.seek(previous_offset)
            new_content = handle.read()
            self._log_offsets[path] = handle.tell()

        if not new_content:
            return []
        return new_content.splitlines()


def _issue_number_from_path(path: Path) -> int | None:
    for parent in (path.parent, *path.parents):
        if parent.name.startswith("issue-"):
            suffix = parent.name[len("issue-") :]
            try:
                return int(suffix)
            except ValueError:
                return None
    return None


def _repo_name_from_path(path: Path, worktree_roots: list[Path]) -> str | None:
    resolved_path = path.resolve()
    for root in worktree_roots:
        try:
            resolved_path.relative_to(root.resolve())
        except ValueError:
            continue
        return root.name
    return None
