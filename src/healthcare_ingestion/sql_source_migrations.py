"""Render repeatable, transactional source-only integrity/audit upgrades without deployment."""

import re

from healthcare_ingestion.source_contracts import validate_source_contract
from healthcare_ingestion.sql_source_integrity import EVENT_TIMES, PERIODS

DDL_FENCE_SQL = (
    "DECLARE @result int; EXEC @result=sys.sp_getapplock "
    "@Resource=N'healthcare-ingestion-source', @DbPrincipal=N'public', "
    "@LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=0; "
    "IF @result<0 THROW 51004,'Source DDL requires the exclusive extraction fence.',1;"
)


def execute_source_migration_sql(connection, script: str) -> None:
    """Approved admin execution path for baseline 001 and upgrade 002, never automatic.

    The outer transaction keeps the fence across a script's nested BEGIN/COMMIT and GO
    batches. The caller supplies a dedicated, non-autocommit migration/admin connection.
    Generator DML-only identities must not receive database CONTROL or db_ddladmin.
    """
    if connection.autocommit:
        raise ValueError("Source DDL requires a dedicated non-autocommit admin connection.")
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT CASE WHEN HAS_PERMS_BY_NAME(DB_NAME(),N'DATABASE',N'CONTROL')=1 "
            "OR IS_ROLEMEMBER(N'db_ddladmin')=1 THEN 1 ELSE 0 END;"
        )
        if cursor.fetchone()[0] != 1:
            raise PermissionError("Source DDL is restricted to the approved migration/admin path.")
        cursor.execute("SET XACT_ABORT ON; IF @@TRANCOUNT=0 BEGIN TRANSACTION;")
        cursor.execute(DDL_FENCE_SQL)
        for batch in re.split(r"(?im)^\s*GO\s*(?:--[^\n]*)?$", script):
            if batch.strip():
                cursor.execute(batch)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        cursor.close()


