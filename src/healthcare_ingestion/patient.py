"""Registered Patient transformations; no writes or authoritative state mutations."""


def normalize_names(frame, columns):
    from pyspark.sql import functions as f

    if not isinstance(columns, (list, tuple)) or not columns or len(set(columns)) != len(columns):
        raise ValueError("Name columns must be a nonempty unique list.")
    for name in columns:
        if name not in frame.columns or dict(frame.dtypes)[name] != "string":
            raise ValueError(f"Name normalization requires a string column: {name}.")
        frame = frame.withColumn(name, f.trim(f.col(name)))
    return frame


def latest_patient(frame, key, modified, business_columns):
    from pyspark.sql import Window
    from pyspark.sql import functions as f

    if not isinstance(business_columns, (list, tuple)) or not business_columns:
        raise ValueError("Patient business columns must be a nonempty sequence.")
    required = [key, modified, *business_columns]
    if key not in business_columns or modified not in business_columns:
        raise ValueError("Patient business columns must retain its key and source time.")
    if len(set(business_columns)) != len(business_columns) or any(
        c not in frame.columns for c in required
    ):
        raise ValueError("Invalid Patient deduplication contract.")
    if frame.where(f.col(key).isNull() | f.col(modified).isNull()).limit(1).count():
        raise ValueError("Patient key and modification timestamp are required.")
    # Named-field JSON avoids delimiter ambiguity and retains null-versus-empty distinctions.
    payload = f.to_json(
        f.struct(*(f.col(c) for c in business_columns)), options={"ignoreNullFields": "false"}
    )
    conflicts = (
        frame.withColumn("__payload", payload)
        .groupBy(key, modified)
        .agg(f.countDistinct("__payload").alias("__variants"))
        .where(f.col("__variants") > 1)
    )
    if conflicts.limit(1).count():
        raise ValueError("Conflicting Patient values share the same key and source time.")
    window = Window.partitionBy(key).orderBy(f.col(modified).desc())
    return (
        frame.select(*business_columns)
        .dropDuplicates()
        .withColumn("__rank", f.row_number().over(window))
        .where(f.col("__rank") == 1)
        .drop("__rank")
    )


REGISTRY = {"normalize_names": normalize_names, "latest_patient": latest_patient}


def dispatch(frame, functions):
    if not isinstance(functions, list) or not functions:
        raise ValueError("An ordered function list is required.")
    for step in functions:
        if set(step) != {"name", "parameters"} or step["name"] not in REGISTRY:
            raise ValueError("Unregistered function or invalid function specification.")
        if not isinstance(step["parameters"], dict):
            raise ValueError("Function parameters must be an object.")
        frame = REGISTRY[step["name"]](frame, **step["parameters"])
    return frame
