"""Run with uv run --locked python .\\scripts\\synthetic-data\\generate.py from the repo root."""

from healthcare_ingestion.generator import main

if __name__ == "__main__":
    raise SystemExit(main())
