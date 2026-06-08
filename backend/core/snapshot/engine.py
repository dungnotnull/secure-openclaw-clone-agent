from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Optional

from git import Repo, GitCommandError

from backend.core.config import settings


MANIFEST_NAME = ".secureclaw_manifest.json"


class SnapshotEngine:
    """Captures workspace state before every action via git-stash + file manifest.

    The manifest contains a SHA-256 hash of every tracked file, providing a
    byte-for-byte identity check that can be verified after revert.
    """

    def __init__(self, workspace_dir: Path | None = None) -> None:
        self._workspace = workspace_dir or settings.WORKSPACE_DIR
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._repo: Repo | None = None
        self._init_repo()

    # ------------------------------------------------------------------
    # snapshot
    # ------------------------------------------------------------------
    def capture(self) -> str:
        """Take a pre-action snapshot.  Returns the combined state hash."""
        self._git_stash()
        manifest_hash = self._compute_manifest_hash()
        return manifest_hash

    # ------------------------------------------------------------------
    # restore
    # ------------------------------------------------------------------
    def restore_to(self, target_hash: str) -> bool:
        """Attempt to restore workspace to *target_hash* via git stash pop."""
        try:
            self._repo.git.stash("pop", "--index")
        except GitCommandError:
            # No stash to pop – try hard reset
            self._repo.git.checkout("--", ".")
            self._repo.git.clean("-fd")

        current_hash = self._compute_manifest_hash()
        return current_hash == target_hash

    # ------------------------------------------------------------------
    # diff
    # ------------------------------------------------------------------
    def compute_diff(self) -> str:
        try:
            return self._repo.git.diff("--staged")
        except GitCommandError:
            return ""

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _init_repo(self) -> None:
        if not (self._workspace / ".git").exists():
            self._repo = Repo.init(self._workspace)
            self._repo.git.add("-A")
            self._repo.git.commit("-m", "Initial workspace snapshot", allow_empty=True)
        else:
            self._repo = Repo(self._workspace)

    def _git_stash(self) -> None:
        self._repo.git.add("-A")
        self._repo.git.stash("push", "--include-untracked", "-m", "pre-action snapshot")

    def _compute_manifest_hash(self) -> str:
        """SHA-256 over sorted list of (relpath, sha256-of-file)."""
        hasher = hashlib.sha256()
        for root, _dirs, files in os.walk(self._workspace):
            for fname in sorted(files):
                fpath = Path(root) / fname
                if ".git" in fpath.parts:
                    continue
                rel = fpath.relative_to(self._workspace).as_posix()
                file_hash = self._file_sha256(fpath)
                hasher.update(f"{rel}\0{file_hash}\n".encode())
        return hasher.hexdigest()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
