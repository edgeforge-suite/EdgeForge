"""Fail-closed validation for operator-supplied executable staging DDL."""

from __future__ import annotations

import re
from dataclasses import dataclass


class StagingDdlValidationError(ValueError):
    """Raised when staging DDL falls outside the approved executable-input boundary."""


@dataclass(frozen=True)
class StagingDdlColumn:
    """One column from a validated staging-table definition."""

    name: str
    raw_type: str
    max_length: int | None
    precision: int | None
    scale: int | None
    required: bool
    primary_key: bool
    unique: bool


@dataclass(frozen=True)
class ValidatedStagingDdl:
    """Structured result shared by staging translation and generation."""

    table_name: str
    columns: tuple[StagingDdlColumn, ...]


@dataclass(frozen=True)
class _Token:
    value: str
    kind: str
    offset: int

    @property
    def keyword(self) -> str:
        return self.value.upper()


class _ParseFailure(ValueError):
    pass


_LENGTH_TYPES = {"BINARY", "CHAR", "VARBINARY", "VARCHAR"}
_PRECISION_TYPES = {"DECIMAL", "NUMBER", "NUMERIC"}
_UNMODIFIED_TYPES = {
    "BIGINT",
    "BLOB",
    "BOOLEAN",
    "BOOL",
    "BYTEA",
    "DATE",
    "DATETIME",
    "INT",
    "INTEGER",
    "SMALLINT",
    "TEXT",
    "TIMESTAMP",
    "UUID",
}

_SQL_TYPES_BY_DATABASE = {
    "h2": _LENGTH_TYPES | _PRECISION_TYPES | _UNMODIFIED_TYPES,
    "postgresql": {
        "BIGINT",
        "BOOLEAN",
        "BOOL",
        "BYTEA",
        "CHAR",
        "DATE",
        "DECIMAL",
        "INT",
        "INTEGER",
        "NUMERIC",
        "SMALLINT",
        "TEXT",
        "TIMESTAMP",
        "UUID",
        "VARCHAR",
    },
}

# Limits are pinned to the shipped dialect baselines: H2 2.2.x and PostgreSQL
# 16.x. The validator deliberately stays at or below each database's declared
# maximum so accepted DDL cannot fail later solely because a modifier is too large.
_TYPE_MODIFIER_LIMITS = {
    "h2": {
        "length": 1_000_000_000,
        "precision": 100_000,
    },
    "postgresql": {
        "length": 10_485_760,
        "precision": 1_000,
    },
}
_MAX_MODIFIER_DIGITS = 18

