from pathlib import Path

SQL_ROOT = Path(__file__).resolve().parents[2] / "sql"
FUNCTIONS_ROOT = SQL_ROOT / "functions"


def resolve_sql_file(relative_path: str) -> Path:
    """
    #Feature: Migrations
    #Scenario: Resolve a path under sql/functions and refuse anything outside it
    #Complexity: Time O(1) - constant

    Args:
        relative_path: Path relative to sql/functions, e.g. "graph/tg_node_commit.sql".

    Returns:
        Absolute path of the SQL file.

    Raises:
        ValueError: When the path is missing, escapes sql/functions or does not exist.
    """
    if not relative_path:
        raise ValueError("[resolve_sql_file] 'relative_path' is required and must be non-empty.")
    path = (FUNCTIONS_ROOT / relative_path).resolve()
    if FUNCTIONS_ROOT not in path.parents:
        raise ValueError(f"[resolve_sql_file] Path {relative_path!r} escapes sql/functions. Fix: use a relative path.")
    if not path.is_file():
        raise ValueError(f"[resolve_sql_file] SQL file {path} does not exist. Fix: create it or correct the name.")
    return path


def read_sql_file(relative_path: str) -> str:
    """
    #Feature: Migrations
    #Scenario: Load the body of one stored-function file
    #Complexity: Time O(n) - linear in file size

    Args:
        relative_path: Path relative to sql/functions.

    Returns:
        SQL text.

    Raises:
        ValueError: When the file cannot be resolved.
    """
    try:
        return resolve_sql_file(relative_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"[read_sql_file] Failed to read {relative_path!r}: {exc}.") from exc


def function_name_of(relative_path: str) -> str:
    """
    #Feature: Migrations
    #Scenario: Derive the SQL function name from its file name (one function per file)
    #Complexity: Time O(1) - constant

    Args:
        relative_path: Path relative to sql/functions.

    Returns:
        The function name, i.e. the file stem.

    Raises:
        ValueError: When the path is missing or not a .sql file.
    """
    if not relative_path:
        raise ValueError("[function_name_of] 'relative_path' is required and must be non-empty.")
    path = Path(relative_path)
    if path.suffix != ".sql":
        raise ValueError(f"[function_name_of] {relative_path!r} is not a .sql file. Fix: name files <function>.sql.")
    return path.stem
