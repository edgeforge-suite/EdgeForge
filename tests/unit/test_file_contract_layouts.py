from __future__ import annotations

import pytest

from appbuilder.metadata.file_contracts import load_file_layout_spec, validate_file_layout_spec


def test_flat_fixed_width_layout_validates_as_data_record() -> None:
    layout = validate_file_layout_spec(
        {
            "fields": [
                {"name": "account_number", "length": 12, "required": True},
                {"name": "status", "length": 2},
            ]
        },
        layout_name="flat.yaml",
        contract_type="file-fixed-width",
    )

    assert layout.format == "fixed-width"
    assert layout.is_flat_fixed_width is True
    assert [field.name for field in layout.fields] == ["account_number", "status"]
    assert [field.length for field in layout.fields] == [12, 2]


def test_flat_fixed_width_layout_rejects_unknown_encoding() -> None:
    with pytest.raises(ValueError, match="unsupported encoding 'NOT_A_CHARSET'"):
        validate_file_layout_spec(
            {
                "encoding": "NOT_A_CHARSET",
                "fields": [
                    {"name": "account_number", "length": 12, "required": True},
                ],
            },
            layout_name="flat-invalid-encoding.yaml",
            contract_type="file-fixed-width",
        )


def test_flat_fixed_width_layout_rejects_python_only_encoding_alias() -> None:
    with pytest.raises(ValueError, match="unsupported encoding 'unicode_escape'"):
        validate_file_layout_spec(
            {
                "encoding": "unicode_escape",
                "fields": [
                    {"name": "account_number", "length": 12, "required": True},
                ],
            },
            layout_name="flat-python-only-encoding.yaml",
            contract_type="file-fixed-width",
        )


def test_flat_fixed_width_layout_rejects_missing_length() -> None:
    with pytest.raises(ValueError, match="positive integer data.amount.length"):
        validate_file_layout_spec(
            {
                "fields": [
                    {"name": "account_number", "length": 12},
                    {"name": "amount"},
                ]
            },
            layout_name="flat-missing-length.yaml",
            contract_type="file-fixed-width",
        )


def test_flat_fixed_width_layout_rejects_mixed_enhanced_shape() -> None:
    with pytest.raises(ValueError, match="must not mix legacy flat fields"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "fields": [{"name": "account_number", "length": 12}],
                "record_types": {
                    "data": {"fields": [{"name": "status", "length": 2}]}
                },
            },
            layout_name="flat-mixed.yaml",
            contract_type="file-fixed-width",
        )


def test_flat_fixed_width_layout_rejects_duplicate_field_names() -> None:
    with pytest.raises(ValueError, match="duplicate field name 'account_number'"):
        validate_file_layout_spec(
            {
                "fields": [
                    {"name": "account_number", "length": 12},
                    {"name": "account_number", "length": 10},
                ]
            },
            layout_name="flat-duplicate.yaml",
            contract_type="file-fixed-width",
        )


