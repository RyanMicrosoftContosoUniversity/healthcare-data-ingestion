# Source SQL Baselines

**Local preparation only. No databases have been deployed.**

Run `uv run --locked python .\scripts\export_source_ddl.py` from the repository root.
The approved JSON source contracts generate separate Clarity and Caboodle
`schema\001-source-baseline.sql` scripts. Generation does not access Azure, Fabric,
or an existing database; it validates both inputs before writing either output.

## What Is Implemented

- All 28 tables and 454 source columns with exact declared types/nullability and PKs.
- Explicit column-level `UQ;` declarations and intra-source `FK to` declarations,
  including Caboodle's event-time dimension references.
- Foreign keys after all table definitions, with no cascading update/delete actions.
- Quoted identifiers, including `[Procedure]`, and deterministic constraint names.
- Input validation for unknown/non-unique/mismatched FK targets; lineage prose marked
  "not a FK" does not become a cross-source or fact-to-fact constraint.

The renderer recognizes only the currently approved FK/UQ purpose notation. This is
not natural-language business-rule inference. Review any contract notation changes;
an unrecognized explicit FK declaration fails instead of silently omitting its constraint.

## Before Deployment

These transactional empty-database baselines **are not repeatable upgrade migrations**.
They deliberately fail against existing tables rather than skip or replace them.
The declared schema (`dbo` for both approved sources) must already exist. Do not execute
them against metadata databases or populated sources. Live Azure SQL execution/catalog
validation has not occurred; do not claim offline tests prove deployed behavior.

The approved source models include additional rules not encoded structurally in the
column JSON and therefore not yet emitted by this renderer:

| Model | Remaining integrity and write-path work |
| --- | --- |
| Clarity | Filtered uniqueness for non-null `Appointment.EncounterID`; patient/encounter and coverage/patient/date consistency; positive/unique diagnosis sequences and one active primary diagnosis; ordered date/time/reference bounds and compatible unit/value pairs. |
| Caboodle | Fact event identity uniqueness; catalog composite business uniqueness; one current Type 2 row and non-overlapping validity; event-time dimension resolution; date-key consistency; corrected-parent propagation and derived measures. |
| Both | Audit/publication timestamp mutation paths, controlled source checkpoints, soft-delete policies, approved indexes/defaults, versioned non-destructive upgrade migrations, deployed catalog/integrity tests, and synthetic population/change scenarios. |

These requirements are retained in `docs\clarity\data-dictionary.md`,
`docs\caboodle\data-dictionary.md`, and the implementation plan. They must be completed
and tested before calling source-schema implementation complete. Constraints that need
multiple rows, temporal lookups, or mutation semantics require reviewed SQL/write-path
logic, not invented cross-source foreign keys.

Cloud targets, infrastructure sizing/identity/networking, and actual deployment remain
gated. Framework review independently gates all control-store migrations, ingestion
configuration, Airflow/discovery execution, and release/recovery runtime.
