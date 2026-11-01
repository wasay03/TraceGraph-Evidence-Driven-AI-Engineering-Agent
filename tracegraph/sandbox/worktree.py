import logging
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from tracegraph.constants.workspace import GIT_TIMEOUT_SECONDS, WORKTREE_REF
from tracegraph.errors import Errors
from tracegraph.interfaces.workspace import IWorkspace

logger = logging.getLogger(__name__)


def _git(path: Path, *args: str) -> str:
    """
    #Feature: Source workspace
    #Scenario: Run a fixed git command template in a repository; never through a shell
    #Complexity: Time O(1) - one subprocess

    Raises:
        Errors.HTTP.BadRequest: When git fails (not a repo, unknown ref).
    """
    try:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                                timeout=GIT_TIMEOUT_SECONDS, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        stderr = getattr(exc, "stderr", "") or str(exc)
        raise Errors.HTTP.BadRequest(f"git {' '.join(args[:2])} failed in {path}: {stderr.strip()}") from exc


class GitWorkspace(IWorkspace):
    """
    #Feature: Source workspace
    #Scenario: Local git repositories; commits are materialised with git archive into a temp dir
    #Complexity: Time O(f) per checkout - linear in repository size
    """

    def __init__(self, workspace_dir: str) -> None:
        """
        #Feature: Source workspace
        #Scenario: Bind to the directory that holds temporary checkouts
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When workspace_dir is empty.
        """
        if not workspace_dir:
            raise ValueError("[GitWorkspace.__init__] 'workspace_dir' is required.")
        self._root = Path(workspace_dir)

    def local_path(self, url: str) -> Path:
        """
        #Feature: Source workspace
        #Scenario: Accept file:// URLs and absolute paths to existing directories only
        #Complexity: Time O(1) - constant

        Raises:
            Errors.HTTP.BadRequest: When the URL is remote, relative or not a directory.
        """
        if not url:
            raise ValueError("[GitWorkspace.local_path] 'url' is required.")
        parsed = urlparse(url)
        raw = parsed.path if parsed.scheme == "file" else url
        if parsed.scheme not in ("", "file") or not Path(raw).is_absolute():
            raise Errors.HTTP.BadRequest(f"Only local repositories are supported (file:// or absolute path); got {url!r}.")
        path = Path(raw).resolve()
        if not path.is_dir():
            raise Errors.HTTP.BadRequest(f"Repository path {path} does not exist or is not a directory.")
        return path

    def resolve_ref(self, path: Path, ref: str) -> str:
        """
        #Feature: Source workspace
        #Scenario: WORKTREE indexes files in place (stamped with HEAD when available); other refs resolve via git
        #Complexity: Time O(1) - one git call
        """
        if ref == WORKTREE_REF:
            is_git = (path / ".git").exists()
            return f"{WORKTREE_REF}@{_git(path, 'rev-parse', 'HEAD') if is_git else 'nogit'}"
        return _git(path, "rev-parse", "--verify", f"{ref}^{{commit}}")

    @contextmanager
    def checkout(self, path: Path, commit_sha: str) -> Iterator[Path]:
        """
        #Feature: Source workspace
        #Scenario: Yield the working tree for WORKTREE snapshots, otherwise an extracted git archive
        #Complexity: Time O(f) - linear in repository size
        """
        if commit_sha.startswith(WORKTREE_REF):
            yield path
            return
        self._root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._root, prefix="tg-") as tmp:
            archive = Path(tmp) / "src.tar"
            _git(path, "archive", "--format=tar", f"--output={archive}", commit_sha)
            with tarfile.open(archive) as tar:
                tar.extractall(Path(tmp) / "src", filter="data")
            logger.info("Checked out commit", extra={"commit": commit_sha, "dir": tmp})
            yield Path(tmp) / "src"