def test_fixed_width_layout_rejects_unsupported_field_type() -> None:
    with pytest.raises(ValueError, match="unsupported field type 'moneyz'"):
        validate_file_layout_spec(
            {
                "fields": [
                    {"name": "amount", "length": 10, "type": "moneyz"},
                ]
            },
            layout_name="unsupported-type.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_implicit_positions_start_after_indicator() -> None:
    layout = validate_file_layout_spec(
        {
            "format": "fixed-width",
            "encoding": "UTF-8",
            "record_types": {
                "data": {
                    "indicator": {"position": 1, "length": 1, "value": "D"},
                    "fields": [
                        {"name": "account_number", "length": 12, "required": True},
                        {"name": "status", "length": 2},
                    ],
                }
            },
        },
        layout_name="enhanced.yaml",
        contract_type="file-fixed-width",
    )

    assert layout.is_flat_fixed_width is False
    assert [(field.name, field.position) for field in layout.fields] == [
        ("account_number", 2),
        ("status", 14),
    ]


def test_enhanced_fixed_width_layout_rejects_unknown_encoding() -> None:
    with pytest.raises(ValueError, match="unsupported encoding 'NOT_A_CHARSET'"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "encoding": "NOT_A_CHARSET",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "account_number", "length": 12, "required": True},
                        ]
                    }
                },
            },
            layout_name="enhanced-invalid-encoding.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_indicator_value_length_mismatch() -> None:
    with pytest.raises(ValueError, match="indicator value length must match"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "indicator": {"position": 1, "length": 2, "value": "D"},
                        "fields": [{"name": "account_number", "length": 12}],
                    }
                },
            },
            layout_name="indicator-length.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_mixed_indicator_coverage() -> None:
    with pytest.raises(ValueError, match="indicators for every record type"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "header": {
                        "indicator": {"position": 1, "length": 1, "value": "H"},
                        "fields": [{"name": "business_date", "length": 10}],
                    },
                    "data": {
                        "fields": [{"name": "account_number", "length": 12}],
                    },
                },
            },
            layout_name="mixed-indicator-coverage.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_duplicate_indicators() -> None:
    with pytest.raises(ValueError, match="duplicate indicators"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "header": {
                        "indicator": {"position": 1, "length": 1, "value": "H"},
                        "fields": [{"name": "business_date", "length": 10}],
                    },
                    "data": {
                        "indicator": {"position": 1, "length": 1, "value": "H"},
                        "fields": [{"name": "account_number", "length": 12}],
                    },
                },
            },
            layout_name="duplicate-indicators.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_duplicate_record_type_names(tmp_path) -> None:
    layout_path = tmp_path / "duplicate-record-types.yaml"
    layout_path.write_text(
        "\n".join(
            [
                "format: fixed-width",
                "record_types:",
                "  data:",
                "    fields:",
                "      - name: account_number",
                "        length: 12",
                "  data:",
                "    fields:",
                "      - name: status",
                "        length: 2",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate key 'data'"):
        load_file_layout_spec(layout_path, contract_type="file-fixed-width")


def test_enhanced_fixed_width_requires_indicators_for_multiple_record_types() -> None:
    with pytest.raises(ValueError, match="multiple record_types requires indicators"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "header": {
                        "fields": [{"name": "business_date", "length": 10}],
                    },
                    "data": {
                        "fields": [{"name": "account_number", "length": 12}],
                    },
                },
            },
            layout_name="missing-indicators.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_both_data_and_detail_record_types() -> None:
    with pytest.raises(ValueError, match="either record_types.data or record_types.detail"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "indicator": {"position": 1, "length": 1, "value": "D"},
                        "fields": [{"name": "account_number", "length": 12}],
                    },
                    "detail": {
                        "indicator": {"position": 1, "length": 1, "value": "R"},
                        "fields": [{"name": "account_number", "length": 12}],
                    },
                },
            },
            layout_name="data-and-detail.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_mixed_explicit_and_implicit_positions() -> None:
    with pytest.raises(ValueError, match="must not mix explicit and implicit"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "account_number", "position": 1, "length": 12},
                            {"name": "status", "length": 2},
                        ]
                    }
                },
            },
            layout_name="mixed.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_overlapping_positions() -> None:
    with pytest.raises(ValueError, match="overlapping positions"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "account_number", "position": 1, "length": 12},
                            {"name": "status", "position": 12, "length": 2},
                        ]
                    }
                },
            },
            layout_name="overlap.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_gaps_without_filler_field() -> None:
    with pytest.raises(ValueError, match="gap.*filler"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "account_number", "position": 1, "length": 12},
                            {"name": "status", "position": 15, "length": 2},
                        ]
                    }
                },
            },
            layout_name="gap.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_leading_field_gap() -> None:
    with pytest.raises(ValueError, match="leading gap"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "account_number", "position": 5, "length": 12},
                        ]
                    }
                },
            },
            layout_name="leading-field-gap.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_leading_indicator_gap() -> None:
    with pytest.raises(ValueError, match="leading gap"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "indicator": {"position": 2, "length": 1, "value": "D"},
                        "fields": [{"name": "account_number", "length": 12}],
                    }
                },
            },
            layout_name="leading-indicator-gap.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_rejects_duplicate_field_names() -> None:
    with pytest.raises(ValueError, match="duplicate field name 'status'"):
        validate_file_layout_spec(
            {
                "format": "fixed-width",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "status", "length": 2},
                            {"name": "status", "length": 1},
                        ]
                    }
                },
            },
            layout_name="enhanced-duplicate.yaml",
            contract_type="file-fixed-width",
        )


def test_enhanced_fixed_width_allows_explicit_filler_field_to_cover_gap() -> None:
    layout = validate_file_layout_spec(
        {
            "format": "fixed-width",
            "record_types": {
                "data": {
                    "fields": [
                        {"name": "account_number", "position": 1, "length": 12},
                        {"name": "filler_1", "position": 13, "length": 2},
                        {"name": "status", "position": 15, "length": 2},
                    ]
                }
            },
        },
        layout_name="filler.yaml",
        contract_type="file-fixed-width",
    )

    assert [field.name for field in layout.fields] == [
        "account_number",
        "filler_1",
        "status",
    ]


