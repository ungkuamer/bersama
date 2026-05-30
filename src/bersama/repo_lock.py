"""System-wide file-based repository lock.

Replaces process-local ``threading.Lock`` with a file lock (``fcntl.flock``)
bound to the repository directory, so concurrent CLI processes and
dashboard processes serialize shared git metadata mutations without
colliding.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import TracebackType
from typing import Self


class RepoLock:
    """A system-wide exclusive file lock bound to a repository directory.

    Uses ``fcntl.flock(LOCK_EX)`` on a lock file created inside
    ``repo_path``.  Compatible with any interface that expects
    ``acquire()`` / ``release()`` / context-manager protocol.
    """

    def __init__(
        self, *, repo_path: str, lockfile_name: str = ".repo.lock"
    ) -> None:
        self._repo_path = repo_path
        self._lockfile = Path(repo_path) / lockfile_name
        self._fd: int | None = None

    # ── Public interface ───────────────────────────────────────────

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """Acquire the exclusive file lock.

        Args:
            blocking: If ``True`` (default), block until the lock is
                acquired.  If ``False``, return immediately with
                ``False`` if the lock cannot be acquired.
            timeout: Ignored; kept for interface compatibility with
                ``threading.Lock``.  File locks do not support
                timeouts directly via ``flock``.
        Returns:
            ``True`` if the lock was acquired, ``False`` otherwise.
        """
        if self._fd is not None:
            # Already locked — re-entrant acquire is a no-op.
            return True

        self._lockfile.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._lockfile), os.O_CREAT | os.O_RDWR)
        try:
            operation = fcntl.LOCK_EX
            if not blocking:
                operation |= fcntl.LOCK_NB
            fcntl.flock(fd, operation)
        except BlockingIOError:
            os.close(fd)
            return False
        except Exception:
            os.close(fd)
            raise

        self._fd = fd
        return True

    def release(self) -> None:
        """Release the file lock and close the underlying file descriptor."""
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    @property
    def locked(self) -> bool:
        """Return ``True`` if the lock is currently held."""
        return self._fd is not None

    # ── Context manager ─────────────────────────────────────────────

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()
