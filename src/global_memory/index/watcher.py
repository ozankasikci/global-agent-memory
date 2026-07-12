"""Watchdog adapter with event-loop debouncing and persisted jobs."""

from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent
from watchdog.observers import Observer

from global_memory.index.jobs import IndexJobQueue
from global_memory.vault.paths import is_managed_memory_path


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: VaultWatcher) -> None:
        self.watcher = watcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or event.event_type in {"opened", "closed", "closed_no_write"}:
            return
        if isinstance(event, FileSystemMovedEvent):
            self.watcher.submit(Path(os.fsdecode(event.src_path)), "delete")
            self.watcher.submit(Path(os.fsdecode(event.dest_path)), "upsert")
        else:
            event_type = "delete" if event.event_type == "deleted" else "upsert"
            self.watcher.submit(Path(os.fsdecode(event.src_path)), event_type)


class VaultWatcher:
    """One observer; all SQLite work is marshalled back to the daemon event loop."""

    def __init__(
        self,
        vault_path: Path,
        jobs: IndexJobQueue,
        *,
        debounce_ms: int = 500,
        excluded_globs: list[str] | None = None,
    ) -> None:
        self.vault_path = vault_path.resolve()
        self.jobs = jobs
        self.debounce_seconds = debounce_ms / 1000
        self.excluded_globs = excluded_globs or []
        self.observer = Observer()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.handles: dict[str, asyncio.TimerHandle] = {}

    def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.observer.schedule(_Handler(self), str(self.vault_path), recursive=True)
        self.observer.start()

    def submit(self, absolute_path: Path, event_type: str) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._debounce, absolute_path, event_type)

    def _debounce(self, absolute_path: Path, event_type: str) -> None:
        try:
            relative = absolute_path.resolve(strict=False).relative_to(self.vault_path)
        except ValueError:
            return
        relative_text = relative.as_posix()
        if not is_managed_memory_path(relative) or any(
            fnmatch.fnmatch(relative_text, pattern) for pattern in self.excluded_globs
        ):
            return
        previous = self.handles.pop(relative_text, None)
        if previous is not None:
            previous.cancel()
        self.handles[relative_text] = self.loop.call_later(  # type: ignore[union-attr]
            self.debounce_seconds, self._flush, relative, event_type
        )

    def _flush(self, relative: Path, event_type: str) -> None:
        self.handles.pop(relative.as_posix(), None)
        self.jobs.enqueue(relative, event_type)
        self.jobs.process_due()

    async def stop(self) -> None:
        for handle in self.handles.values():
            handle.cancel()
        self.handles.clear()
        self.observer.stop()
        await asyncio.to_thread(self.observer.join, 5)