# Conservative union of SQL-standard, H2, and PostgreSQL keywords that are unsafe
# as unquoted identifiers in the shipped database profiles. The v1 boundary
# intentionally rejects more than either dialect alone rather than emitting DDL
# whose meaning changes with the selected runtime.
_RESERVED_IDENTIFIERS = {
    "ALL",
    "ALTER",
    "ANALYSE",
    "ANALYZE",
    "AND",
    "ANY",
    "ARRAY",
    "AS",
    "ASC",
    "ASYMMETRIC",
    "AUTHORIZATION",
    "BEGIN",
    "BETWEEN",
    "BOTH",
    "BY",
    "CASE",
    "CAST",
    "CHECK",
    "COLLATE",
    "COLLATION",
    "COLUMN",
    "CONCURRENTLY",
    "CONSTRAINT",
    "COPY",
    "CREATE",
    "CROSS",
    "CURRENT_CATALOG",
    "CURRENT_DATE",
    "CURRENT_PATH",
    "CURRENT_ROLE",
    "CURRENT_SCHEMA",
    "CURRENT_TIME",
    "CURRENT_TIMESTAMP",
    "CURRENT_USER",
    "DAY",
    "DEFAULT",
    "DEFERRABLE",
    "DELETE",
    "DESC",
    "DISTINCT",
    "DO",
    "DROP",
    "ELSE",
    "END",
    "EXCEPT",
    "EXISTS",
    "EXECUTE",
    "FALSE",
    "FETCH",
    "FOR",
    "FOREIGN",
    "FREEZE",
    "FROM",
    "FULL",
    "GRANT",
    "GROUP",
    "GROUPS",
    "HAVING",
    "HOUR",
    "IF",
    "ILIKE",
    "IN",
    "INDEX",
    "INITIALLY",
    "INNER",
    "INSERT",
    "INTERSECT",
    "INTERVAL",
    "INTO",
    "IS",
    "ISNULL",
    "JOIN",
    "KEY",
    "LEADING",
    "LEFT",
    "LATERAL",
    "LIKE",
    "LIMIT",
    "LOCALTIME",
    "LOCALTIMESTAMP",
    "MINUS",
    "MINUTE",
    "MONTH",
    "NATURAL",
    "NOT",
    "NOTNULL",
    "NULL",
    "OFFSET",
    "ON",
    "ONLY",
    "OR",
    "ORDER",
    "OUTER",
    "OVERLAPS",
    "OVER",
    "PARTITION",
    "PLACING",
    "PRIMARY",
    "QUALIFY",
    "RANGE",
    "REFERENCES",
    "REGEXP",
    "RETURNING",
    "RIGHT",
    "ROW",
    "ROWNUM",
    "ROWS",
    "SECOND",
    "SELECT",
    "SESSION_USER",
    "SET",
    "SIMILAR",
    "SOME",
    "SYMMETRIC",
    "SYSTEM_USER",
    "TABLE",
    "TABLESAMPLE",
    "THEN",
    "TO",
    "TOP",
    "TRAILING",
    "TRUE",
    "UESCAPE",
    "UNION",
    "UNIQUE",
    "UNKNOWN",
    "UPDATE",
    "USER",
    "USING",
    "VALUE",
    "VALUES",
    "VARIADIC",
    "VERBOSE",
    "WHEN",
    "WHERE",
    "WINDOW",
    "WITH",
    "YEAR",
    "_ROWID_",
}


def validate_staging_ddl(
    ddl_content: str,
    *,
    handoff_name: str,
    database: str,
    declared_table: str | None = None,
) -> ValidatedStagingDdl:
    """Validate staging DDL and return its table/column structure.

    Security-sensitive input must fail when it cannot be classified. Downstream
    metadata helpers reuse this structured result rather than interpreting the SQL
    with a second parser.
    """

    normalized_database = database.strip().lower()
    allowed_types = _SQL_TYPES_BY_DATABASE.get(normalized_database)
    if allowed_types is None:
        raise StagingDdlValidationError(
            f"Staging DDL for handoff '{handoff_name}' cannot be validated for unsupported "
            f"target database '{database}'."
        )
    permitted = (
        "exactly one CREATE TABLE for a dedicated handoff table with simple ASCII "
        "identifiers, scalar columns, and PRIMARY KEY/UNIQUE constraints, followed only "
        "by optional simple CREATE [UNIQUE] INDEX statements on that table; "
        f"IF NOT EXISTS is not permitted and column types must be valid for {normalized_database}"
    )
    try:
        tokens = _tokenize(ddl_content)
        statements = _split_statements(tokens)
        if not statements:
            raise _ParseFailure("empty DDL")

        validated_table: ValidatedStagingDdl | None = None
        for index, statement in enumerate(statements):
            if statement[0].keyword != "CREATE":
                raise _ParseFailure(f"{statement[0].keyword} statement")
            if len(statement) < 2:
                raise _ParseFailure("incomplete CREATE statement")
            second = statement[1].keyword
            if second == "TABLE":
                if index != 0 or validated_table is not None:
                    raise _ParseFailure("multiple or non-leading CREATE TABLE statements")
                validated_table = _parse_create_table(
                    statement,
                    allowed_types=allowed_types,
                    database=normalized_database,
                )
                continue
            if second in {"INDEX", "UNIQUE"}:
                if validated_table is None:
                    raise _ParseFailure("CREATE INDEX before CREATE TABLE")
                _parse_create_index(
                    statement,
                    table_name=validated_table.table_name,
                    columns={_identifier_key(column.name) for column in validated_table.columns},
                )
                continue
            raise _ParseFailure(f"CREATE {second} statement")

        if validated_table is None:
            raise _ParseFailure("missing CREATE TABLE statement")
        if declared_table is not None:
            _require_simple_identifier(declared_table, "declared table")
        if declared_table is not None and _identifier_key(
            validated_table.table_name
        ) != _identifier_key(declared_table):
            raise _ParseFailure(
                f"CREATE TABLE target '{validated_table.table_name}' does not match declared table "
                f"'{declared_table}'"
            )
        return validated_table
    except _ParseFailure as exc:
        raise StagingDdlValidationError(
            f"Staging DDL for handoff '{handoff_name}' is not permitted: {exc}. "
            f"Permitted v1 input is {permitted}."
        ) from exc


