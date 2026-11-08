"""Validation helpers for file-contract layout specs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

FILE_CONTRACT_TYPES = frozenset({"file-fixed-width", "file-csv"})
SUPPORTED_JAVA_FILE_ENCODINGS = frozenset(
    {
        "ascii",
        "iso-8859-1",
        "us-ascii",
        "utf-8",
        "utf-16",
        "utf-16be",
        "utf-16le",
        "windows-1252",
    }
)
SUPPORTED_FILE_FIELD_TYPES = frozenset(
    {
        "string",
        "char",
        "text",
        "integer",
        "int",
        "long",
        "decimal",
        "number",
        "bigdecimal",
        "date",
        "localdate",
        "datetime",
        "date-time",
        "timestamp",
        "localdatetime",
        "boolean",
        "bool",
    }
)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys in layout contracts."""


def _construct_mapping_without_duplicate_keys(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"File layout declares duplicate key '{key}'.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_without_duplicate_keys,
)


@dataclass(frozen=True)
class FileLayoutField:
    name: str
    required: bool
    length: int | None = None
    position: int | None = None
    column: int | None = None
    type: str | None = None
    format: str | None = None
    decimal_format: str | None = None
    value_source: str | None = None
    type_coercion: str | None = None


@dataclass(frozen=True)
class FileLayoutIndicator:
    value: str
    position: int | None = None
    length: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class FileLayoutRecordType:
    name: str
    fields: tuple[FileLayoutField, ...]
    indicator: FileLayoutIndicator | None = None
    expected_length: int = 0


@dataclass(frozen=True)
class FileLayoutSpec:
    format: str
    fields: tuple[FileLayoutField, ...]
    is_flat_fixed_width: bool = False
    record_types: tuple[FileLayoutRecordType, ...] = ()
    encoding: str | None = None
    delimiter: str | None = None
    quote_char: str | None = None
    escape_char: str | None = None
    has_header_row: bool | None = None
    line_separator: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        """Return a JSON-serializable layout payload for generation metadata."""

        return asdict(self)


def load_file_layout_spec(layout_path: Path, *, contract_type: str) -> FileLayoutSpec:
    """Load and validate a CSV or fixed-width file layout spec."""

    payload = yaml.load(
        layout_path.read_text(encoding="utf-8"),
        Loader=_UniqueKeySafeLoader,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"File layout '{layout_path}' must contain a YAML mapping.")
    return validate_file_layout_spec(payload, layout_name=str(layout_path), contract_type=contract_type)


def validate_file_layout_spec(
    payload: dict[str, Any],
    *,
    layout_name: str,
    contract_type: str,
) -> FileLayoutSpec:
    """Validate a layout payload and return the data-record field contract."""

    if contract_type == "file-fixed-width":
        return _validate_fixed_width_layout(payload, layout_name=layout_name)
    if contract_type == "file-csv":
        return _validate_csv_layout(payload, layout_name=layout_name)
    raise ValueError(f"Unsupported file contract type '{contract_type}' for layout '{layout_name}'.")


