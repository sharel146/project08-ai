"""The propose -> sandbox-test -> you-approve self-improvement loop.

This is the safe version of "Sunny improves herself". She can read her own
code, and when she wants to change it she does NOT touch the live tree directly.
Instead:

  1. The proposed file is written into an isolated git worktree (a throwaway
     checkout of HEAD) so the running code is never disturbed.
  2. The test suite runs there.
  3. If tests fail, the change is discarded and the failure is reported.
  4. If tests pass, you are asked to approve via your phone.
  5. Only on approval is the change written to the real working tree — and even
     then it is left uncommitted so you review the diff before committing.

That keeps a buggy self-edit from ever reaching the live tree, and keeps you in
the loop for anything that ships.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImprovementOutcome:
    ok: bool
    stage: str  # "validated", "tests_failed", "rejected", "error", "applied"
    detail: str


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=600
    )


class SelfImprover:
    def __init__(self, repo_root: Path, test_command: str):
        self.repo_root = Path(repo_root).resolve()
        self.test_command = test_command

    # --- read-only introspection ---
    def list_files(self) -> list[str]:
        files = _run(["git", "ls-files"], self.repo_root)
        if files.returncode != 0:
            raise RuntimeError(files.stderr.strip() or "git ls-files failed")
        return [f for f in files.stdout.splitlines() if f.strip()]

    def read_file(self, rel_path: str) -> str:
        target = self._resolve_inside_repo(rel_path)
        return target.read_text(encoding="utf-8")

    # --- the propose/test/approve flow ---
    def validate_change(self, rel_path: str, new_content: str) -> ImprovementOutcome:
        """Apply the change in a sandbox worktree and run the tests there.
        Returns the outcome WITHOUT touching the live tree."""
        self._resolve_inside_repo(rel_path)  # path-safety check before doing work
        sandbox = Path(tempfile.mkdtemp(prefix="sunny-sandbox-"))
        worktree = sandbox / "tree"
        try:
            add = _run(
                ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
                self.repo_root,
            )
            if add.returncode != 0:
                return ImprovementOutcome(
                    False, "error", f"could not create sandbox: {add.stderr.strip()}"
                )

            (worktree / rel_path).parent.mkdir(parents=True, exist_ok=True)
            (worktree / rel_path).write_text(new_content, encoding="utf-8")

            tests = _run(self.test_command.split(), worktree)
            if tests.returncode != 0:
                tail = (tests.stdout + tests.stderr).strip()[-1500:]
                return ImprovementOutcome(False, "tests_failed", tail)
            return ImprovementOutcome(True, "validated", "tests passed in sandbox")
        finally:
            _run(["git", "worktree", "remove", "--force", str(worktree)], self.repo_root)
            shutil.rmtree(sandbox, ignore_errors=True)

    def apply_change(self, rel_path: str, new_content: str) -> ImprovementOutcome:
        """Write the validated change into the live working tree (uncommitted)."""
        target = self._resolve_inside_repo(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
        return ImprovementOutcome(
            True, "applied", f"{rel_path} updated in working tree (review and commit)"
        )

    def _resolve_inside_repo(self, rel_path: str) -> Path:
        target = (self.repo_root / rel_path).resolve()
        if self.repo_root not in target.parents and target != self.repo_root:
            raise ValueError(f"refusing to touch path outside the repo: {rel_path}")
        return target