def render_source_migration(contract: dict) -> str:
    validate_source_contract(contract)
    schema = contract["schema"]
    statements = [
        "-- Source-only upgrade 002. Offline-generated; review before Azure SQL execution.",
        "-- No third database. Requires the approved 001 baseline in this source database.",
        "SET XACT_ABORT ON;\nSET NOCOUNT ON;\nBEGIN TRANSACTION;",
        DDL_FENCE_SQL,
    ]
    source = contract["source_system"]
    for table in contract["tables"]:
        qualified = f"[{schema}].[{table['name']}]"
        statements.append(
            f"IF OBJECT_ID(N'{qualified}',N'U') IS NULL "
            "THROW 51000,'Approved source baseline is missing.',1;"
        )
    statements.append(
        "IF OBJECT_ID(N'dbo.SyntheticSourceCheckpoint',N'U') IS NULL\n"
        "CREATE TABLE dbo.SyntheticSourceCheckpoint (\n"
        " SourceSystem varchar(30) NOT NULL PRIMARY KEY,\n"
        " BatchName varchar(80) NOT NULL, PopulationDigest char(64) NOT NULL,\n"
        " MappingDigest char(64) NOT NULL, ContractDigest char(64) NOT NULL,\n"
        " RowCount bigint NOT NULL CHECK(RowCount>=0), CommittedAtUtc datetime2(7) NOT NULL,\n"
        " CoverageStartUtc datetime2(7) NOT NULL, CoverageEndUtc datetime2(7) NOT NULL,\n"
        f" CONSTRAINT CK_SyntheticSourceIdentity CHECK(SourceSystem='{source}')\n);"
    )
    statements.append(
        "IF OBJECT_ID(N'dbo.SyntheticSourceBatchCommit',N'U') IS NULL\n"
        "CREATE TABLE dbo.SyntheticSourceBatchCommit (\n"
        " SourceSystem varchar(30) NOT NULL, BatchName varchar(80) NOT NULL,\n"
        " PopulationDigest char(64) NOT NULL, MappingDigest char(64) NOT NULL,\n"
        " ContractDigest char(64) NOT NULL, RowCount bigint NOT NULL CHECK(RowCount>=0),\n"
        " CommittedAtUtc datetime2(7) NOT NULL,\n"
        " CoverageStartUtc datetime2(7) NOT NULL, CoverageEndUtc datetime2(7) NOT NULL,\n"
        " CONSTRAINT PK_SyntheticSourceBatchCommit PRIMARY KEY(SourceSystem,BatchName),\n"
        f" CONSTRAINT CK_SyntheticBatchSource CHECK(SourceSystem='{source}')\n);"
    )
    for auxiliary in ("SyntheticSourceCheckpoint", "SyntheticSourceBatchCommit"):
        for field in ("CoverageStartUtc", "CoverageEndUtc"):
            statements.append(
                f"IF COL_LENGTH(N'dbo.{auxiliary}',N'{field}') IS NULL "
                f"ALTER TABLE dbo.{auxiliary} ADD {field} datetime2(7) NULL;"
            )
        guard = (
            f"IF EXISTS(SELECT 1 FROM dbo.{auxiliary} WHERE CoverageStartUtc IS NULL "
            "OR CoverageEndUtc IS NULL) "
            "THROW 51008,'Legacy coverage requires reviewed generation evidence backfill.',1;"
        )
        statements.append("EXEC(N'" + guard.replace("'", "''") + "');")
        for field in ("CoverageStartUtc", "CoverageEndUtc"):
            alter = (
                "IF EXISTS(SELECT 1 FROM sys.columns WHERE object_id="
                f"OBJECT_ID(N'dbo.{auxiliary}') AND name=N'{field}' AND is_nullable=1) "
                f"ALTER TABLE dbo.{auxiliary} ALTER COLUMN {field} datetime2(7) NOT NULL;"
            )
            statements.append("EXEC(N'" + alter.replace("'", "''") + "');")
        constraint = (
            "IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE "
            f"name=N'CK_{auxiliary}_Coverage') ALTER TABLE dbo.{auxiliary} WITH CHECK "
            f"ADD CONSTRAINT CK_{auxiliary}_Coverage CHECK(CoverageStartUtc<=CoverageEndUtc);"
        )
        statements.append("EXEC(N'" + constraint.replace("'", "''") + "');")
    modified = "ModifiedAtUtc" if source == "Clarity" else "EtlModifiedAtUtc"
    upper_queries = [
        "SELECT MAX(CommittedAtUtc) AS audit_at FROM dbo.SyntheticSourceCheckpoint",
        "SELECT MAX(CommittedAtUtc) AS audit_at FROM dbo.SyntheticSourceBatchCommit",
        *[
            f"SELECT MAX([{modified}]) AS audit_at FROM [{schema}].[{t['name']}]"
            for t in contract["tables"]
        ],
    ]
    publication_procedure = (
        "CREATE OR ALTER PROCEDURE dbo.PrepareSyntheticSourcePublication AS BEGIN "
        "SET NOCOUNT ON; "
        "IF APPLOCK_MODE(N'public',N'healthcare-ingestion-source',N'Transaction')<>N'Exclusive' "
        "THROW 51004,'Source writes require the exclusive extraction fence.',1; "
        "DECLARE @upper datetime2(7); SELECT @upper=MAX(a.audit_at) FROM ("
        + " UNION ALL ".join(upper_queries)
        + ") a; "
        "DECLARE @publication datetime2(7)=SYSUTCDATETIME(); "
        "IF @publication<=@upper SET @publication=DATEADD(nanosecond,100,@upper); "
        "DECLARE @text varchar(33)=CONVERT(varchar(33),@publication,126); "
        "EXEC sys.sp_set_session_context @key=N'source_publication_at', "
        "@value=@text,@read_only=1; END;"
    )
    statements.append("EXEC(N'" + publication_procedure.replace("'", "''") + "');")
    ledger_trigger = (
        "CREATE OR ALTER TRIGGER dbo.TR_SyntheticSourceBatchCommit_Immutable "
        "ON dbo.SyntheticSourceBatchCommit AFTER INSERT,UPDATE,DELETE AS BEGIN "
        "SET NOCOUNT ON; "
        "IF EXISTS(SELECT 1 FROM deleted) "
        "THROW 51005,'Committed source batch evidence is immutable.',1; "
        "IF APPLOCK_MODE(N'public',N'healthcare-ingestion-source',N'Transaction')<>N'Exclusive' "
        "THROW 51004,'Source writes require the exclusive extraction fence.',1; "
        "DECLARE @publication datetime2(7)="
        "TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N'source_publication_at')); "
        "IF @publication IS NULL OR EXISTS(SELECT 1 FROM inserted "
        "WHERE CommittedAtUtc<>@publication) OR EXISTS("
        "SELECT 1 FROM dbo.SyntheticSourceCheckpoint WHERE CommittedAtUtc>=@publication) "
        "THROW 51007,'Source publication audit must advance the committed boundary.',1; "
        "IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.SyntheticSourceCheckpoint c "
        "ON i.SourceSystem=c.SourceSystem WHERE i.CoverageStartUtc<>c.CoverageEndUtc "
        "OR i.CoverageEndUtc<c.CoverageEndUtc) "
        "THROW 51009,'Source coverage must continue from the prior committed horizon.',1; END;"
    )
    statements.append("EXEC(N'" + ledger_trigger.replace("'", "''") + "');")
    head_trigger = (
        "CREATE OR ALTER TRIGGER dbo.TR_SyntheticSourceCheckpoint_Integrity "
        "ON dbo.SyntheticSourceCheckpoint AFTER INSERT,UPDATE,DELETE AS BEGIN SET NOCOUNT ON; "
        "IF APPLOCK_MODE(N'public',N'healthcare-ingestion-source',N'Transaction')<>N'Exclusive' "
        "THROW 51004,'Source writes require the exclusive extraction fence.',1; "
        "IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i "
        "WHERE i.SourceSystem=d.SourceSystem)) "
        "THROW 51005,'Committed source checkpoint deletion is prohibited.',1; "
        "IF EXISTS(SELECT 1 FROM inserted i LEFT JOIN dbo.SyntheticSourceBatchCommit b "
        "ON i.SourceSystem=b.SourceSystem AND i.BatchName=b.BatchName "
        "WHERE b.BatchName IS NULL OR i.PopulationDigest<>b.PopulationDigest "
        "OR i.MappingDigest<>b.MappingDigest OR i.ContractDigest<>b.ContractDigest "
        "OR i.RowCount<>b.RowCount OR i.CommittedAtUtc<>b.CommittedAtUtc "
        "OR i.CoverageStartUtc<>b.CoverageStartUtc OR i.CoverageEndUtc<>b.CoverageEndUtc) "
        "THROW 51005,'Source checkpoint must match its immutable coverage ledger.',1; "
        "IF EXISTS(SELECT 1 FROM inserted i JOIN deleted d ON i.SourceSystem=d.SourceSystem "
        "WHERE i.CommittedAtUtc<=d.CommittedAtUtc OR i.CoverageStartUtc<>d.CoverageEndUtc "
        "OR i.CoverageEndUtc<d.CoverageEndUtc) "
        "THROW 51009,'Source checkpoint coverage or audit boundary regresses.',1; END;"
    )
    statements.append("EXEC(N'" + head_trigger.replace("'", "''") + "');")
    statements.append(
        "IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys "
        "WHERE name=N'FK_SyntheticSourceCheckpoint_Batch' "
        "AND parent_object_id=OBJECT_ID(N'dbo.SyntheticSourceCheckpoint'))\n"
        "ALTER TABLE dbo.SyntheticSourceCheckpoint WITH CHECK "
        "ADD CONSTRAINT FK_SyntheticSourceCheckpoint_Batch "
        "FOREIGN KEY(SourceSystem,BatchName) "
        "REFERENCES dbo.SyntheticSourceBatchCommit(SourceSystem,BatchName);"
    )

    def check(table, suffix, expression):
        name = f"CK_Synthetic_{table}_{suffix}"
        statements.append(
            f"IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'{name}' "
            f"AND parent_object_id=OBJECT_ID(N'[{schema}].[{table}]'))\n"
            f" ALTER TABLE [{schema}].[{table}] WITH CHECK ADD CONSTRAINT [{name}] "
            f"CHECK ({expression});"
        )

    def index(table, suffix, columns, predicate=None):
        name = f"UX_Synthetic_{table}_{suffix}"
        statements.append(
            f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'{name}' "
            f"AND object_id=OBJECT_ID(N'[{schema}].[{table}]'))\n"
            f" CREATE UNIQUE INDEX [{name}] ON [{schema}].[{table}] "
            f"({','.join('[' + c + ']' for c in columns)})"
            + (f" WHERE {predicate}" if predicate else "")
            + ";"
        )

    for table in contract["tables"]:
        name, columns = table["name"], {c["name"] for c in table["columns"]}
        for lower, upper in PERIODS:
            if {lower, upper} <= columns:
                operator = "<" if lower == "EffectiveFromUtc" else "<="
                check(
                    name,
                    lower + "_" + upper,
                    f"[{lower}] IS NULL OR [{upper}] IS NULL OR [{lower}]{operator}[{upper}]",
                )
        for value, unit in (
            ("OrderedDose", "DoseUnit"),
            ("AdministeredDose", "DoseUnit"),
            ("NumericValue", "ResultUnit"),
            ("NumericValue", "ValueUnit"),
        ):
            if {value, unit} <= columns:
                check(
                    name,
                    value + "_Unit",
                    f"[{value}] IS NULL OR [{unit}] IS NOT NULL",
                )
        if {"ReferenceLow", "ReferenceHigh", "ResultUnit"} <= columns:
            check(
                name,
                "ReferenceUnit",
                "([ReferenceLow] IS NULL AND [ReferenceHigh] IS NULL) OR [ResultUnit] IS NOT NULL",
            )
        if "DeletedAtUtc" in columns:
            check(
                name,
                "Deleted",
                "([IsDeleted]=0 AND [DeletedAtUtc] IS NULL) OR "
                "([IsDeleted]=1 AND [DeletedAtUtc] IS NOT NULL)",
            )
        if "DiagnosisSequence" in columns:
            check(name, "Sequence", "[DiagnosisSequence]>0")
        if "IsCurrent" in columns:
            business = "Source" + name[3:] + "ID"
            check(
                name,
                "Current",
                "([IsCurrent]=1 AND [EffectiveToUtc] IS NULL) OR "
                "([IsCurrent]=0 AND [EffectiveToUtc] IS NOT NULL)",
            )
            index(name, "Current", ["OriginSystem", business], "[IsCurrent]=1")
            index(name, "Version", ["OriginSystem", business, "EffectiveFromUtc"])
        if name.startswith("Fact"):
            primary_source = {
                "FactEncounter": "SourceEncounterID",
                "FactDiagnosis": "SourceDiagnosisID",
                "FactProcedure": "SourceProcedureID",
                "FactMedicationOrder": "SourceMedicationOrderID",
                "FactMedicationAdministration": "SourceMedicationAdministrationID",
                "FactLabResult": "SourceLaboratoryResultID",
                "FactAppointment": "SourceAppointmentID",
            }[name]
            index(name, "SourceEvent", ["OriginSystem", primary_source])
        if name in {"DimDiagnosis", "DimProcedure", "DimMedication"}:
            prefix = name[3:]
            index(name, "Catalog", ["OriginSystem", prefix + "CodeSystem", prefix + "Code"])
        if source == "Clarity" and name == "Appointment":
            index(name, "Encounter", ["EncounterID"], "[EncounterID] IS NOT NULL")
        if name in {"Diagnosis", "FactDiagnosis"}:
            encounter = "EncounterID" if source == "Clarity" else "SourceEncounterID"
            index(name, "Sequence", [encounter, "DiagnosisSequence"])
            index(
                name,
                "Primary",
                [encounter],
                "[IsPrimary]=1 AND [IsDeleted]=0 AND [DiagnosisStatus]<>N'canceled' "
                "AND [DiagnosisStatus]<>N'cancelled' AND [DiagnosisStatus]<>N'inactive'",
            )
        _audit_trigger(statements, contract, table)
    checks = _relational_checks(contract)
    procedure = (
        f"CREATE OR ALTER PROCEDURE [{schema}].[ValidateSyntheticSource] AS\n"
        "BEGIN\nSET NOCOUNT ON;\n" + "\n".join(checks) + "\nEND;"
    )
    statements.append("EXEC(N'" + procedure.replace("'", "''") + "');")
    statements.append(f"EXEC [{schema}].[ValidateSyntheticSource];")
    statements.append("COMMIT TRANSACTION;")
    return "\n\n".join(statements) + "\n"