def _validate_fixed_width_layout(payload: dict[str, Any], *, layout_name: str) -> FileLayoutSpec:
    if "fields" in payload:
        if payload.get("format") is not None or payload.get("record_types") is not None:
            raise ValueError(
                f"Fixed-width layout '{layout_name}' must not mix legacy flat fields[] "
                "with top-level format or record_types."
            )
        fields_payload = _require_list(payload.get("fields"), layout_name, "fields")
        _ensure_unique_field_names(
            fields_payload,
            layout_name=layout_name,
            label="fields",
        )
        parsed_fields = tuple(
            _fixed_width_field(
                field,
                layout_name=layout_name,
                record_type="data",
                require_length=True,
            )
            for field in fields_payload
        )
        fields: list[FileLayoutField] = []
        next_position = 1
        for field in parsed_fields:
            fields.append(
                FileLayoutField(
                    name=field.name,
                    required=field.required,
                    length=field.length,
                    position=next_position,
                    type=field.type,
                    format=field.format,
                    decimal_format=field.decimal_format,
                    value_source=field.value_source,
                    type_coercion=field.type_coercion,
                )
            )
            next_position += field.length or 0
        data_record = FileLayoutRecordType(
            name="data",
            fields=tuple(fields),
            expected_length=sum(field.length or 0 for field in fields),
        )
        return FileLayoutSpec(
            format="fixed-width",
            fields=tuple(fields),
            is_flat_fixed_width=True,
            record_types=(data_record,),
            encoding=_validated_encoding(payload.get("encoding"), layout_name),
        )

    if payload.get("format") != "fixed-width":
        raise ValueError(
            f"Fixed-width layout '{layout_name}' must declare format: fixed-width "
            "or use the legacy flat fields[] layout."
        )
    record_types = payload.get("record_types")
    if not isinstance(record_types, dict) or not record_types:
        raise ValueError(f"Fixed-width layout '{layout_name}' requires record_types.")
    if "data" in record_types and "detail" in record_types:
        raise ValueError(
            f"Fixed-width layout '{layout_name}' must declare either record_types.data "
            "or record_types.detail, not both."
        )

    data_fields: tuple[FileLayoutField, ...] | None = None
    parsed_record_types: list[FileLayoutRecordType] = []
    for record_type, record_payload in record_types.items():
        if not isinstance(record_type, str) or not record_type.strip():
            raise ValueError(f"Fixed-width layout '{layout_name}' has an empty record type name.")
        if not isinstance(record_payload, dict):
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record type '{record_type}' must be a mapping."
            )
        parsed_record_type = _validate_fixed_width_record_type(
            record_payload,
            layout_name=layout_name,
            record_type=record_type,
        )
        parsed_record_types.append(parsed_record_type)
        if record_type in {"data", "detail"}:
            data_fields = parsed_record_type.fields

    _validate_fixed_width_record_type_indicators(
        parsed_record_types,
        layout_name=layout_name,
    )
    if data_fields is None:
        raise ValueError(
            f"Fixed-width layout '{layout_name}' requires record_types.data.fields "
            "or record_types.detail.fields."
        )
    return FileLayoutSpec(
        format="fixed-width",
        fields=data_fields,
        is_flat_fixed_width=False,
        record_types=tuple(parsed_record_types),
        encoding=_validated_encoding(payload.get("encoding"), layout_name),
    )


def _validate_fixed_width_record_type(
    payload: dict[str, Any],
    *,
    layout_name: str,
    record_type: str,
) -> FileLayoutRecordType:
    indicator = payload.get("indicator")
    occupied: list[tuple[int, int, str]] = []
    implicit_start = 1
    parsed_indicator: FileLayoutIndicator | None = None
    if indicator is not None:
        if not isinstance(indicator, dict):
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record type '{record_type}' indicator must be a mapping."
            )
        indicator_position = _positive_int(
            indicator.get("position"),
            layout_name,
            f"record_types.{record_type}.indicator.position",
        )
        indicator_length = _positive_int(
            indicator.get("length"),
            layout_name,
            f"record_types.{record_type}.indicator.length",
        )
        indicator_value = indicator.get("value")
        if indicator_value is None:
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record type '{record_type}' indicator requires value."
            )
        indicator_value = str(indicator_value)
        if len(indicator_value) != indicator_length:
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record type '{record_type}' indicator value "
                f"length must match indicator.length {indicator_length}."
            )
        parsed_indicator = FileLayoutIndicator(
            position=indicator_position,
            length=indicator_length,
            value=indicator_value,
        )
        occupied.append(
            (
                indicator_position,
                indicator_position + indicator_length - 1,
                f"{record_type}.indicator",
            )
        )
        implicit_start = indicator_position + indicator_length

    fields_payload = _require_list(
        payload.get("fields"),
        layout_name,
        f"record_types.{record_type}.fields",
    )
    _ensure_unique_field_names(
        fields_payload,
        layout_name=layout_name,
        label=f"record_types.{record_type}.fields",
    )
    explicit_flags = [
        isinstance(field, dict) and field.get("position") is not None
        for field in fields_payload
    ]
    if any(explicit_flags) and not all(explicit_flags):
        raise ValueError(
            f"Fixed-width layout '{layout_name}' record type '{record_type}' must not mix "
            "explicit and implicit field positions."
        )

    fields: list[FileLayoutField] = []
    next_position = implicit_start
    explicit = all(explicit_flags) if explicit_flags else False
    for field_payload in fields_payload:
        field = _fixed_width_field(
            field_payload,
            layout_name=layout_name,
            record_type=record_type,
            require_length=True,
        )
        position = field.position if explicit else next_position
        assert position is not None
        end = position + (field.length or 0) - 1
        occupied.append((position, end, f"{record_type}.{field.name}"))
        fields.append(
            FileLayoutField(
                name=field.name,
                required=field.required,
                length=field.length,
                position=position,
                type=field.type,
                format=field.format,
                decimal_format=field.decimal_format,
                value_source=field.value_source,
                type_coercion=field.type_coercion,
            )
        )
        next_position = end + 1

    _validate_contiguous_spans(occupied, layout_name=layout_name, record_type=record_type)
    expected_length = max(end for _start, end, _label in occupied)
    return FileLayoutRecordType(
        name=record_type,
        fields=tuple(fields),
        indicator=parsed_indicator,
        expected_length=expected_length,
    )