def test_csv_layout_validates_data_columns() -> None:
    layout = validate_file_layout_spec(
        {
            "format": "csv",
            "encoding": "UTF-8",
            "delimiter": "|",
            "quote_char": '"',
            "escape_char": "\\",
            "has_header_row": True,
            "record_types": {
                "data": {
                    "fields": [
                        {"name": "counterparty_id", "column": 1, "required": True},
                        {"name": "effective_date", "column": 2, "type": "date"},
                    ]
                }
            },
        },
        layout_name="csv.yaml",
        contract_type="file-csv",
    )

    assert layout.format == "csv"
    assert [(field.name, field.column) for field in layout.fields] == [
        ("counterparty_id", 1),
        ("effective_date", 2),
    ]
    assert layout.delimiter == "|"
    assert layout.quote_char == '"'
    assert layout.escape_char == "\\"
    assert layout.has_header_row is True


def test_csv_layout_rejects_duplicate_columns() -> None:
    with pytest.raises(ValueError, match="duplicate column 1"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "counterparty_id", "column": 1},
                            {"name": "counterparty_name", "column": 1},
                        ]
                    }
                },
            },
            layout_name="csv-duplicate.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_zero_column() -> None:
    with pytest.raises(ValueError, match="requires positive integer data.counterparty_id.column"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 0}]}
                },
            },
            layout_name="csv-zero-column.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match=r"missing column\(s\): 2"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "counterparty_id", "column": 1},
                            {"name": "effective_date", "column": 3},
                        ]
                    }
                },
            },
            layout_name="csv-missing-column.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_duplicate_field_names() -> None:
    with pytest.raises(ValueError, match="duplicate field name 'counterparty_id'"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "counterparty_id", "column": 1},
                            {"name": "counterparty_id", "column": 2},
                        ]
                    }
                },
            },
            layout_name="csv-duplicate-name.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_invalid_delimiter() -> None:
    with pytest.raises(ValueError, match="delimiter must be a single character"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": "||",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-invalid-delimiter.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_unknown_encoding() -> None:
    with pytest.raises(ValueError, match="unsupported encoding 'NOT_A_CHARSET'"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "encoding": "NOT_A_CHARSET",
                "delimiter": ",",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-invalid-encoding.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_python_only_encoding_alias() -> None:
    with pytest.raises(ValueError, match="unsupported encoding 'unicode_escape'"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "encoding": "unicode_escape",
                "delimiter": ",",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-python-only-encoding.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_ambiguous_delimiter_quote_combination() -> None:
    with pytest.raises(ValueError, match="delimiter must differ from quote_char"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": '"',
                "quote_char": '"',
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-delimiter-quote.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_delimiter_conflicting_with_line_separator() -> None:
    with pytest.raises(ValueError, match="delimiter must not conflict with line_separator"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": "\n",
                "line_separator": "\n",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-delimiter-line-separator.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_quote_char_conflicting_with_line_separator() -> None:
    with pytest.raises(ValueError, match="quote_char must not conflict with line_separator"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "quote_char": "\n",
                "line_separator": "\n",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-quote-line-separator.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_ambiguous_quote_escape_combination() -> None:
    with pytest.raises(ValueError, match="quote_char must differ from escape_char"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "quote_char": '"',
                "escape_char": '"',
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-quote-escape.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_unsupported_field_type() -> None:
    with pytest.raises(ValueError, match="unsupported field type 'dateish'"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "record_types": {
                    "data": {
                        "fields": [
                            {"name": "effective_date", "column": 1, "type": "dateish"},
                        ]
                    }
                },
            },
            layout_name="csv-unsupported-type.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_non_boolean_has_header_row() -> None:
    with pytest.raises(ValueError, match="has_header_row must be a boolean"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "has_header_row": "true",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-invalid-header.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_ambiguous_line_separator() -> None:
    with pytest.raises(ValueError, match="line_separator"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "line_separator": "auto",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-invalid-line-separator.yaml",
            contract_type="file-csv",
        )


def test_csv_layout_rejects_escape_char_conflicting_with_line_separator() -> None:
    with pytest.raises(ValueError, match="escape_char must not conflict with line_separator"):
        validate_file_layout_spec(
            {
                "format": "csv",
                "delimiter": ",",
                "escape_char": "\n",
                "line_separator": "\n",
                "record_types": {
                    "data": {"fields": [{"name": "counterparty_id", "column": 1}]}
                },
            },
            layout_name="csv-escape-line-separator.yaml",
            contract_type="file-csv",
        )
