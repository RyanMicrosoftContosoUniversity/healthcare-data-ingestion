"""Explicit source-fidelity schema mapping, separate from technical UTC timestamps."""

import re


def mapped_schema(table):
    from pyspark.sql import types as t

    simple = {
        "bigint": t.LongType,
        "int": t.IntegerType,
        "smallint": t.ShortType,
        "tinyint": t.ShortType,
        "bit": t.BooleanType,
        "date": t.DateType,
        "uniqueidentifier": t.StringType,
    }
    fields = []
    for column in table["columns"]:
        sql = re.sub(r"\s", "", column["sql_type"].lower())
        decimal = re.fullmatch(r"decimal\((\d+),(\d+)\)", sql)
        if decimal:
            kind = t.DecimalType(int(decimal[1]), int(decimal[2]))
        elif sql.startswith(("varchar(", "nvarchar(", "datetime2(")):
            kind = t.StringType()
        elif sql in simple:
            kind = simple[sql]()
        else:
            raise ValueError(f"Unsupported source type {sql}.")
        fields.append(t.StructField(column["name"], kind, column["nullable"]))
    return t.StructType(fields)


def assert_schema(frame, expected):
    """Nullability is enforced on values; readers may conservatively mark fields nullable."""
    from pyspark.sql import functions as f

    actual = [(field.name, field.dataType) for field in frame.schema]
    wanted = [(field.name, field.dataType) for field in expected]
    if actual != wanted:
        raise ValueError("Captured columns/types differ from the immutable mapped contract.")
    required = [field.name for field in expected if not field.nullable]
    if required:
        condition = f.lit(False)
        for column in required:
            condition = condition | f.col(column).isNull()
        if frame.where(condition).limit(1).count():
            raise ValueError("Captured data violates required-column nullability.")