def _validate_fixed_width_record_type_indicators(
    record_types: list[FileLayoutRecordType],
    *,
    layout_name: str,
) -> None:
    indicator_record_types = [
        record_type for record_type in record_types if record_type.indicator is not None
    ]
    if len(record_types) > 1 and not indicator_record_types:
        raise ValueError(
            f"Fixed-width layout '{layout_name}' with multiple record_types requires "
            "indicators so generated parser routing is deterministic."
        )
    if indicator_record_types and len(indicator_record_types) != len(record_types):
        raise ValueError(
            f"Fixed-width layout '{layout_name}' must declare indicators for every "
            "record type when any record type uses an indicator."
        )

    seen: dict[tuple[int, int, str], str] = {}
    for record_type in indicator_record_types:
        assert record_type.indicator is not None
        key = (
            record_type.indicator.position,
            record_type.indicator.length,
            record_type.indicator.value,
        )
        previous = seen.get(key)
        if previous is not None:
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record types '{previous}' and "
                f"'{record_type.name}' declare duplicate indicators."
            )
        seen[key] = record_type.name


def _fixed_width_field(
    payload: Any,
    *,
    layout_name: str,
    record_type: str,
    require_length: bool,
) -> FileLayoutField:
    if not isinstance(payload, dict):
        raise ValueError(
            f"Fixed-width layout '{layout_name}' record type '{record_type}' fields must be mappings."
        )
    name = _required_name(payload.get("name"), layout_name, f"record_types.{record_type}.fields.name")
    if require_length or payload.get("length") is not None:
        length = _positive_int(payload.get("length"), layout_name, f"{record_type}.{name}.length")
    else:
        length = None
    position = payload.get("position")
    if position is not None:
        position = _positive_int(position, layout_name, f"{record_type}.{name}.position")
    return FileLayoutField(
        name=name,
        required=bool(payload.get("required", False)),
        length=length,
        position=position,
        type=_normalize_field_type(
            payload.get("type"),
            layout_name=layout_name,
            label=f"{record_type}.{name}.type",
        ),
        format=str(payload["format"]) if payload.get("format") is not None else None,
        decimal_format=(
            str(payload["decimal_format"])
            if payload.get("decimal_format") is not None
            else None
        ),
        value_source=(
            str(payload["value_source"])
            if payload.get("value_source") is not None
            else None
        ),
        type_coercion=(
            str(payload["type_coercion"])
            if payload.get("type_coercion") is not None
            else None
        ),
    )


