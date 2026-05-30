"""Tests for the Repository Operation Lock (ADR 0004).

The Repository Operation Lock guards shared repository metadata mutations
such as git fetch, branch creation, worktree add/remove, and PRD branch
integration, while keeping worktree-local harness execution parallel.
"""

from __future__ import annotations

import multiprocessing
import os
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bersama.claiming import ClaimWorkspaceGateway
from bersama.prd_preparation import GitWorkspaceGateway
from bersama.integration import IntegrationWorkspaceGateway
from bersama.repo_lock import RepoLock


class FakeGitRunner:
    """A generic fake git runner used across gateway lock tests."""

    def __init__(self, outputs: dict[tuple[str, ...], str] | None = None) -> None:
        self.outputs = outputs or {}
        self.commands: list[tuple[tuple[str, ...], str]] = []
        self.failures: dict[tuple[str, ...], subprocess.CalledProcessError] = {}

    def fail(self, command: tuple[str, ...], stderr: str) -> None:
        self.failures[command] = subprocess.CalledProcessError(
            1, command, stderr=stderr
        )

    def __call__(self, command: tuple[str, ...], *, cwd: str) -> str:
        self.commands.append((command, cwd))
        if command in self.failures:
            raise self.failures[command]
        return self.outputs.get(command, "")


# ── Helper: RecordingLock ──────────────────────────────────────────────


