"""Curated parameter contracts shared by release validation and runtime dispatch."""

FUNCTION_SCHEMAS = {
    "normalize_names": {
        "type": "object",
        "required": ["columns"],
        "additionalProperties": False,
        "properties": {
            "columns": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        },
    },
    "latest_patient": {
        "type": "object",
        "required": ["key", "modified", "business_columns"],
        "additionalProperties": False,
        "properties": {
            "key": {"type": "string"},
            "modified": {"type": "string"},
            "business_columns": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        },
    },
}
