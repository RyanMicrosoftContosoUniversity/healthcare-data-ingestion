# Approved Synthetic Source Models

The user explicitly approved the existing 13-table Clarity and 15-table Caboodle models
on separate Azure SQL logical servers and databases for this implementation.

## Population Decision

Generate both sources independently using a deterministic shared identity manifest.
This supersedes earlier proposals to derive Caboodle through a Clarity-to-Caboodle ETL.
Preserve lineage fields and historical relationships, but do not assume independently
generated rows reconcile one-for-one across the two sources.

Each source is reconciled to its own Bronze copy. All records remain synthetic.

## Scope and Constraints

- Performance-oriented development with configurable volume and deterministic changes.
- Preserve the approved column definitions, keys, nullability, audit fields, history,
  relationship constraints, and event grains.
- Source dictionaries and typed snapshots are reviewable implementation inputs.
- Source approval does not authorize an arbitrary subscription, capacity, network model,
  SQL SKU, administrator, or spend level.
- Framework/control-store approval remains pending and is required before that phase.