def _audit_trigger(statements, contract, table):
    source, schema, name = contract["source_system"], contract["schema"], table["name"]
    creation = "CreatedAtUtc" if source == "Clarity" else "EtlCreatedAtUtc"
    modified = "ModifiedAtUtc" if source == "Clarity" else "EtlModifiedAtUtc"
    keys = table["primary_key"]
    join = " AND ".join(f"t.[{k}]=i.[{k}]" for k in keys)
    deleted_join = " AND ".join(f"d.[{k}]=i.[{k}]" for k in keys)
    assignments = [f"[{creation}]=COALESCE(d.[{creation}],@now)", f"[{modified}]=@now"]
    if source == "Clarity":
        assignments.append(
            "[DeletedAtUtc]=CASE WHEN i.IsDeleted=1 THEN "
            "COALESCE(d.DeletedAtUtc,@now) ELSE NULL END"
        )
    batch_gate = ""
    if source == "Caboodle":
        batch_gate = (
            "IF EXISTS(SELECT 1 FROM inserted WHERE EtlBatchID<>"
            "TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N'source_batch_id'))) "
            "OR TRY_CONVERT(uniqueidentifier,SESSION_CONTEXT(N'source_batch_id')) IS NULL "
            "THROW 51001,'Caboodle writes require approved loader batch context.',1;\n"
        )
    sql = (
        f"CREATE OR ALTER TRIGGER [{schema}].[TR_Synthetic_{name}_Audit] "
        f"ON [{schema}].[{name}] AFTER INSERT,UPDATE,DELETE AS\nBEGIN\n"
        "SET NOCOUNT ON;\n"
        f"IF TRIGGER_NESTLEVEL(OBJECT_ID(N'[{schema}].[TR_Synthetic_{name}_Audit]'),"
        "'AFTER','DML')>1 RETURN;\n"
        "IF APPLOCK_MODE(N'public',N'healthcare-ingestion-source',N'Transaction')<>N'Exclusive' "
        "THROW 51004,'Source writes require the exclusive extraction fence.',1;\n"
        "IF EXISTS(SELECT 1 FROM deleted d WHERE NOT EXISTS(SELECT 1 FROM inserted i WHERE "
        + " AND ".join(f"d.[{k}]=i.[{k}]" for k in keys)
        + ")) "
        "THROW 51002,'Physical deletes and primary-key changes are prohibited.',1;\n"
        + batch_gate
        + "DECLARE @now datetime2(7)="
        "TRY_CONVERT(datetime2(7),SESSION_CONTEXT(N'source_publication_at'));\n"
        "IF @now IS NULL OR EXISTS(SELECT 1 FROM dbo.SyntheticSourceCheckpoint "
        "WHERE CommittedAtUtc>=@now) "
        "THROW 51007,'Source publication audit must advance the committed boundary.',1;\n"
        f"UPDATE t SET {', '.join(assignments)} FROM [{schema}].[{name}] t "
        f"JOIN inserted i ON {join} LEFT JOIN deleted d ON {deleted_join};\nEND;"
    )
    statements.append("EXEC(N'" + sql.replace("'", "''") + "');")


