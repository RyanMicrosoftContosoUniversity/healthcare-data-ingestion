"""Generate local SQL baselines without connecting to source or control databases."""

import json
from pathlib import Path

from healthcare_ingestion.source_ddl import render_source_ddl


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    outputs = []
    for source in ("clarity", "caboodle"):
        contract = json.loads(
            (root / "database" / "schema-contracts" / f"{source}.json").read_text(encoding="utf-8")
        )
        sql = render_source_ddl(contract)
        target = root / "database" / source / "schema" / "001-source-baseline.sql"
        outputs.append((target, sql, len(contract["tables"])))
    for target, sql, table_count in outputs:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sql, encoding="utf-8", newline="\n")
        print(f"{target.relative_to(root)}: {table_count} tables.")


if __name__ == "__main__":
    main()
