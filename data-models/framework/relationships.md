# Proposed Framework Table Relationships

Cardinality reads from the heading table to the related table. `many` includes zero.
All relationships are proposed; full definitions and review decisions are in
`docs\ingestion\metadata-design.md`. Column names are schema-qualified.

For one diagram covering all 17 tables and 30 distinct foreign-key relationships, open
`data-models\framework\00-overview.mmd` or its zoomable `00-overview.svg` preview.
The overview shows PK/FK columns only; the four focused diagrams retain selected
review fields.

For every column as well as every relationship, open
`data-models\framework\05-full-schema.mmd` or its `05-full-schema.svg` preview.
It includes shared configuration audit columns and the Spark metric extension fields;
the keys-only overview remains unchanged.

## cfg.ProcessingDomain Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.PipelineDefinition | 1 to many | `cfg.ProcessingDomain.DomainID == cfg.PipelineDefinition.DomainID` |

## cfg.SourceSystem Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.SourceObject | 1 to many | `cfg.SourceSystem.SourceSystemID == cfg.SourceObject.SourceSystemID` |

## cfg.SourceObject Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.SourceSystem | many to 1 | `cfg.SourceObject.SourceSystemID == cfg.SourceSystem.SourceSystemID` |
| cfg.PipelineObject | 1 to many | `cfg.SourceObject.SourceObjectID == cfg.PipelineObject.SourceObjectID` |

## cfg.PipelineDefinition Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.ProcessingDomain | many to 1 | `cfg.PipelineDefinition.DomainID == cfg.ProcessingDomain.DomainID` |
| cfg.PipelineObject | 1 to many | `cfg.PipelineDefinition.PipelineID == cfg.PipelineObject.PipelineID` |
| ops.IngestionRun | 1 to many | `cfg.PipelineDefinition.PipelineID == ops.IngestionRun.PipelineID` |
| ops.AlertEvent | 1 to many | `cfg.PipelineDefinition.PipelineID == ops.AlertEvent.PipelineID` |

## cfg.PipelineObject Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.PipelineDefinition | many to 1 | `cfg.PipelineObject.PipelineID == cfg.PipelineDefinition.PipelineID` |
| cfg.SourceObject | many to 1 | `cfg.PipelineObject.SourceObjectID == cfg.SourceObject.SourceObjectID` |
| cfg.TransformationStep | 1 to many | `cfg.PipelineObject.PipelineObjectID == cfg.TransformationStep.PipelineObjectID` |
| ops.IngestionTableRun | 1 to many | `cfg.PipelineObject.PipelineObjectID == ops.IngestionTableRun.PipelineObjectID` |
| ops.IngestionWatermark | 1 to 0 or 1 | `cfg.PipelineObject.PipelineObjectID == ops.IngestionWatermark.PipelineObjectID` |

## cfg.TransformationStep Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.PipelineObject | many to 1 | `cfg.TransformationStep.PipelineObjectID == cfg.PipelineObject.PipelineObjectID` |
| ops.IngestionTransformationRun | 1 to many | `cfg.TransformationStep.TransformationStepID == ops.IngestionTransformationRun.TransformationStepID` |

## ops.IngestionRun Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.PipelineDefinition | many to 1 | `ops.IngestionRun.PipelineID == cfg.PipelineDefinition.PipelineID` |
| ops.IngestionTableRun | 1 to many | `ops.IngestionRun.RunID == ops.IngestionTableRun.RunID` |
| ops.IngestionWatermark | 1 to many | `ops.IngestionRun.RunID == ops.IngestionWatermark.LeaseOwnerRunID` |
| ops.IngestionError | 1 to many | `ops.IngestionRun.RunID == ops.IngestionError.RunID` |
| ops.SchemaChangeLog | 1 to many | `ops.IngestionRun.RunID == ops.SchemaChangeLog.RunID` |
| ops.ReconciliationResult | 1 to many | `ops.IngestionRun.RunID == ops.ReconciliationResult.RunID` |
| ops.IngestionTransformationRun | 1 to many | `ops.IngestionRun.RunID == ops.IngestionTransformationRun.RunID` |
| ops.SparkApplicationRunMetric | 1 to many | `ops.IngestionRun.RunID == ops.SparkApplicationRunMetric.RunID` |
| ops.DiagnosticCollection | 1 to many | `ops.IngestionRun.RunID == ops.DiagnosticCollection.RunID` |
| ops.AlertEvent | 1 to many | `ops.IngestionRun.RunID == ops.AlertEvent.RunID` |

