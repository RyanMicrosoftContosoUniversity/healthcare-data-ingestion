import io
import json

import pytest

from healthcare_ingestion.delta_io import PublicationIntent, publication_evidence
from healthcare_ingestion.logging_utils import configure_logging, logging_context


def test_publication_recovery_requires_complete_commit_evidence():
    intent = PublicationIntent("batch", "dataset", 1, recovering=True)
    entries = [{"version": 3, "userMetadata": '{"batch_id":"batch","dataset_id":"dataset"}'}]
    assert publication_evidence(entries, intent) == 3
    with pytest.raises(ValueError, match="unavailable"):
        publication_evidence([{"version": 4}], intent)
    assert publication_evidence([{"version": 1}, {"version": 2}], intent) is None
    with pytest.raises(ValueError, match="corruption"):
        publication_evidence(entries + [{"version": 5, **entries[0]}], intent)


def test_logging_scopes_reset_without_serializing_exception_secrets():
    stream = io.StringIO()
    logger = configure_logging(stream=stream)
    with logging_context(run_id="first"):
        logger.info("RunStarted")
        try:
            raise ValueError("Password=must-not-be-logged")
        except ValueError:
            logger.exception("RunFailed")
    logger.info("Outside")
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert events[0]["run_id"] == "first"
    assert events[1]["ExceptionType"] == "ValueError"
    assert "run_id" not in events[2]
    assert "must-not-be-logged" not in stream.getvalue()