def _validate_contiguous_spans(
    spans: list[tuple[int, int, str]],
    *,
    layout_name: str,
    record_type: str,
) -> None:
    ordered = sorted(spans, key=lambda item: item[0])
    expected_start: int = 1
    previous_label: str | None = None
    for start, end, label in ordered:
        if end < start:
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record type '{record_type}' has invalid span for {label}."
            )
        if start <= expected_start - 1:
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record type '{record_type}' has overlapping "
                f"positions near {label}."
            )
        if start > expected_start:
            if previous_label is None:
                raise ValueError(
                    f"Fixed-width layout '{layout_name}' record type '{record_type}' has a leading "
                    f"gap before {label}; add an explicit filler/padding field."
                )
            raise ValueError(
                f"Fixed-width layout '{layout_name}' record type '{record_type}' has a gap between "
                f"{previous_label} and {label}; add an explicit filler/padding field."
            )
        expected_start = end + 1
        previous_label = label


def _validate_csv_layout(payload: dict[str, Any], *, layout_name: str) -> FileLayoutSpec:
    if payload.get("format") != "csv":
        raise ValueError(f"CSV layout '{layout_name}' must declare format: csv.")

    delimiter = _single_character(payload.get("delimiter", ","), layout_name, "delimiter", allow_tab=True)
    quote_char = payload.get("quote_char", '"')
    if quote_char is not None:
        quote_char = _single_character(quote_char, layout_name, "quote_char")
    escape_char = payload.get("escape_char", "\\")
    if escape_char is not None:
        escape_char = _single_character(escape_char, layout_name, "escape_char")
    if quote_char is not None and delimiter == quote_char:
        raise ValueError(f"CSV layout '{layout_name}' delimiter must differ from quote_char.")
    if escape_char is not None and delimiter == escape_char:
        raise ValueError(f"CSV layout '{layout_name}' delimiter must differ from escape_char.")
    if quote_char is not None and escape_char is not None and quote_char == escape_char:
        raise ValueError(f"CSV layout '{layout_name}' quote_char must differ from escape_char.")
    has_header_row = payload.get("has_header_row", False)
    if not isinstance(has_header_row, bool):
        raise ValueError(f"CSV layout '{layout_name}' has_header_row must be a boolean.")
    line_separator = _line_separator(payload.get("line_separator", "\n"), layout_name)
    if delimiter in line_separator:
        raise ValueError(
            f"CSV layout '{layout_name}' delimiter must not conflict with line_separator."
        )
    if quote_char is not None and quote_char in line_separator:
        raise ValueError(
            f"CSV layout '{layout_name}' quote_char must not conflict with line_separator."
        )
    if escape_char is not None and escape_char in line_separator:
        raise ValueError(
            f"CSV layout '{layout_name}' escape_char must not conflict with line_separator."
        )

    record_types = payload.get("record_types")
    if not isinstance(record_types, dict) or not isinstance(record_types.get("data"), dict):
        raise ValueError(f"CSV layout '{layout_name}' requires record_types.data.fields.")

    parsed_record_types: list[FileLayoutRecordType] = []
    data_fields: tuple[FileLayoutField, ...] | None = None
    for record_type, record_payload in record_types.items():
        if not isinstance(record_type, str) or not record_type.strip():
            raise ValueError(f"CSV layout '{layout_name}' has an empty record type name.")
        if not isinstance(record_payload, dict):
            raise ValueError(
                f"CSV layout '{layout_name}' record type '{record_type}' must be a mapping."
            )
        parsed_record_type = _validate_csv_record_type(
            record_payload,
            layout_name=layout_name,
            record_type=record_type,
        )
        parsed_record_types.append(parsed_record_type)
        if record_type == "data":
            data_fields = parsed_record_type.fields

    if data_fields is None:
        raise ValueError(f"CSV layout '{layout_name}' requires record_types.data.fields.")
    _validate_csv_record_type_indicators(parsed_record_types, layout_name=layout_name)

    return FileLayoutSpec(
        format="csv",
        fields=data_fields,
        is_flat_fixed_width=False,
        record_types=tuple(parsed_record_types),
        encoding=_validated_encoding(payload.get("encoding"), layout_name),
        delimiter=delimiter,
        quote_char=quote_char,
        escape_char=escape_char,
        has_header_row=has_header_row,
        line_separator=line_separator,
    )


