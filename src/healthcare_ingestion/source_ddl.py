"""Render empty-database SQL definitions from approved source-column contracts."""

import hashlib
import re
from collections.abc import Mapping

from healthcare_ingestion.source_contracts import validate_source_contract

_REFERENCE = re.compile(
    r"^FK to (?:the event-time version of )?"
    r"`([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)`(?=[.;, ]|$)",
    re.IGNORECASE,
)


def _quote(name: str) -> str:
    return f"[{name}]"


def _constraint_name(*parts: str) -> str:
    name = "_".join(parts)
    if len(name) > 128:
        digest = hashlib.sha256(name.encode("ascii")).hexdigest()[:12]
        name = f"{name[:115]}_{digest}"
    return _quote(name)


def _is_unique(column: Mapping) -> bool:
    return column["purpose"].upper().startswith("UQ;")


def _foreign_keys(contract: Mapping) -> list[str]:
    tables = {table["name"].casefold(): table for table in contract["tables"]}
    schema = _quote(contract["schema"])
    statements = []
    for table in contract["tables"]:
        for column in table["columns"]:
            purpose = column["purpose"]
            if not purpose.upper().startswith("FK TO "):
                continue
            reference = _REFERENCE.match(purpose)
            if reference is None:
                raise ValueError(f"{table['name']}.{column['name']}: unrecognized FK declaration.")
            target = tables.get(reference[1].casefold())
            target_columns = (
                {item["name"].casefold(): item for item in target["columns"]} if target else {}
            )
            target_column = target_columns.get(reference[2].casefold())
            if target_column is None:
                raise ValueError(f"{table['name']}.{column['name']}: unknown FK target.")
            primary_key = [name.casefold() for name in target["primary_key"]]
            if primary_key != [target_column["name"].casefold()] and not _is_unique(target_column):
                raise ValueError(f"{table['name']}.{column['name']}: FK target is not unique.")
            source_type = re.sub(r"\s+", "", column["sql_type"]).casefold()
            target_type = re.sub(r"\s+", "", target_column["sql_type"]).casefold()
            if source_type != target_type:
                raise ValueError(f"{table['name']}.{column['name']}: FK types do not match.")
            name = _constraint_name("FK", table["name"], column["name"])
            statements.append(
                f"ALTER TABLE {schema}.{_quote(table['name'])} WITH CHECK\n"
                f"    ADD CONSTRAINT {name} FOREIGN KEY ({_quote(column['name'])})\n"
                f"    REFERENCES {schema}.{_quote(target['name'])}"
                f" ({_quote(target_column['name'])})\n"
                "    ON DELETE NO ACTION ON UPDATE NO ACTION;"
            )
    return statements


def render_source_ddl(contract: Mapping) -> str:
    """Render columns, PKs, explicit UQs/FKs; never alter or deploy a database."""
    validate_source_contract(contract)
    foreign_keys = _foreign_keys(contract)
    statements = [
        f"-- Generated {contract['source_system']} source baseline; do not edit by hand.",
        "-- For an empty source database with the declared schema already present.",
        "-- Not an upgrade migration; remaining integrity/write-path work: database/README.md.",
        "SET XACT_ABORT ON;\nBEGIN TRANSACTION;",
    ]
    schema = _quote(contract["schema"])
    for table in contract["tables"]:
        declarations = [
            f"    {_quote(column['name'])} {column['sql_type']} "
            f"{'NULL' if column['nullable'] else 'NOT NULL'}"
            for column in table["columns"]
        ]
        by_name = {column["name"].casefold(): column["name"] for column in table["columns"]}
        keys = ", ".join(_quote(by_name[name.casefold()]) for name in table["primary_key"])
        declarations.append(
            f"    CONSTRAINT {_constraint_name('PK', table['name'])} PRIMARY KEY ({keys})"
        )
        for column in table["columns"]:
            if _is_unique(column):
                declarations.append(
                    f"    CONSTRAINT {_constraint_name('UQ', table['name'], column['name'])}"
                    f" UNIQUE ({_quote(column['name'])})"
                )
        body = ",\n".join(declarations)
        statements.append(f"CREATE TABLE {schema}.{_quote(table['name'])} (\n{body}\n);")
    statements.extend(foreign_keys)
    statements.append("COMMIT TRANSACTION;")
    return "\n\n".join(statements) + "\n"
