import logging
from dataclasses import dataclass
from pathlib import Path

from tracegraph.constants.workspace import EXCLUDED_DIRS, MAX_SOURCE_FILE_BYTES, SOURCE_ROOT_CANDIDATES
from tracegraph.utilities.ids import content_hash

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SourceFile:
    """
    #Feature: Snapshot pass
    #Scenario: One Python file of the checked-out commit with its module name and content hash
    #Complexity: Time O(1) - constant
    """

    path: str
    qname: str
    text: str
    sha: str
    is_test: bool
    is_package: bool


def _is_test_path(rel: Path) -> bool:
    """
    #Feature: Snapshot pass
    #Scenario: pytest-style test file detection
    #Complexity: Time O(d) - linear in path depth
    """
    name = rel.name
    return (any(p in ("tests", "test") for p in rel.parts[:-1]) or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def _module_qname(rel: Path, source_root: Path | None) -> str:
    """
    #Feature: Snapshot pass
    #Scenario: Dotted module name; files under a src/ layout are named relative to src/
    #Complexity: Time O(d) - linear in path depth
    """
    if source_root is not None and rel.parts[0] == source_root.name:
        rel = rel.relative_to(source_root.name)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or rel.stem


def _iter_python_files(root: Path) -> list[Path]:
    """
    #Feature: Snapshot pass
    #Scenario: Sorted .py files, skipping virtualenvs, caches and VCS directories
    #Complexity: Time O(f) - linear in files
    """
    files = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if path.is_file() and path.stat().st_size <= MAX_SOURCE_FILE_BYTES:
            files.append(path)
    return sorted(files)


def discover_sources(root: Path) -> list[SourceFile]:
    """
    #Feature: Snapshot pass
    #Scenario: Hash every Python file of the checkout (PRD 5.1 step 1); order is deterministic
    #Complexity: Time O(b) - linear in bytes read

    Args:
        root: Directory holding the checked-out commit.

    Returns:
        SourceFile list sorted by path.

    Raises:
        ValueError: When root is not a directory.
    """
    if root is None or not root.is_dir():
        raise ValueError(f"[discover_sources] Root {root} is not a directory. Fix: pass the checkout directory.")
    src = next((root / c for c in SOURCE_ROOT_CANDIDATES if (root / c).is_dir()), None)
    out = []
    for path in _iter_python_files(root):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8", errors="replace")
        out.append(SourceFile(path=rel.as_posix(), qname=_module_qname(rel, src), text=text, sha=content_hash(text),
                              is_test=_is_test_path(rel), is_package=rel.name == "__init__.py"))
    logger.info("Discovered sources", extra={"files": len(out), "root": str(root)})
    return out