def _validate_csv_record_type(
    payload: dict[str, Any],
    *,
    layout_name: str,
    record_type: str,
) -> FileLayoutRecordType:
    indicator = payload.get("indicator")
    parsed_indicator: FileLayoutIndicator | None = None
    if indicator is not None:
        if not isinstance(indicator, dict):
            raise ValueError(
                f"CSV layout '{layout_name}' record type '{record_type}' indicator must be a mapping."
            )
        if indicator.get("position") is not None or indicator.get("length") is not None:
            raise ValueError(
                f"CSV layout '{layout_name}' uses position-based record routing for "
                f"record type '{record_type}'. CSV inbound trailer validation supports "
                "indicator-column routing only in this slice."
            )
        column = _positive_int(
            indicator.get("column"),
            layout_name,
            f"record_types.{record_type}.indicator.column",
        )
        value = _required_name(
            indicator.get("value"),
            layout_name,
            f"record_types.{record_type}.indicator.value",
        )
        parsed_indicator = FileLayoutIndicator(value=value, column=column)

    fields_payload = _require_list(
        payload.get("fields"),
        layout_name,
        f"record_types.{record_type}.fields",
    )
    _ensure_unique_field_names(
        fields_payload,
        layout_name=layout_name,
        label=f"record_types.{record_type}.fields",
    )

    seen_columns: set[int] = set()
    fields: list[FileLayoutField] = []
    for field_payload in fields_payload:
        if not isinstance(field_payload, dict):
            raise ValueError(f"CSV layout '{layout_name}' fields must be mappings.")
        field = _csv_field(field_payload, layout_name=layout_name, record_type=record_type)
        if field.column in seen_columns:
            raise ValueError(
                f"CSV layout '{layout_name}' record type '{record_type}' declares "
                f"duplicate column {field.column}."
            )
        seen_columns.add(field.column or 0)
        fields.append(field)

    occupied_columns = set(seen_columns)
    if parsed_indicator is not None and parsed_indicator.column is not None:
        occupied_columns.add(parsed_indicator.column)
    if occupied_columns:
        missing_columns = sorted(set(range(1, max(occupied_columns) + 1)) - occupied_columns)
        if missing_columns:
            formatted = ", ".join(str(column) for column in missing_columns)
            raise ValueError(
                f"CSV layout '{layout_name}' record type '{record_type}' is missing "
                f"column(s): {formatted}."
            )
    return FileLayoutRecordType(
        name=record_type,
        fields=tuple(fields),
        indicator=parsed_indicator,
        expected_length=max(occupied_columns) if occupied_columns else 0,
    )


def _validate_csv_record_type_indicators(
    record_types: list[FileLayoutRecordType],
    *,
    layout_name: str,
) -> None:
    indicator_record_types = [
        record_type for record_type in record_types if record_type.indicator is not None
    ]
    if not indicator_record_types:
        if len(record_types) > 1:
            raise ValueError(
                f"CSV layout '{layout_name}' declares multiple record_types without "
                "indicator-column routing. CSV inbound trailer validation supports "
                "indicator-column routing only in this slice."
            )
        return
    if len(indicator_record_types) != len(record_types):
        raise ValueError(
            f"CSV layout '{layout_name}' must declare indicator.column for every "
            "record_type when using indicator-column routing."
        )
    indicator_columns = {
        record_type.indicator.column
        for record_type in indicator_record_types
        if record_type.indicator is not None
    }
    if len(indicator_columns) != 1:
        raise ValueError(
            f"CSV layout '{layout_name}' must use one shared indicator column for "
            "all CSV record types."
        )
    seen_values: dict[str, str] = {}
    for record_type in indicator_record_types:
        assert record_type.indicator is not None
        value = record_type.indicator.value
        if value in seen_values:
            raise ValueError(
                f"CSV layout '{layout_name}' declares duplicate indicator value "
                f"'{value}' for record types '{seen_values[value]}' and '{record_type.name}'."
            )
        seen_values[value] = record_type.name


