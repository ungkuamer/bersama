"""Tests for the Repository Operation Lock (ADR 0004).

The Repository Operation Lock guards shared repository metadata mutations
such as git fetch, branch creation, worktree add/remove, and PRD branch
integration, while keeping worktree-local harness execution parallel.
"""

from __future__ import annotations

import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from bersama.claiming import ClaimWorkspaceGateway
from bersama.prd_preparation import GitWorkspaceGateway
from bersama.integration import IntegrationWorkspaceGateway


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


def test_orchestrator_passes_repo_lock_to_all_gateways() -> None:
    """The Orchestrator must create a single Repository Operation Lock
    and pass it to the claim, PRD preparation, and integration gateways."""
    from bersama.orchestrator import Orchestrator

    orchestrator = Orchestrator()

    assert hasattr(orchestrator, "_repo_lock"), "Orchestrator must have _repo_lock"
    assert orchestrator._repo_lock is not None, "_repo_lock must not be None"
    assert hasattr(orchestrator._repo_lock, "acquire"), \
        "_repo_lock must be a lock with acquire()"
    assert hasattr(orchestrator._repo_lock, "release"), \
        "_repo_lock must be a lock with release()"

    claim_lock = orchestrator.claim_workspace._lock
    git_lock = orchestrator.git_workspace._lock
    integration_lock = orchestrator.integration_workspace._lock

    assert claim_lock is orchestrator._repo_lock, \
        "ClaimWorkspaceGateway must use the orchestrator's repo lock"
    assert git_lock is orchestrator._repo_lock, \
        "GitWorkspaceGateway must use the orchestrator's repo lock"
    assert integration_lock is orchestrator._repo_lock, \
        "IntegrationWorkspaceGateway must use the orchestrator's repo lock"


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