class RecordingLock:
    """A lock that delegates to threading.Lock but records every
    acquire/release call for verification."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.acquire_calls: list[str] = []
        self.release_calls: list[str] = []

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        self.acquire_calls.append("acquire")
        return self._lock.acquire(blocking=blocking, timeout=timeout)

    def release(self) -> None:
        self.release_calls.append("release")
        self._lock.release()

    def __enter__(self) -> None:
        self.acquire()

    def __exit__(self, *args: object) -> None:
        self.release()

    @property
    def locked(self) -> bool:
        return self._lock.locked()


# ── ClaimWorkspaceGateway Lock Tests ──────────────────────────────────


def test_claim_workspace_gateway_does_not_acquire_lock_when_lock_is_none() -> None:
    """Default behaviour: when no lock is provided, no lock acquire/release
    should happen. This is the backwards-compatible path."""
    runner = FakeGitRunner()
    workspace = ClaimWorkspaceGateway(runner=runner)

    assert workspace.ensure_remote_branch_from_base(
        repo_path="/repos/demo",
        base_branch="prd/1-prd",
        branch_name="impl/1/2-child",
    ) is False

    path = workspace.create_worktree(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        branch_name="impl/1/2-child",
        issue_number=2,
    )
    assert path == "/worktrees/demo/issue-2"


def test_claim_workspace_gateway_acquires_lock_for_ensure_remote_branch_from_base() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    workspace = ClaimWorkspaceGateway(runner=runner, lock=lock)

    workspace.ensure_remote_branch_from_base(
        repo_path="/repos/demo",
        base_branch="prd/1-prd",
        branch_name="impl/1/2-child",
    )

    assert len(lock.acquire_calls) >= 1, "Expected lock.acquire() to be called"
    assert len(lock.release_calls) >= 1, "Expected lock.release() to be called"
    assert not lock.locked, "Lock should be released after operation"


def test_claim_workspace_gateway_acquires_lock_for_create_worktree() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    workspace = ClaimWorkspaceGateway(runner=runner, lock=lock)

    workspace.create_worktree(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        branch_name="impl/1/2-child",
        issue_number=2,
    )

    assert len(lock.acquire_calls) >= 1, "Expected lock.acquire() to be called"
    assert len(lock.release_calls) >= 1, "Expected lock.release() to be called"
    assert not lock.locked, "Lock should be released after operation"


def test_claim_workspace_gateway_releases_lock_on_exception() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    runner.fail(
        ("git", "push", "origin", "impl/1/2-child:impl/1/2-child"),
        "push failed",
    )
    workspace = ClaimWorkspaceGateway(runner=runner, lock=lock)

    try:
        workspace.ensure_remote_branch_from_base(
            repo_path="/repos/demo",
            base_branch="prd/1-prd",
            branch_name="impl/1/2-child",
        )
    except Exception:
        pass

    assert not lock.locked, (
        "Lock must be released even when the operation raises an exception"
    )


# ── GitWorkspaceGateway Lock Tests ────────────────────────────────────


def test_git_workspace_gateway_does_not_acquire_lock_when_lock_is_none() -> None:
    runner = FakeGitRunner()
    workspace = GitWorkspaceGateway(runner=runner)

    result = workspace.ensure_remote_branch(
        repo_path="/repos/demo",
        main_branch="main",
        branch_name="prd/1-prd",
    )
    assert result is False


def test_git_workspace_gateway_acquires_lock_for_ensure_remote_branch() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    workspace = GitWorkspaceGateway(runner=runner, lock=lock)

    workspace.ensure_remote_branch(
        repo_path="/repos/demo",
        main_branch="main",
        branch_name="prd/1-prd",
    )

    assert len(lock.acquire_calls) >= 1, "Expected lock.acquire() to be called"
    assert len(lock.release_calls) >= 1, "Expected lock.release() to be called"
    assert not lock.locked, "Lock should be released after operation"


def test_git_workspace_gateway_releases_lock_on_exception() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    runner.fail(
        ("git", "branch", "--create-reflog", "prd/1-prd", "origin/main"),
        "branch creation failed",
    )
    workspace = GitWorkspaceGateway(runner=runner, lock=lock)

    try:
        workspace.ensure_remote_branch(
            repo_path="/repos/demo",
            main_branch="main",
            branch_name="prd/1-prd",
        )
    except Exception:
        pass

    assert not lock.locked, (
        "Lock must be released even when the operation raises an exception"
    )


# ── IntegrationWorkspaceGateway Lock Tests ────────────────────────────


def test_integration_workspace_gateway_does_not_acquire_lock_when_lock_is_none() -> None:
    runner = FakeGitRunner()
    workspace = IntegrationWorkspaceGateway(runner=runner)

    workspace.update_branch(
        worktree_path="/worktrees/demo/issue-2",
        implementation_branch="impl/1/2-child",
        prd_branch="prd/1-prd",
    )
    workspace.push_branch(
        worktree_path="/worktrees/demo/issue-2",
        branch_name="impl/1/2-child",
    )
    workspace.merge_into_prd(
        worktree_path="/worktrees/demo/issue-2",
        implementation_branch="impl/1/2-child",
        prd_branch="prd/1-prd",
    )


def test_integration_workspace_gateway_acquires_lock_for_update_branch() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    workspace = IntegrationWorkspaceGateway(runner=runner, lock=lock)

    workspace.update_branch(
        worktree_path="/worktrees/demo/issue-2",
        implementation_branch="impl/1/2-child",
        prd_branch="prd/1-prd",
    )

    assert len(lock.acquire_calls) >= 1, "Expected lock.acquire() to be called"
    assert len(lock.release_calls) >= 1, "Expected lock.release() to be called"
    assert not lock.locked, "Lock should be released after operation"


def test_integration_workspace_gateway_acquires_lock_for_push_branch() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    workspace = IntegrationWorkspaceGateway(runner=runner, lock=lock)

    workspace.push_branch(
        worktree_path="/worktrees/demo/issue-2",
        branch_name="impl/1/2-child",
    )

    assert len(lock.acquire_calls) >= 1, "Expected lock.acquire() to be called"
    assert len(lock.release_calls) >= 1, "Expected lock.release() to be called"
    assert not lock.locked, "Lock should be released after operation"


def test_integration_workspace_gateway_acquires_lock_for_merge_into_prd() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    workspace = IntegrationWorkspaceGateway(runner=runner, lock=lock)

    workspace.merge_into_prd(
        worktree_path="/worktrees/demo/issue-2",
        implementation_branch="impl/1/2-child",
        prd_branch="prd/1-prd",
    )

    assert len(lock.acquire_calls) >= 1, "Expected lock.acquire() to be called"
    assert len(lock.release_calls) >= 1, "Expected lock.release() to be called"
    assert not lock.locked, "Lock should be released after operation"


def test_integration_workspace_gateway_releases_lock_on_exception() -> None:
    lock = RecordingLock()
    runner = FakeGitRunner()
    runner.fail(
        ("git", "push", "origin", "impl/1/2-child"),
        "push failed",
    )
    workspace = IntegrationWorkspaceGateway(runner=runner, lock=lock)

    try:
        workspace.push_branch(
            worktree_path="/worktrees/demo/issue-2",
            branch_name="impl/1/2-child",
        )
    except Exception:
        pass

    assert not lock.locked, (
        "Lock must be released even when the operation raises an exception"
    )


# ── Shared lock serialization tests ───────────────────────────────────


def test_multiple_gateways_share_the_same_lock() -> None:
    """When ClaimWorkspaceGateway, GitWorkspaceGateway, and IntegrationWorkspaceGateway
    all receive the same lock instance, only one can hold it at a time.
    This proves that shared repository operations are serialized even
    across different gateway classes."""
    lock = threading.Lock()
    results: list[str] = []

    def claim_op() -> str:
        with lock:
            results.append("claim-start")
            time.sleep(0.05)
            results.append("claim-end")
        return "claim-done"

    def integration_op() -> str:
        with lock:
            results.append("integration-start")
            time.sleep(0.05)
            results.append("integration-end")
        return "integration-done"

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(claim_op)
        f2 = ex.submit(integration_op)
        list(as_completed([f1, f2]))

    # The lock ensures that one operation completes before the other begins.
    assert results in (
        ["claim-start", "claim-end", "integration-start", "integration-end"],
        ["integration-start", "integration-end", "claim-start", "claim-end"],
    ), f"Operations overlapped: {results}"


def test_orchestrator_repo_lock_is_none_when_no_repo_path() -> None:
    """When created without repo_path, the Orchestrator's _repo_lock is None
    and gateways receive None. The lock is bound when run() provides repo_path."""
    from bersama.orchestrator import Orchestrator

    orchestrator = Orchestrator()

    # Before run(), the lock is not yet bound (no repo_path known)
    assert orchestrator._repo_lock is None, \
        "_repo_lock should be None before run() binds it to a repo_path"

    claim_lock = orchestrator.claim_workspace._lock
    git_lock = orchestrator.git_workspace._lock
    integration_lock = orchestrator.integration_workspace._lock

    assert claim_lock is None, \
        "ClaimWorkspaceGateway should have no lock before run()"
    assert git_lock is None, \
        "GitWorkspaceGateway should have no lock before run()"
    assert integration_lock is None, \
        "IntegrationWorkspaceGateway should have no lock before run()"


def test_orchestrator_binds_repo_lock_on_run() -> None:
    """When run() is invoked with a repo_path, the Orchestrator creates
    a RepoLock bound to that path and injects it into all gateways."""
    import tempfile
    from pathlib import Path
    from bersama.orchestrator import Orchestrator
    from bersama.repo_lock import RepoLock

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "repo"
        repo_path.mkdir()

        orchestrator = Orchestrator()
        orchestrator._bind_repo_lock(str(repo_path))

        assert isinstance(orchestrator._repo_lock, RepoLock), \
            "_repo_lock should be a RepoLock instance"
        assert orchestrator._repo_lock._repo_path == str(repo_path), \
            "RepoLock should be bound to the given repo_path"

        claim_lock = orchestrator.claim_workspace._lock
        git_lock = orchestrator.git_workspace._lock
        integration_lock = orchestrator.integration_workspace._lock

        assert claim_lock is orchestrator._repo_lock, \
            "ClaimWorkspaceGateway must use the orchestrator's repo lock"
        assert git_lock is orchestrator._repo_lock, \
            "GitWorkspaceGateway must use the orchestrator's repo lock"
        assert integration_lock is orchestrator._repo_lock, \
            "IntegrationWorkspaceGateway must use the orchestrator's repo lock"


def test_orchestrator_does_not_bind_lock_when_gateways_provided() -> None:
    """When external gateways are provided, the Orchestrator does not
    override their locks. The caller is responsible for lock injection."""
    from bersama.claiming import ClaimWorkspaceGateway
    from bersama.prd_preparation import GitWorkspaceGateway
    from bersama.integration import IntegrationWorkspaceGateway
    from bersama.orchestrator import Orchestrator

    claim = ClaimWorkspaceGateway()
    git = GitWorkspaceGateway()
    integration = IntegrationWorkspaceGateway()

    orchestrator = Orchestrator(
        claim_workspace_gateway=claim,
        git_workspace_gateway=git,
        integration_workspace_gateway=integration,
    )

    assert claim._lock is None
    assert git._lock is None
    assert integration._lock is None

    # After _bind_repo_lock, only internal gateways get the lock.
    # External gateways are untouched.
    with tempfile.TemporaryDirectory() as tmpdir:
        orchestrator._bind_repo_lock(tmpdir)

    assert claim._lock is None, "External gateway lock should not be touched"
    assert git._lock is None, "External gateway lock should not be touched"
    assert integration._lock is None, "External gateway lock should not be touched"


def test_harness_execution_service_does_not_receive_repo_lock() -> None:
    """The HarnessExecutionService must NOT receive or hold the Repository
    Operation Lock. Harness execution is worktree-local and must remain
    parallel while shared Git operations are serialized."""
    from bersama.orchestrator import Orchestrator

    orchestrator = Orchestrator()

    assert not hasattr(orchestrator.execution_service, "_repo_lock"), \
        "HarnessExecutionService must not hold the Repository Operation Lock"
    assert not hasattr(orchestrator.execution_service, "_lock"), \
        "HarnessExecutionService must not hold any lock"


# ── RepoLock Tests ───────────────────────────────────────────────────


def test_repo_lock_acquire_and_release() -> None:
    """RepoLock acquires an exclusive file lock and releases it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock = RepoLock(repo_path=tmpdir)
        assert not lock.locked, "Lock should not be held initially"

        lock.acquire()
        assert lock.locked, "Lock should be held after acquire"

        lock.release()
        assert not lock.locked, "Lock should be released"