def _csv_field(
    payload: Any,
    *,
    layout_name: str,
    record_type: str,
) -> FileLayoutField:
    if not isinstance(payload, dict):
        raise ValueError(f"CSV layout '{layout_name}' fields must be mappings.")
    name = _required_name(payload.get("name"), layout_name, f"record_types.{record_type}.fields.name")
    column = _positive_int(payload.get("column"), layout_name, f"{record_type}.{name}.column")
    return FileLayoutField(
        name=name,
        required=bool(payload.get("required", False)),
        column=column,
        type=_normalize_field_type(
            payload.get("type"),
            layout_name=layout_name,
            label=f"{record_type}.{name}.type",
        ),
        format=(
            str(payload["format"])
            if payload.get("format") is not None
            else None
        ),
        decimal_format=(
            str(payload["decimal_format"])
            if payload.get("decimal_format") is not None
            else None
        ),
        value_source=(
            str(payload["value_source"])
            if payload.get("value_source") is not None
            else None
        ),
        type_coercion=(
            str(payload["type_coercion"])
            if payload.get("type_coercion") is not None
            else None
        ),
    )


def _normalize_field_type(value: Any, *, layout_name: str, label: str) -> str | None:
    if value is None:
        return None
    field_type = str(value).lower()
    if field_type not in SUPPORTED_FILE_FIELD_TYPES:
        raise ValueError(
            f"File layout '{layout_name}' declares unsupported field type "
            f"'{value}' at {label}."
        )
    return field_type


def _require_list(value: Any, layout_name: str, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"File layout '{layout_name}' requires non-empty {label}.")
    return value


def _required_name(value: Any, layout_name: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"File layout '{layout_name}' requires non-empty {label}.")
    return value.strip()


def _ensure_unique_field_names(
    fields_payload: list[Any],
    *,
    layout_name: str,
    label: str,
) -> None:
    seen: set[str] = set()
    for field_payload in fields_payload:
        if not isinstance(field_payload, dict):
            continue
        name_value = field_payload.get("name")
        if not isinstance(name_value, str):
            continue
        name = name_value.strip()
        if not name:
            continue
        if name in seen:
            raise ValueError(
                f"File layout '{layout_name}' declares duplicate field name '{name}' in {label}."
            )
        seen.add(name)


def _positive_int(value: Any, layout_name: str, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"File layout '{layout_name}' requires positive integer {label}.")
    return value


def _validated_encoding(value: Any, layout_name: str) -> str:
    encoding = "UTF-8" if value is None else value
    if not isinstance(encoding, str) or not encoding.strip():
        raise ValueError(f"File layout '{layout_name}' encoding must be a non-empty string.")
    encoding = encoding.strip()
    if encoding.lower() not in SUPPORTED_JAVA_FILE_ENCODINGS:
        raise ValueError(
            f"File layout '{layout_name}' declares unsupported encoding '{encoding}' "
            "for generated Java Charset.forName(...). "
            f"Supported encodings: {sorted(SUPPORTED_JAVA_FILE_ENCODINGS)}."
        )
    return encoding


def _single_character(
    value: Any,
    layout_name: str,
    label: str,
    *,
    allow_tab: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"CSV layout '{layout_name}' {label} must be a string.")
    normalized = "\t" if allow_tab and value == "\\t" else value
    if len(normalized) != 1:
        raise ValueError(f"CSV layout '{layout_name}' {label} must be a single character.")
    return normalized


def _line_separator(value: Any, layout_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"CSV layout '{layout_name}' line_separator must be a string.")
    normalized = (
        value.replace("\\r", "\r")
        .replace("\\n", "\n")
    )
    if normalized not in {"\n", "\r\n", "\r"}:
        raise ValueError(
            f"CSV layout '{layout_name}' line_separator must be one of \\n, \\r\\n, or \\r."
        )
    return normalized
