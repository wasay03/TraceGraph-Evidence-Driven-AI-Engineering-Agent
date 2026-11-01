import logging
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tracegraph.constants.agent import CHECK_TIMEOUT_SECONDS, TEST_TIMEOUT_SECONDS
from tracegraph.errors import Errors

logger = logging.getLogger(__name__)

_DIFF_FILE = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)", re.MULTILINE)
_HUNK = re.compile(r"^\+\+\+ b/(\S+)|^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
_PYTEST_SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors|skipped)")


@dataclass(slots=True)
class CommandResult:
    """
    #Feature: Sandbox
    #Scenario: Outcome of one fixed command template
    #Complexity: Time O(1) - constant
    """

    ok: bool
    returncode: int
    output: str


def _run(cmd: list[str], cwd: Path, timeout: int) -> CommandResult:
    """
    #Feature: Sandbox
    #Scenario: Run a fixed argv (never a shell) with a timeout; output is tail-truncated
    #Complexity: Time O(1) - one subprocess
    """
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return CommandResult(proc.returncode == 0, proc.returncode, (proc.stdout + proc.stderr)[-8000:])
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, -1, f"timeout after {timeout}s: {(exc.stdout or '')[-2000:]}")
    except FileNotFoundError as exc:
        return CommandResult(False, -1, f"command unavailable: {exc}")


def safe_relative(path: str) -> str:
    """
    #Feature: Sandbox
    #Scenario: Normalise a repo-relative path and refuse absolute paths or parent traversal
    #Complexity: Time O(p) - path length

    Raises:
        Errors.HTTP.BadRequest: When the path escapes the worktree.
    """
    pure = PurePosixPath(path)
    if not path or pure.is_absolute() or ".." in pure.parts:
        raise Errors.HTTP.BadRequest(f"Path {path!r} must be relative to the repository root.")
    return str(pure)