def _tokenize(sql: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            index = length if newline == -1 else newline + 1
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end == -1:
                raise _ParseFailure("unterminated block comment")
            if sql.find("/*", index + 2, end) != -1:
                raise _ParseFailure("nested block comment")
            index = end + 2
            continue
        if char in "(),;":
            tokens.append(_Token(char, "symbol", index))
            index += 1
            continue
        if char in {'"', "`", "["}:
            raise _ParseFailure(
                f"quoted identifier in {_statement_label(sql, index)} is outside the "
                "simple identifier boundary"
            )
        if _is_ascii_letter(char) or char == "_":
            end = index + 1
            while end < length and (
                _is_ascii_letter(sql[end]) or sql[end].isdigit() or sql[end] == "_"
            ):
                end += 1
            tokens.append(_Token(sql[index:end], "identifier", index))
            index = end
            continue
        if char in "0123456789":
            end = index + 1
            while end < length and sql[end] in "0123456789":
                end += 1
            tokens.append(_Token(sql[index:end], "number", index))
            index = end
            continue
        if char == "'":
            raise _ParseFailure(
                f"string literal in {_statement_label(sql, index)} at offset {index}"
            )
        raise _ParseFailure(
            f"unrecognised token {char!r} in {_statement_label(sql, index)} at offset {index}"
        )
    return tokens


def _statement_label(sql: str, offset: int) -> str:
    statement_prefix = sql[:offset].rsplit(";", 1)[-1]
    match = re.search(r"[A-Za-z_][A-Za-z0-9_]*", statement_prefix)
    return f"{match.group(0).upper()} statement" if match else "SQL statement"


def _is_ascii_letter(value: str) -> bool:
    return "A" <= value <= "Z" or "a" <= value <= "z"


def _split_statements(tokens: list[_Token]) -> list[list[_Token]]:
    statements: list[list[_Token]] = []
    current: list[_Token] = []
    depth = 0
    for token in tokens:
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth -= 1
            if depth < 0:
                raise _ParseFailure("unbalanced closing parenthesis")
        if token.value == ";":
            if depth != 0:
                raise _ParseFailure("statement terminator inside parentheses")
            if not current:
                raise _ParseFailure("empty SQL statement")
            statements.append(current)
            current = []
        else:
            current.append(token)
    if depth != 0:
        raise _ParseFailure("unbalanced parentheses")
    if current:
        statements.append(current)
    return statements


class _Cursor:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0

    @property
    def done(self) -> bool:
        return self.index >= len(self.tokens)

    def peek(self) -> _Token | None:
        return None if self.done else self.tokens[self.index]

    def take(self) -> _Token:
        if self.done:
            raise _ParseFailure("unexpected end of statement")
        token = self.tokens[self.index]
        self.index += 1
        return token

    def match_keyword(self, keyword: str) -> bool:
        token = self.peek()
        if token is not None and token.kind == "identifier" and token.keyword == keyword:
            self.index += 1
            return True
        return False

    def expect_keyword(self, keyword: str) -> None:
        token = self.take()
        if token.kind != "identifier" or token.keyword != keyword:
            raise _ParseFailure(f"expected {keyword}, found {token.value!r}")

    def expect_symbol(self, symbol: str) -> None:
        token = self.take()
        if token.value != symbol:
            raise _ParseFailure(f"expected {symbol!r}, found {token.value!r}")

    def expect_identifier(self, description: str) -> str:
        token = self.take()
        if token.kind != "identifier":
            raise _ParseFailure(f"expected {description}, found {token.value!r}")
        _require_simple_identifier(token.value, description)
        return token.value


def _parse_create_table(
    statement: list[_Token],
    *,
    allowed_types: set[str],
    database: str,
) -> ValidatedStagingDdl:
    cursor = _Cursor(statement)
    cursor.expect_keyword("CREATE")
    cursor.expect_keyword("TABLE")
    _reject_if_not_exists(cursor, construct="CREATE TABLE")
    table_name = cursor.expect_identifier("table name")
    cursor.expect_symbol("(")

    body = _take_parenthesized_body(cursor)
    if not cursor.done:
        raise _ParseFailure(f"unsupported CREATE TABLE construct {cursor.take().value!r}")
    elements = _split_comma_separated(body, description="CREATE TABLE element")

    columns: list[StagingDdlColumn] = []
    column_keys: set[str] = set()
    constraints: list[tuple[str, list[str]]] = []
    for element in elements:
        first = element[0].keyword
        if first in {"CONSTRAINT", "PRIMARY", "UNIQUE"}:
            constraints.append(_parse_table_constraint(element))
            continue
        column = _parse_column_definition(
            element,
            allowed_types=allowed_types,
            database=database,
        )
        key = _identifier_key(column.name)
        if key in column_keys:
            raise _ParseFailure(f"duplicate column '{column.name}'")
        column_keys.add(key)
        columns.append(column)

    if not columns:
        raise _ParseFailure("CREATE TABLE without columns")
    primary_keys: set[str] = set()
    unique_columns: set[str] = set()
    primary_key_definitions = sum(column.primary_key for column in columns)
    for constraint_kind, constraint_columns in constraints:
        unknown = [name for name in constraint_columns if _identifier_key(name) not in column_keys]
        if unknown:
            raise _ParseFailure(
                "table constraint references unknown column(s): " + ", ".join(unknown)
            )
        if constraint_kind == "PRIMARY KEY":
            primary_key_definitions += 1
        target = primary_keys if constraint_kind == "PRIMARY KEY" else unique_columns
        target.update(_identifier_key(name) for name in constraint_columns)
    if primary_key_definitions > 1:
        raise _ParseFailure("multiple PRIMARY KEY definitions")

    merged_columns = tuple(
        StagingDdlColumn(
            name=column.name,
            raw_type=column.raw_type,
            max_length=column.max_length,
            precision=column.precision,
            scale=column.scale,
            required=column.required or _identifier_key(column.name) in primary_keys,
            primary_key=column.primary_key or _identifier_key(column.name) in primary_keys,
            unique=column.unique or _identifier_key(column.name) in unique_columns,
        )
        for column in columns
    )
    return ValidatedStagingDdl(table_name=table_name, columns=merged_columns)


def _reject_if_not_exists(cursor: _Cursor, *, construct: str) -> None:
    if cursor.match_keyword("IF"):
        cursor.expect_keyword("NOT")
        cursor.expect_keyword("EXISTS")
        raise _ParseFailure(f"{construct} IF NOT EXISTS is not permitted")


def _take_parenthesized_body(cursor: _Cursor) -> list[_Token]:
    body: list[_Token] = []
    depth = 1
    while not cursor.done:
        token = cursor.take()
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth -= 1
            if depth == 0:
                return body
        body.append(token)
    raise _ParseFailure("unterminated parenthesized definition")


def _split_comma_separated(tokens: list[_Token], *, description: str) -> list[list[_Token]]:
    parts: list[list[_Token]] = []
    current: list[_Token] = []
    depth = 0
    for token in tokens:
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth -= 1
        if token.value == "," and depth == 0:
            if not current:
                raise _ParseFailure(f"empty {description}")
            parts.append(current)
            current = []
        else:
            current.append(token)
    if not current:
        raise _ParseFailure(f"empty or trailing {description}")
    parts.append(current)
    return parts


def _parse_column_definition(
    tokens: list[_Token],
    *,
    allowed_types: set[str],
    database: str,
) -> StagingDdlColumn:
    cursor = _Cursor(tokens)
    column_name = cursor.expect_identifier("column name")
    raw_type = cursor.expect_identifier("column type").upper()
    if raw_type not in allowed_types:
        raise _ParseFailure(f"column type '{raw_type}' is unsupported for the target database")
    modifiers: list[int] = []
    if cursor.peek() is not None and cursor.peek().value == "(":
        cursor.take()
        first = cursor.take()
        if first.kind != "number":
            raise _ParseFailure("type precision/length must be numeric")
        modifiers.append(_parse_modifier_value(first.value))
        if cursor.peek() is not None and cursor.peek().value == ",":
            cursor.take()
            second = cursor.take()
            if second.kind != "number":
                raise _ParseFailure("type scale must be numeric")
            modifiers.append(_parse_modifier_value(second.value))
        cursor.expect_symbol(")")
    _validate_type_modifiers(raw_type, modifiers, database=database)

    seen: set[str] = set()
    while not cursor.done:
        if cursor.match_keyword("NOT"):
            cursor.expect_keyword("NULL")
            constraint = "NOT NULL"
        elif cursor.match_keyword("NULL"):
            constraint = "NULL"
        elif cursor.match_keyword("PRIMARY"):
            cursor.expect_keyword("KEY")
            constraint = "PRIMARY KEY"
        elif cursor.match_keyword("UNIQUE"):
            constraint = "UNIQUE"
        else:
            token = cursor.take()
            raise _ParseFailure(
                f"unsupported column construct '{token.value}' on '{column_name}'"
            )
        if constraint in seen:
            raise _ParseFailure(f"duplicate {constraint} on column '{column_name}'")
        seen.add(constraint)
    if "NULL" in seen and "NOT NULL" in seen:
        raise _ParseFailure(f"conflicting nullability on column '{column_name}'")
    max_length = modifiers[0] if raw_type in _LENGTH_TYPES and modifiers else None
    precision = modifiers[0] if raw_type in _PRECISION_TYPES and modifiers else None
    scale = modifiers[1] if len(modifiers) == 2 else None
    return StagingDdlColumn(
        name=column_name,
        raw_type=raw_type,
        max_length=max_length,
        precision=precision,
        scale=scale,
        required="NOT NULL" in seen or "PRIMARY KEY" in seen,
        primary_key="PRIMARY KEY" in seen,
        unique="UNIQUE" in seen,
    )


def _parse_table_constraint(tokens: list[_Token]) -> tuple[str, list[str]]:
    cursor = _Cursor(tokens)
    if cursor.match_keyword("CONSTRAINT"):
        cursor.expect_identifier("constraint name")
    if cursor.match_keyword("PRIMARY"):
        cursor.expect_keyword("KEY")
        constraint_kind = "PRIMARY KEY"
    elif cursor.match_keyword("UNIQUE"):
        constraint_kind = "UNIQUE"
    else:
        token = cursor.take()
        raise _ParseFailure(f"unsupported table constraint '{token.value}'")
    cursor.expect_symbol("(")
    body = _take_parenthesized_body(cursor)
    if not cursor.done:
        raise _ParseFailure(f"unsupported table constraint construct '{cursor.take().value}'")
    columns = _split_comma_separated(body, description="constraint column")
    names: list[str] = []
    for column_tokens in columns:
        column_cursor = _Cursor(column_tokens)
        names.append(column_cursor.expect_identifier("constraint column"))
        if not column_cursor.done:
            raise _ParseFailure("constraint columns must be plain identifiers")
    return constraint_kind, names


def _parse_create_index(
    statement: list[_Token],
    *,
    table_name: str,
    columns: set[str],
) -> None:
    cursor = _Cursor(statement)
    cursor.expect_keyword("CREATE")
    cursor.match_keyword("UNIQUE")
    cursor.expect_keyword("INDEX")
    _reject_if_not_exists(cursor, construct="CREATE INDEX")
    cursor.expect_identifier("index name")
    cursor.expect_keyword("ON")
    target_table = cursor.expect_identifier("index table")
    if _identifier_key(target_table) != _identifier_key(table_name):
        raise _ParseFailure(
            f"CREATE INDEX target '{target_table}' does not match handoff table '{table_name}'"
        )
    cursor.expect_symbol("(")
    body = _take_parenthesized_body(cursor)
    if not cursor.done:
        raise _ParseFailure(f"unsupported CREATE INDEX construct '{cursor.take().value}'")

    index_columns = _split_comma_separated(body, description="index column")
    for column_tokens in index_columns:
        column_cursor = _Cursor(column_tokens)
        column_name = column_cursor.expect_identifier("index column")
        if _identifier_key(column_name) not in columns:
            raise _ParseFailure(f"CREATE INDEX references unknown column '{column_name}'")
        if not column_cursor.done and not (
            column_cursor.match_keyword("ASC") or column_cursor.match_keyword("DESC")
        ):
            raise _ParseFailure("index columns must be plain identifiers with optional ASC/DESC")
        if not column_cursor.done:
            raise _ParseFailure("unsupported CREATE INDEX column construct")


def _identifier_key(value: str) -> str:
    return value.lower()


def _require_simple_identifier(value: str, description: str) -> None:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
        raise _ParseFailure(f"{description} '{value}' is outside the ASCII identifier boundary")
    if value.upper() in _RESERVED_IDENTIFIERS:
        raise _ParseFailure(f"reserved word '{value}' cannot be used as {description}")


def _parse_modifier_value(value: str) -> int:
    normalized = value.lstrip("0") or "0"
    if len(normalized) > _MAX_MODIFIER_DIGITS:
        raise _ParseFailure("type modifier has too many digits to validate safely")
    return int(normalized)


def _validate_type_modifiers(
    raw_type: str,
    modifiers: list[int],
    *,
    database: str,
) -> None:
    if raw_type in _UNMODIFIED_TYPES:
        if modifiers:
            raise _ParseFailure(f"column type '{raw_type}' does not accept modifiers")
        return
    if raw_type in _LENGTH_TYPES:
        if len(modifiers) > 1:
            raise _ParseFailure(f"column type '{raw_type}' accepts at most one length")
        if modifiers and modifiers[0] <= 0:
            raise _ParseFailure(f"column type '{raw_type}' length must be positive")
        maximum = _TYPE_MODIFIER_LIMITS[database]["length"]
        if modifiers and modifiers[0] > maximum:
            raise _ParseFailure(
                f"column type '{raw_type}' length {modifiers[0]} exceeds "
                f"{database} maximum {maximum}"
            )
        return
    if len(modifiers) > 2:
        raise _ParseFailure(f"column type '{raw_type}' accepts precision and optional scale")
    if not modifiers:
        return
    precision = modifiers[0]
    scale = modifiers[1] if len(modifiers) == 2 else 0
    if precision <= 0:
        raise _ParseFailure(f"column type '{raw_type}' precision must be positive")
    maximum = _TYPE_MODIFIER_LIMITS[database]["precision"]
    if precision > maximum:
        raise _ParseFailure(
            f"column type '{raw_type}' precision {precision} exceeds "
            f"{database} maximum {maximum}"
        )
    if scale < 0 or scale > precision:
        raise _ParseFailure(
            f"column type '{raw_type}' scale must be between zero and precision"
        )
