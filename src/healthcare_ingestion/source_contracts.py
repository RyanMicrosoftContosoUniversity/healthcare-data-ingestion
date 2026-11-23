"""Validate approved SQL source-column contracts before deployment generation."""

import re
from collections.abc import Mapping


def bind_source_contracts(snapshot, contracts):
    """Bind approved systems to connection refs through immutable source dataset IDs."""
    systems = {}
    for contract in contracts.values():
        source = contract["source_system"].casefold()
        if source in systems and systems[source] != contract:
            raise ValueError("Conflicting approved contracts for one source system.")
        systems[source] = contract
    bound = {}
    for dataset in snapshot.datasets:
        if not dataset.external or dataset.layer != "source":
            continue
        parts = dataset.dataset_id.split(".")
        if len(parts) < 3 or parts[0] != "source" or parts[1] not in systems:
            raise ValueError("A source dataset has no approved system contract.")
        contract = systems[parts[1]]
        for mapping in dataset.physical_maps.values():
            connection = mapping["connection_ref"]
            if connection in bound and bound[connection] != contract:
                raise ValueError("A source connection cannot mix system contracts.")
            if mapping["schema"] != contract["schema"] or mapping["table"] not in {
                table["name"] for table in contract["tables"]
            }:
                raise ValueError("The source mapping differs from its approved contract.")
            bound[connection] = contract
    return bound


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_SQL_TYPE = re.compile(
    r"(?:bigint|int|smallint|tinyint|bit|date|uniqueidentifier"
    r"|datetime2\([0-7]\)"
    r"|n?varchar\((?:[1-9][0-9]*|max)\)"
    r"|decimal\([1-9][0-9]*,\s*[0-9]+\))\Z",
    re.IGNORECASE,
)


def validate_source_contract(contract: Mapping) -> None:
    """Reject ambiguous names, invalid column declarations, and unusable primary keys."""
    if type(contract.get("schema_version")) is not int or contract["schema_version"] != 1:
        raise ValueError("Unsupported source contract schema_version.")
    if contract.get("source_system") not in {"Clarity", "Caboodle"}:
        raise ValueError("Unknown source_system.")
    _check_identifier(contract.get("schema"), "schema")
    tables = contract.get("tables")
    if not isinstance(tables, list) or not tables:
        raise ValueError("A source contract requires a nonempty tables list.")
    table_names = set()
    for table in tables:
        if not isinstance(table, Mapping):
            raise ValueError("Each table must be an object.")
        name = _check_identifier(table.get("name"), "table")
        if name.casefold() in table_names:
            raise ValueError(f"Duplicate table name: {name}")
        table_names.add(name.casefold())
        columns = table.get("columns")
        if not isinstance(columns, list) or not columns:
            raise ValueError(f"{name}: columns must be a nonempty list.")
        by_name = {}
        for column in columns:
            if not isinstance(column, Mapping):
                raise ValueError(f"{name}: each column must be an object.")
            column_name = _check_identifier(column.get("name"), "column")
            normalized = column_name.casefold()
            if normalized in by_name:
                raise ValueError(f"{name}: duplicate column {column_name}")
            sql_type = column.get("sql_type")
            if not isinstance(sql_type, str) or not _SQL_TYPE.fullmatch(sql_type):
                raise ValueError(f"{name}.{column_name}: unsupported SQL type.")
            _check_type_bounds(sql_type)
            if type(column.get("nullable")) is not bool:
                raise ValueError(f"{name}.{column_name}: nullable must be a boolean.")
            if not isinstance(column.get("purpose"), str) or not column["purpose"].strip():
                raise ValueError(f"{name}.{column_name}: purpose is required.")
            by_name[normalized] = column
        primary_key = table.get("primary_key")
        if not isinstance(primary_key, list) or not primary_key:
            raise ValueError(f"{name}: primary_key is required.")
        seen_keys = set()
        for key in primary_key:
            normalized = _check_identifier(key, "primary key").casefold()
            if normalized not in by_name or normalized in seen_keys:
                raise ValueError(f"{name}: invalid or duplicate primary key column {key}")
            if by_name[normalized]["nullable"]:
                raise ValueError(f"{name}: primary key column {key} cannot be nullable.")
            seen_keys.add(normalized)


def _check_identifier(value, kind: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {kind} identifier: {value!r}")
    return value


def _check_type_bounds(sql_type: str) -> None:
    decimal = re.fullmatch(r"decimal\((\d+),\s*(\d+)\)", sql_type, re.IGNORECASE)
    if decimal:
        precision, scale = map(int, decimal.groups())
        if not 0 <= scale <= precision <= 38:
            raise ValueError("Decimal precision/scale must satisfy 0 <= scale <= precision <= 38.")
    text = re.fullmatch(r"(n?varchar)\((\d+)\)", sql_type, re.IGNORECASE)
    if text:
        maximum = 4000 if text[1].lower() == "nvarchar" else 8000
        if int(text[2]) > maximum:
            raise ValueError(f"{text[1]} length exceeds {maximum}; use max if intended.")