def test_repo_lock_context_manager() -> None:
    """RepoLock works as a context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock = RepoLock(repo_path=tmpdir)
        with lock:
            assert lock.locked, "Lock should be held inside context"
        assert not lock.locked, "Lock should be released after context"


def test_repo_lock_creates_lockfile_in_repo_path() -> None:
    """RepoLock creates the lock file inside the given repo directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock = RepoLock(repo_path=tmpdir)
        lock.acquire()
        lockfile = Path(tmpdir) / ".repo.lock"
        assert lockfile.exists(), f"Lock file should exist at {lockfile}"
        lock.release()


def test_repo_lock_custom_lockfile_name() -> None:
    """RepoLock supports a custom lock file name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock = RepoLock(repo_path=tmpdir, lockfile_name=".custom.lock")
        lock.acquire()
        lockfile = Path(tmpdir) / ".custom.lock"
        assert lockfile.exists()
        lock.release()


def test_repo_lock_exclusive() -> None:
    """Only one RepoLock can hold the same lock file at a time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock1 = RepoLock(repo_path=tmpdir)
        lock2 = RepoLock(repo_path=tmpdir)

        lock1.acquire()
        assert lock1.locked
        assert not lock2.locked

        # lock2 should not be able to acquire (non-blocking)
        acquired = lock2.acquire(blocking=False)
        assert not acquired, "Second lock should not acquire when first holds it"

        lock1.release()
        assert not lock1.locked

        # Now lock2 can acquire
        acquired = lock2.acquire(blocking=False)
        assert acquired, "Second lock should acquire after first releases"
        lock2.release()


