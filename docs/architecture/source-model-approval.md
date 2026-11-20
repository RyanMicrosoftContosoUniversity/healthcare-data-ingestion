# Approved Synthetic Source Models

The user explicitly approved the existing 13-table Clarity and 15-table Caboodle models
on separate Azure SQL logical servers and databases for this implementation.

## Population Decision

Generate both sources independently using a deterministic shared identity manifest.
This supersedes earlier proposals to derive Caboodle through a Clarity-to-Caboodle ETL.
Preserve lineage fields and historical relationships, but do not assume independently
generated rows reconcile one-for-one across the two sources.

Each source is reconciled to its own Bronze copy. All records remain synthetic.

November 20 decision: use **Synthea for clinical data generation with versioned mapping
configuration to populate the Azure SQL source models**. Retain independent Clarity
and Caboodle loading paths and the shared deterministic identity manifest; Caboodle
does not read Clarity. A mapping file describes conversions but still needs an
executable loader for keys, relationships, change application, audit fields and
validation. Prepare mapping coverage and any supplemental operational/test-data rules
for review without changing the approved schemas.

November 20 follow-up approves the demo profile: 1,000 initial patients, 12 months
retained history and about 500-1,000 combined daily source-row changes. Normal targets
include about five new patients, ten demographic updates and 25 new encounters,
plus related clinical/history rows; around 3-5 corrections and 1-2 eligible soft deletes
are within the total. Zero-change and approximately 5,000-row spike scenarios are
available on demand. These are controlled workload targets, not guaranteed Synthea
counts or truncation limits. The detailed profile is in the decision register.

Standard S0 (10 DTU) per database is the accepted initial SQL evaluation baseline,
subject to initial-load/extraction checks and normal deployment gates. Generator
hosting is selected: Azure Container Apps Jobs on Consumption, with approximately
$10/month as the generation planning target, not a fixed fee or enforced cap.
Worker/runtime size, storage, actual spend controls and deployment targets remain
open. The generation estimate excludes SQL databases, normal Fabric ingestion and the
initial historical seed. The earlier larger volume/four-vCore recommendations
are superseded as the demo baseline; no cloud deployment is authorized here.

## Scope and Constraints

- Low-cost demonstration with configurable volume and deterministic changes, not a
  requirement to simulate actual hospital volume. Preserve the approved isolated
  performance-benchmark capability without requiring large daily data volumes.
- Preserve the approved column definitions, keys, nullability, audit fields, history,
  relationship constraints, and event grains.
- Source dictionaries and typed snapshots are reviewable implementation inputs.
- Source/profile approval does not authorize an arbitrary subscription, capacity,
  network model, administrator, spend level or deployment. Changes to the accepted
  initial S0 evaluation baseline require sizing review.
- Framework/control-store approval remains pending and is required before that phase.
