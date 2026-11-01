WORKTREE_REF = "WORKTREE"
GIT_TIMEOUT_SECONDS = 60

EXCLUDED_DIRS = frozenset(
    {".git", ".hg", ".venv", "venv", "env", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
     ".ruff_cache", ".tox", "build", "dist", "site-packages"}
)
SOURCE_ROOT_CANDIDATES = ("src",)
MAX_SOURCE_FILE_BYTES = 2_000_000