def _relational_checks(contract):
    checks = []
    schema = contract["schema"]

    def reject(query, message):
        checks.append(f"IF EXISTS({query}) THROW 51003,'{message}',1;")

    if contract["source_system"] == "Clarity":
        reject(
            f"SELECT 1 FROM [{schema}].Appointment a JOIN [{schema}].Encounter e "
            "ON a.EncounterID=e.EncounterID WHERE a.PatientID<>e.PatientID",
            "Appointment encounter patient mismatch.",
        )
        reject(
            f"SELECT 1 FROM [{schema}].Encounter e JOIN [{schema}].Coverage c "
            "ON e.PrimaryCoverageID=c.CoverageID WHERE e.PatientID<>c.PatientID OR "
            "CAST(e.ArrivalAtUtc AS date)<c.EffectiveDate OR "
            "CAST(e.ArrivalAtUtc AS date)>c.TerminationDate",
            "Encounter coverage patient or date mismatch.",
        )
    else:
        from healthcare_ingestion.source_mapping import DATE_FIELDS

        for dim in ("DimPatient", "DimProvider", "DimDepartment", "DimCoverage"):
            business, key = "Source" + dim[3:] + "ID", dim[3:] + "Key"
            reject(
                f"SELECT 1 FROM [{schema}].[{dim}] a JOIN [{schema}].[{dim}] b "
                f"ON a.OriginSystem=b.OriginSystem AND a.[{business}]=b.[{business}] "
                f"AND a.[{key}]<b.[{key}] WHERE "
                "(a.EffectiveToUtc IS NULL OR b.EffectiveFromUtc<a.EffectiveToUtc) AND "
                "(b.EffectiveToUtc IS NULL OR a.EffectiveFromUtc<b.EffectiveToUtc)",
                f"{dim} validity overlap.",
            )
            reject(
                f"SELECT 1 FROM [{schema}].[{dim}] GROUP BY OriginSystem,[{business}] "
                "HAVING SUM(CASE WHEN IsCurrent=1 THEN 1 ELSE 0 END)<>1",
                f"{dim} current version missing or ambiguous.",
            )
        for table in contract["tables"]:
            name = table["name"]
            if name not in EVENT_TIMES:
                continue
            columns = {c["name"] for c in table["columns"]}
            candidates = EVENT_TIMES[name]
            event = (
                "f.[" + candidates[0] + "]"
                if len(candidates) == 1
                else ("COALESCE(" + ",".join("f.[" + c + "]" for c in candidates) + ")")
            )
            for field, dim in (
                ("PatientKey", "DimPatient"),
                ("DepartmentKey", "DimDepartment"),
                ("CoverageKey", "DimCoverage"),
                ("AttendingProviderKey", "DimProvider"),
                ("DiagnosingProviderKey", "DimProvider"),
                ("PerformingProviderKey", "DimProvider"),
                ("OrderingProviderKey", "DimProvider"),
                ("AdministeringProviderKey", "DimProvider"),
                ("ProviderKey", "DimProvider"),
            ):
                if field in columns:
                    key = dim[3:] + "Key"
                    reject(
                        f"SELECT 1 FROM [{schema}].[{name}] f JOIN [{schema}].[{dim}] d "
                        f"ON f.[{field}]=d.[{key}] WHERE {event}<d.EffectiveFromUtc OR "
                        f"{event}>=d.EffectiveToUtc",
                        f"{name} event-time dimension mismatch.",
                    )
            for key, field in DATE_FIELDS.items():
                if key in columns:
                    reject(
                        f"SELECT 1 FROM [{schema}].[{name}] WHERE "
                        f"([{key}] IS NULL AND [{field}] IS NOT NULL) OR "
                        f"([{key}] IS NOT NULL AND [{field}] IS NULL) OR "
                        f"[{key}]<>CONVERT(int,CONVERT(char(8),[{field}],112))",
                        f"{name} date key mismatch.",
                    )
            if name not in {"FactEncounter", "FactAppointment"}:
                reject(
                    f"SELECT 1 FROM [{schema}].[{name}] f "
                    f"LEFT JOIN [{schema}].FactEncounter e "
                    "ON f.SourceEncounterID=e.SourceEncounterID "
                    "AND f.OriginSystem=e.OriginSystem "
                    f"JOIN [{schema}].DimPatient p ON f.PatientKey=p.PatientKey "
                    f"LEFT JOIN [{schema}].DimPatient q ON e.PatientKey=q.PatientKey "
                    "WHERE e.EncounterKey IS NULL OR p.SourcePatientID<>q.SourcePatientID "
                    "OR f.IsDeleted<e.IsDeleted",
                    f"{name} encounter lineage or parent deletion mismatch.",
                )
        reject(
            f"SELECT 1 FROM [{schema}].FactEncounter e JOIN [{schema}].DimCoverage c "
            f"ON e.CoverageKey=c.CoverageKey JOIN [{schema}].DimPatient p "
            "ON e.PatientKey=p.PatientKey WHERE c.SourcePatientID<>p.SourcePatientID OR "
            "CAST(e.ArrivalAtUtc AS date)<c.EffectiveDate OR "
            "CAST(e.ArrivalAtUtc AS date)>c.TerminationDate",
            "FactEncounter enrollment mismatch.",
        )
        reject(
            f"SELECT 1 FROM [{schema}].FactMedicationAdministration a "
            f"LEFT JOIN [{schema}].FactMedicationOrder o "
            "ON a.SourceMedicationOrderID=o.SourceMedicationOrderID AND "
            "a.OriginSystem=o.OriginSystem WHERE o.MedicationOrderKey IS NULL OR "
            "a.SourceEncounterID<>o.SourceEncounterID OR a.MedicationKey<>o.MedicationKey OR "
            "a.IsDeleted<o.IsDeleted",
            "Administration corrected order mismatch.",
        )

        # Whole datetime2 spans fit bigint ticks, but not bigint nanoseconds. Integer
        # tick arithmetic and decimal(28,0)/(9,0) retain ten fractional minute digits,
        # avoiding premature SQL decimal scale reduction at the scale-2 rounding tie.
        def elapsed(start, end):
            return (
                f"CAST((DATEDIFF_BIG(day,[{start}],[{end}])*CAST(864000000000 AS bigint) "
                f"+ DATEDIFF_BIG(nanosecond,CAST([{end}] AS date),[{end}])/100 "
                f"- DATEDIFF_BIG(nanosecond,CAST([{start}] AS date),[{start}])/100) "
                "AS decimal(28,0))/CAST(600000000 AS decimal(9,0))"
            )

        reject(
            f"SELECT 1 FROM [{schema}].FactEncounter WHERE "
            "(DischargeAtUtc IS NULL AND LengthOfStayMinutes IS NOT NULL) OR "
            "(DischargeAtUtc IS NOT NULL AND LengthOfStayMinutes IS NULL) OR "
            f"LengthOfStayMinutes<>ROUND({elapsed('ArrivalAtUtc', 'DischargeAtUtc')},2)",
            "Encounter derived length of stay mismatch.",
        )
        appointment_duration = elapsed("ScheduledStartAtUtc", "ScheduledEndAtUtc")
        reject(
            f"SELECT 1 FROM [{schema}].FactAppointment WHERE "
            f"ScheduledDurationMinutes<>ROUND({appointment_duration},2)",
            "Appointment derived duration mismatch.",
        )
    return checks