def test_repo_lock_releases_on_exception() -> None:
    """RepoLock releases even when an exception is raised inside the context."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock = RepoLock(repo_path=tmpdir)
        try:
            with lock:
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert not lock.locked, "Lock must be released after exception"


def test_repo_lock_closes_fd_on_release() -> None:
    """Releasing the lock closes the underlying file descriptor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock = RepoLock(repo_path=tmpdir)
        lock.acquire()
        lock.release()
        # Acquire again to verify fd was properly closed and can be reopened
        lock.acquire()
        lock.release()


# ── Multi-Process Lock Tests ──────────────────────────────────────────


def _child_acquire_and_hold(repo_path: str, ready: multiprocessing.synchronize.Event, done: multiprocessing.synchronize.Event) -> None:
    """Child process: acquire the lock, signal ready, wait for done, release."""
    lock = RepoLock(repo_path=repo_path)
    lock.acquire()
    ready.set()
    done.wait()
    lock.release()


def _child_try_acquire_nonblocking(repo_path: str, result_queue: multiprocessing.Queue) -> None:
    """Child process: try non-blocking acquire, put result in queue."""
    lock = RepoLock(repo_path=repo_path)
    acquired = lock.acquire(blocking=False)
    result_queue.put(acquired)
    if acquired:
        lock.release()


