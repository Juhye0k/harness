from copy import deepcopy

import pytest

from app.api.editor import RevisionRequest
from app.domain.caption_edit import content_hash, validate_cues
from app.domain.video import VideoError

SEGMENTS = [{"id": "s0", "text": "원본 대사"}, {"id": "s1", "text": "두 번째"}]
CUES = [
    {"source_segment_id": "s0", "start_ms": 1000, "end_ms": 2000, "lines": ["첫 자막"]},
    {"source_segment_id": "s1", "start_ms": 2400, "end_ms": 3400, "lines": ["두 번째"]},
]


def test_manual_edit_preserves_source_and_version_fingerprint():
    original = deepcopy(CUES)
    assert validate_cues(CUES, SEGMENTS, 1000, 6000, True) == CUES
    assert CUES == original
    changed = deepcopy(CUES)
    changed[0]["lines"] = ["수정한 자막"]
    assert content_hash(changed, "asr1", True) != content_hash(CUES, "asr1", True)
    assert content_hash(CUES, "asr1", True) != content_hash(CUES, "asr1", False)
    assert content_hash(CUES, "asr1", True) != content_hash(CUES, "asr2", True)


@pytest.mark.parametrize(
    "mutation",
    [
        {"start_ms": 999},
        {"end_ms": 1000},
        {"end_ms": 10000},
        {"end_ms": 1449},
        {"end_ms": 2801},
        {"source_segment_id": "other"},
        {"lines": ["한 줄", "두 줄", "세 줄"]},
        {"lines": ["가" * 15]},
        {"lines": ["단어 하나 둘 셋"]},
        {"lines": ["가" * 14], "end_ms": 1500},
        {"lines": [r"{\pos(0,0)}"]},
        {"lines": ["줄\n바꿈"]},
    ],
)
def test_display_and_render_limits_are_not_bypassed(mutation):
    cues = deepcopy(CUES)
    cues[0].update(mutation)
    with pytest.raises(VideoError):
        validate_cues(cues, SEGMENTS, 1000, 6000, True)


def test_overlap_and_missing_source_cannot_be_confirmed():
    cues = deepcopy(CUES)
    cues[1]["start_ms"] = 1900
    with pytest.raises(VideoError):
        validate_cues(cues, SEGMENTS, 1000, 6000, True)
    with pytest.raises(VideoError, match="누락"):
        validate_cues(CUES[:1], SEGMENTS, 1000, 6000, True)
    assert validate_cues(CUES[:1], SEGMENTS, 1000, 6000, False)


@pytest.mark.parametrize("field,value", [("start_ms", True), ("start_ms", 1.2), ("end_ms", "2000")])
def test_editor_time_schema_requires_integer_milliseconds(field, value):
    cues = deepcopy(CUES)
    cues[0][field] = value
    with pytest.raises(ValueError):
        RevisionRequest(source_version="v1", cues=cues, reviewed=True)