class SandboxWorkspace:
    """
    #Feature: Sandbox (PRD 11.1)
    #Scenario: One detached git worktree per run at the snapshot commit; only fixed command templates execute
    #Complexity: Time O(1) per operation excluding subprocess work

    Network and resource isolation (containers) are not provided by this class.
    """

    def __init__(self, repo_path: Path, root: Path, python: str | None = None) -> None:
        """
        #Feature: Sandbox
        #Scenario: Bind to a source repository and an existing worktree root
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a path is missing.
        """
        if repo_path is None or root is None:
            raise ValueError("[SandboxWorkspace.__init__] 'repo_path' and 'root' are required.")
        self.repo_path, self.root, self.python = repo_path, root, python or sys.executable

    @classmethod
    def create(cls, repo_path: Path, base_dir: Path, commit: str, run_id: int, python: str | None = None
               ) -> "SandboxWorkspace":
        """
        #Feature: Sandbox
        #Scenario: git worktree add --detach at the snapshot commit (WORKTREE snapshots use HEAD)
        #Complexity: Time O(f) - checkout size

        Raises:
            Errors.HTTP.BadRequest: When git cannot create the worktree.
        """
        base_dir.mkdir(parents=True, exist_ok=True)
        root = base_dir / f"run-{run_id}-{uuid.uuid4().hex[:6]}"
        ref = "HEAD" if commit.startswith("WORKTREE") else commit
        result = _run(["git", "-C", str(repo_path), "worktree", "add", "--detach", str(root), ref], repo_path, 120)
        if not result.ok:
            raise Errors.HTTP.BadRequest(f"Cannot create sandbox worktree: {result.output}")
        logger.info("Sandbox created", extra={"run_id": run_id, "worktree": str(root), "commit": ref})
        return cls(repo_path, root, python)

    def read_file(self, path: str, start: int = 1, end: int | None = None) -> str:
        """
        #Feature: Sandbox
        #Scenario: Numbered lines of a file in the worktree
        #Complexity: Time O(l) - lines read

        Raises:
            Errors.HTTP.NotFound: When the file does not exist.
        """
        target = self.root / safe_relative(path)
        if not target.is_file():
            raise Errors.HTTP.NotFound(f"{path} does not exist in the sandbox.")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        stop = min(end or len(lines), len(lines))
        return "\n".join(f"{i:5} {lines[i - 1]}" for i in range(max(start, 1), stop + 1))

    def list_dir(self, path: str = ".") -> list[str]:
        """
        #Feature: Sandbox
        #Scenario: Entries of a directory (directories end with /), hidden entries skipped
        #Complexity: Time O(d) - directory size
        """
        target = self.root / safe_relative(path) if path not in ("", ".") else self.root
        if not target.is_dir():
            raise Errors.HTTP.NotFound(f"{path} is not a directory in the sandbox.")
        return sorted(f"{p.name}/" if p.is_dir() else p.name for p in target.iterdir() if not p.name.startswith("."))

    def grep(self, pattern: str, max_lines: int = 200) -> str:
        """
        #Feature: Sandbox
        #Scenario: Fixed-string search over Python files (baseline tool)
        #Complexity: Time O(b) - bytes scanned
        """
        result = _run(["grep", "-rnF", "--include=*.py", "--", pattern, "."], self.root, CHECK_TIMEOUT_SECONDS)
        return "\n".join(result.output.splitlines()[:max_lines])

    @staticmethod
    def patch_files(diff: str) -> list[str]:
        """
        #Feature: Sandbox
        #Scenario: Files a unified diff touches (excluding /dev/null)
        #Complexity: Time O(d) - diff size
        """
        return sorted({safe_relative(m) for m in _DIFF_FILE.findall(diff) if m != "/dev/null"})

    def apply_patch(self, diff: str) -> tuple[str, list[str]]:
        """
        #Feature: Sandbox
        #Scenario: git apply --check then apply; returns (patch id, files)
        #Complexity: Time O(d) - diff size

        Raises:
            Errors.HTTP.BadRequest: When the patch does not apply.
        """
        files = self.patch_files(diff)
        patch_id = f"p{uuid.uuid4().hex[:8]}"
        store = self.root / ".tg-patches"
        store.mkdir(exist_ok=True)
        (store / f"{patch_id}.diff").write_text(diff if diff.endswith("\n") else diff + "\n", encoding="utf-8")
        args = ["git", "apply", "--recount", "--whitespace=nowarn"]
        check = _run([*args, "--check", str(store / f"{patch_id}.diff")], self.root, CHECK_TIMEOUT_SECONDS)
        if not check.ok:
            raise Errors.HTTP.BadRequest(f"Patch does not apply: {check.output.strip()}")
        _run([*args, str(store / f"{patch_id}.diff")], self.root, CHECK_TIMEOUT_SECONDS)
        return patch_id, files

    def revert_patch(self, patch_id: str) -> None:
        """
        #Feature: Sandbox
        #Scenario: Reverse a previously applied patch
        #Complexity: Time O(d) - diff size

        Raises:
            Errors.HTTP.BadRequest: When the patch is unknown or cannot be reversed.
        """
        diff = self.root / ".tg-patches" / f"{safe_relative(patch_id)}.diff"
        if not diff.is_file():
            raise Errors.HTTP.BadRequest(f"Unknown patch {patch_id}.")
        result = _run(["git", "apply", "-R", "--recount", str(diff)], self.root, CHECK_TIMEOUT_SECONDS)
        if not result.ok:
            raise Errors.HTTP.BadRequest(f"Cannot revert {patch_id}: {result.output.strip()}")

    def changed_lines(self) -> dict[str, set[int]]:
        """
        #Feature: Plan conformance
        #Scenario: New-side line numbers changed per file versus the checkout commit (untracked files included)
        #Complexity: Time O(d) - diff size
        """
        _run(["git", "add", "-A", "--intent-to-add", "."], self.root, CHECK_TIMEOUT_SECONDS)
        diff = _run(["git", "diff", "-U0", "--", ".", ":(exclude).tg-patches"], self.root, CHECK_TIMEOUT_SECONDS).output
        changed, current = {}, None
        for path, start, count in _HUNK.findall(diff):
            if path:
                current = path
            elif current is not None:
                n = int(count) if count else 1
                changed.setdefault(current, set()).update(range(int(start), int(start) + max(n, 1)))
        return changed

    def run_tests(self, node_ids: list[str]) -> dict[str, object]:
        """
        #Feature: Verification ladder (rungs 5-6)
        #Scenario: pytest on given node ids (all tests when empty); counts parsed from the summary line
        #Complexity: Time O(test runtime)
        """
        ids = [safe_relative(n.split("::")[0]) + ("::" + n.split("::", 1)[1] if "::" in n else "") for n in node_ids]
        result = _run([self.python, "-m", "pytest", "-q", "-p", "no:cacheprovider", *ids], self.root,
                      TEST_TIMEOUT_SECONDS)
        counts = {k.rstrip("s"): int(v) for v, k in _PYTEST_SUMMARY.findall(result.output.splitlines()[-1]
                                                                             if result.output else "")}
        return {"ok": result.ok, "returncode": result.returncode, "counts": counts, "output": result.output[-4000:]}

    def run_checks(self, files: list[str]) -> dict[str, object]:
        """
        #Feature: Verification ladder (rungs 2-3)
        #Scenario: ruff check on changed files when ruff is installed; otherwise reported unavailable
        #Complexity: Time O(f) - files checked
        """
        if shutil.which("ruff") is None or not files:
            return {"ok": True, "status": "unavailable" if files else "skipped", "output": ""}
        result = _run(["ruff", "check", "--quiet", *[safe_relative(f) for f in files]], self.root,
                      CHECK_TIMEOUT_SECONDS)
        return {"ok": result.ok, "status": "checked", "output": result.output}

    def cleanup(self) -> None:
        """
        #Feature: Sandbox
        #Scenario: Remove the worktree
        #Complexity: Time O(f) - files removed
        """
        _run(["git", "-C", str(self.repo_path), "worktree", "remove", "--force", str(self.root)], self.repo_path, 120)


def read_at_commit(repo_path: Path, commit: str, path: str) -> list[str]:
    """
    #Feature: Sandbox
    #Scenario: File lines as of the snapshot commit (working tree for WORKTREE snapshots)
    #Complexity: Time O(s) - file size

    Raises:
        Errors.HTTP.NotFound: When the file is absent at that commit.
    """
    rel = safe_relative(path)
    if commit.startswith("WORKTREE"):
        target = repo_path / rel
        if not target.is_file():
            raise Errors.HTTP.NotFound(f"{path} not found in the working tree.")
        return target.read_text(encoding="utf-8", errors="replace").splitlines()
    result = _run(["git", "show", f"{commit}:{rel}"], repo_path, CHECK_TIMEOUT_SECONDS)
    if not result.ok:
        raise Errors.HTTP.NotFound(f"{path} not found at {commit[:12]}.")
    return result.output.splitlines()
