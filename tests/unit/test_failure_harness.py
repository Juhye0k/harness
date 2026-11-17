import pytest

from app.adapters.analysis_requests import input_hash
from scripts.run_failure_drills import validate_project


@pytest.mark.parametrize(
    "project",
    [
        "shortform-harness",
        "shortform-integration",
        "shortform-failure-../../main",
        "shortform-failure-abc",
        "shortform-failure-000000000000;docker",
    ],
)
def test_drill_cannot_target_existing_or_injected_project(project):
    with pytest.raises(ValueError):
        validate_project(project)


def test_drill_scope_and_receipt_input_identity():
    validate_project("shortform-failure-012345abcdef")
    assert input_hash({"mode": "transcription", "url": "https://example.com/a"}) == input_hash(
        {"url": "https://example.com/a", "mode": "transcription"}
    )
    assert input_hash({"purpose": "balanced"}) != input_hash({"purpose": "humor"})