## ops.IngestionTableRun Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.IngestionRun | many to 1 | `ops.IngestionTableRun.RunID == ops.IngestionRun.RunID` |
| cfg.PipelineObject | many to 1 | `ops.IngestionTableRun.PipelineObjectID == cfg.PipelineObject.PipelineObjectID` |
| ops.IngestionWatermark | 1 to many | `ops.IngestionTableRun.TableRunID == ops.IngestionWatermark.LastSuccessfulTableRunID` |
| ops.IngestionError | 1 to many | `ops.IngestionTableRun.TableRunID == ops.IngestionError.TableRunID` |
| ops.SchemaChangeLog | 1 to many | `ops.IngestionTableRun.TableRunID == ops.SchemaChangeLog.TableRunID` |
| ops.ReconciliationResult | 1 to many | `ops.IngestionTableRun.TableRunID == ops.ReconciliationResult.TableRunID` |
| ops.IngestionTransformationRun | 1 to many | `ops.IngestionTableRun.TableRunID == ops.IngestionTransformationRun.TableRunID` |
| ops.SparkApplicationRunMetric | 1 to many | `ops.IngestionTableRun.TableRunID == ops.SparkApplicationRunMetric.TableRunID` |
| ops.AlertEvent | 1 to many | `ops.IngestionTableRun.TableRunID == ops.AlertEvent.TableRunID` |

## ops.IngestionWatermark Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.PipelineObject | 1 to 1 | `ops.IngestionWatermark.PipelineObjectID == cfg.PipelineObject.PipelineObjectID` |
| ops.IngestionTableRun | many to 0 or 1 | `ops.IngestionWatermark.LastSuccessfulTableRunID == ops.IngestionTableRun.TableRunID` |
| ops.IngestionRun | many to 0 or 1 | `ops.IngestionWatermark.LeaseOwnerRunID == ops.IngestionRun.RunID` |

## ops.IngestionError Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.IngestionRun | many to 1 | `ops.IngestionError.RunID == ops.IngestionRun.RunID` |
| ops.IngestionTableRun | many to 0 or 1 | `ops.IngestionError.TableRunID == ops.IngestionTableRun.TableRunID` |
| ops.IngestionTransformationRun | many to 0 or 1 | `ops.IngestionError.StepExecutionID == ops.IngestionTransformationRun.StepExecutionID` |

## ops.SchemaChangeLog Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.IngestionRun | many to 1 | `ops.SchemaChangeLog.RunID == ops.IngestionRun.RunID` |
| ops.IngestionTableRun | many to 1 | `ops.SchemaChangeLog.TableRunID == ops.IngestionTableRun.TableRunID` |

## ops.ReconciliationResult Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.IngestionRun | many to 1 | `ops.ReconciliationResult.RunID == ops.IngestionRun.RunID` |
| ops.IngestionTableRun | many to 1 | `ops.ReconciliationResult.TableRunID == ops.IngestionTableRun.TableRunID` |

## ops.IngestionTransformationRun Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.IngestionError | 1 to many | `ops.IngestionTransformationRun.StepExecutionID == ops.IngestionError.StepExecutionID` |
| ops.IngestionRun | many to 1 | `ops.IngestionTransformationRun.RunID == ops.IngestionRun.RunID` |
| ops.IngestionTableRun | many to 1 | `ops.IngestionTransformationRun.TableRunID == ops.IngestionTableRun.TableRunID` |
| cfg.TransformationStep | many to 1 | `ops.IngestionTransformationRun.TransformationStepID == cfg.TransformationStep.TransformationStepID` |

## ops.SparkApplicationRunMetric Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.IngestionRun | many to 1 | `ops.SparkApplicationRunMetric.RunID == ops.IngestionRun.RunID` |
| ops.IngestionTableRun | many to 0 or 1 | `ops.SparkApplicationRunMetric.TableRunID == ops.IngestionTableRun.TableRunID` |
| ops.DiagnosticCollection | 1 to many | `ops.SparkApplicationRunMetric.SparkMetricID == ops.DiagnosticCollection.SparkMetricID` |
| ops.AlertEvent | 1 to many | `ops.SparkApplicationRunMetric.SparkMetricID == ops.AlertEvent.SparkMetricID` |

## ops.DiagnosticCollection Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.IngestionRun | many to 1 | `ops.DiagnosticCollection.RunID == ops.IngestionRun.RunID` |
| ops.SparkApplicationRunMetric | many to 0 or 1 | `ops.DiagnosticCollection.SparkMetricID == ops.SparkApplicationRunMetric.SparkMetricID` |
| ops.DiagnosticArtifact | 1 to many | `ops.DiagnosticCollection.CollectionID == ops.DiagnosticArtifact.CollectionID` |

## ops.DiagnosticArtifact Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| ops.DiagnosticCollection | many to 1 | `ops.DiagnosticArtifact.CollectionID == ops.DiagnosticCollection.CollectionID` |

## ops.AlertEvent Table Relationships

| Table | Cardinality | Columns |
| --- | --- | --- |
| cfg.PipelineDefinition | many to 0 or 1 | `ops.AlertEvent.PipelineID == cfg.PipelineDefinition.PipelineID` |
| ops.IngestionRun | many to 0 or 1 | `ops.AlertEvent.RunID == ops.IngestionRun.RunID` |
| ops.IngestionTableRun | many to 0 or 1 | `ops.AlertEvent.TableRunID == ops.IngestionTableRun.TableRunID` |
| ops.SparkApplicationRunMetric | many to 0 or 1 | `ops.AlertEvent.SparkMetricID == ops.SparkApplicationRunMetric.SparkMetricID` |
