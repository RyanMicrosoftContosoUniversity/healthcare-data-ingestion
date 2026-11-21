"""Strict live catalog validation and lossless SQL extraction projections."""

import hashlib
import json
import re
from dataclasses import dataclass

from healthcare_ingestion.source_contracts import validate_source_contract


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value):
        raise ValueError("Invalid SQL identifier.")
    return f"[{value}]"


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def canonical_type(name, length, precision, scale):
    name = name.lower()
    if name in {"varchar", "nvarchar"}:
        size = "max" if length == -1 else str(length // (2 if name == "nvarchar" else 1))
        return f"{name}({size})"
    if name in {"decimal", "numeric"}:
        return f"{name}({precision},{scale})"
    if name == "datetime2":
        return f"datetime2({scale})"
    return name


@dataclass(frozen=True)
class DiscoveryResult:
    table: str
    expected_hash: str
    actual_hash: str
    differences: tuple[str, ...]

    @property
    def accepted(self):
        return not self.differences


def compare_table(table, columns, primary_key):
    expected = {
        "columns": [
            {
                "name": c["name"],
                "sql_type": re.sub(r"\s", "", c["sql_type"].lower()),
                "nullable": c["nullable"],
                "computed": False,
                "identity": False,
            }
            for c in table["columns"]
        ],
        "primary_key": table["primary_key"],
    }
    actual = {"columns": columns, "primary_key": primary_key}
    differences = []
    if expected["columns"] != columns:
        differences.append(
            "Column order, name, type, nullability, identity or computation differs."
        )
    if table["primary_key"] != primary_key:
        differences.append("Primary key differs.")
    return DiscoveryResult(
        table["name"], fingerprint(expected), fingerprint(actual), tuple(differences)
    )


def discover(connection, contract):
    """Inspect all selected tables before extraction; DB failures propagate fail-closed."""
    validate_source_contract(contract)
    names = [table["name"] for table in contract["tables"]]
    placeholders = ",".join("?" for _ in names)
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT t.name,c.name,ty.name,c.max_length,c.precision,c.scale,c.is_nullable,"
            "c.is_computed,c.is_identity FROM sys.tables t "
            "JOIN sys.schemas s ON s.schema_id=t.schema_id "
            "JOIN sys.columns c ON c.object_id=t.object_id "
            "JOIN sys.types ty ON ty.user_type_id=c.user_type_id "
            f"WHERE s.name=? AND t.name IN ({placeholders}) ORDER BY t.name,c.column_id",
            contract["schema"],
            *names,
        )
        columns = {name: [] for name in names}
        for table, name, sql_type, length, precision, scale, nullable, computed, identity in cursor:
            columns[table].append(
                {
                    "name": name,
                    "sql_type": canonical_type(sql_type, length, precision, scale),
                    "nullable": bool(nullable),
                    "computed": bool(computed),
                    "identity": bool(identity),
                }
            )
        cursor.execute(
            "SELECT t.name,c.name FROM sys.tables t "
            "JOIN sys.schemas s ON s.schema_id=t.schema_id "
            "JOIN sys.indexes i ON i.object_id=t.object_id AND i.is_primary_key=1 "
            "JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id "
            "JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id "
            f"WHERE s.name=? AND t.name IN ({placeholders}) ORDER BY t.name,ic.key_ordinal",
            contract["schema"],
            *names,
        )
        keys = {name: [] for name in names}
        for table, column in cursor:
            keys[table].append(column)
        return [compare_table(t, columns[t["name"]], keys[t["name"]]) for t in contract["tables"]]
    finally:
        cursor.close()


def extraction_query(schema, table, watermark=None):
    """Return SQL plus parameter slots, retaining datetime2's seventh fractional digit."""
    projections = []
    for column in table["columns"]:
        name = identifier(column["name"])
        expression = name
        if column["sql_type"].lower().startswith("datetime2"):
            expression = f"CONVERT(varchar(33),{name},126)"
        projections.append(f"{expression} AS {name}")
    query = f"SELECT {','.join(projections)} FROM {identifier(schema)}.{identifier(table['name'])}"
    if watermark:
        names = {c["name"] for c in table["columns"]}
        if watermark not in names:
            raise ValueError("Watermark is not an approved source column.")
        name = identifier(watermark)
        query += f" WHERE {name}>CAST(? AS datetime2(7)) AND {name}<=CAST(? AS datetime2(7))"
    return query


def timestamp7(value):
    """Canonical lossless source timestamp; never accept an already-truncated datetime."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Source datetime2 must be extracted as ISO text.")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?", value)
    if not match:
        raise ValueError("Invalid datetime2 ISO representation.")
    from datetime import datetime

    datetime.fromisoformat(value)
    return match[1] + "." + (match[2] or "").ljust(7, "0")
