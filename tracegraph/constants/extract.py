EXTRACTOR_VERSIONS: dict[str, str] = {
    "ingest": "1.0.0",
    "structure": "1.0.0",
    "resolve": "1.0.0",
    "fastapi": "1.0.0",
    "sqlalchemy": "1.0.0",
    "alembic": "1.0.0",
    "sql": "1.0.0",
    "facts": "1.0.0",
    "pytest": "1.0.0",
}

METHOD_AST = "ast"
METHOD_RESOLVE = "resolve"
METHOD_ORM = "orm"
METHOD_SQL = "sql"
METHOD_SCHEMA = "schema"

ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})
EXCEPTION_BASES = frozenset({"builtins.Exception", "builtins.BaseException", "Exception", "BaseException"})
PYDANTIC_BASES = frozenset({"pydantic.BaseModel", "pydantic.main.BaseModel", "pydantic_settings.BaseSettings"})
ABC_BASES = frozenset({"abc.ABC", "ABC"})
WRAPPER_TYPES = frozenset({"Optional", "Mapped", "Annotated", "Final", "ClassVar", "Type", "type", "Required",
                           "NotRequired"})

HOLE_PARSE_ERROR = "parse_error"
HOLE_UNTYPED_RECEIVER = "untyped_receiver"
HOLE_DYNAMIC_ATTRIBUTE = "dynamic_attribute"
HOLE_EVAL = "eval"
HOLE_DYNAMIC_IMPORT = "dynamic_import"
HOLE_DYNAMIC_SQL = "dynamic_sql"

DYNAMIC_CALL_HOLES: dict[str, str] = {
    "getattr": HOLE_DYNAMIC_ATTRIBUTE,
    "setattr": HOLE_DYNAMIC_ATTRIBUTE,
    "delattr": HOLE_DYNAMIC_ATTRIBUTE,
    "eval": HOLE_EVAL,
    "exec": HOLE_EVAL,
    "__import__": HOLE_DYNAMIC_IMPORT,
    "importlib.import_module": HOLE_DYNAMIC_IMPORT,
}
HOLE_RAW_SQL_MIGRATION = "raw_sql_migration"

SQL_TYPE_ALIASES: dict[str, str] = {"STRING": "VARCHAR", "UNICODE": "VARCHAR", "UNICODETEXT": "TEXT",
                                    "BIGINTEGER": "BIGINT", "SMALLINTEGER": "SMALLINT", "DATETIME": "TIMESTAMP"}


def normalize_sql_type(name: str | None) -> str | None:
    """
    #Feature: Schema extraction
    #Scenario: Canonical upper-case SQL type name so ORM and migration types compare equal
    #Complexity: Time O(1) - constant
    """
    if not name:
        return None
    upper = name.upper()
    return SQL_TYPE_ALIASES.get(upper, upper)