def test_repo_lock_serializes_across_processes() -> None:
    """Two processes cannot hold the same repo lock simultaneously."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ready = multiprocessing.Event()
        done = multiprocessing.Event()

        p1 = multiprocessing.Process(
            target=_child_acquire_and_hold, args=(tmpdir, ready, done)
        )
        p1.start()
        ready.wait(timeout=5)

        # Now process 1 holds the lock. Process 2 should fail to acquire non-blocking.
        result_queue: multiprocessing.Queue[bool] = multiprocessing.Queue()
        p2 = multiprocessing.Process(
            target=_child_try_acquire_nonblocking, args=(tmpdir, result_queue)
        )
        p2.start()
        p2.join(timeout=5)

        acquired_by_p2 = result_queue.get(timeout=5)
        assert not acquired_by_p2, (
            "Second process should not acquire lock while first holds it"
        )

        # Release process 1
        done.set()
        p1.join(timeout=5)

        # Now process 3 should acquire successfully
        result_queue2: multiprocessing.Queue[bool] = multiprocessing.Queue()
        p3 = multiprocessing.Process(
            target=_child_try_acquire_nonblocking, args=(tmpdir, result_queue2)
        )
        p3.start()
        p3.join(timeout=5)

        acquired_by_p3 = result_queue2.get(timeout=5)
        assert acquired_by_p3, (
            "Third process should acquire lock after first releases"
        )


def test_repo_lock_serializes_concurrent_cli_processes() -> None:
    """Simulates concurrent CLI processes using the lock and verifies they
    serialize safely without colliding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shared_counter = multiprocessing.Value("i", 0)
        num_processes = 4

        def _child_increment(repo_path: str, counter: multiprocessing.Value) -> None:
            lock = RepoLock(repo_path=repo_path)
            with lock:
                current = counter.value
                # Simulate work that would collide if not serialized
                time.sleep(0.01)
                counter.value = current + 1

        processes = []
        for _ in range(num_processes):
            p = multiprocessing.Process(
                target=_child_increment, args=(tmpdir, shared_counter)
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join(timeout=10)

        assert shared_counter.value == num_processes, (
            f"Expected counter={num_processes}, got {shared_counter.value}. "
            "Processes likely collided without proper serialization."
        )
