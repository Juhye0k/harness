import pytest

from app.domain.recommendations import candidates, normalize, rank
from app.domain.video import MediaInfo, VideoError, validate_output, validate_range


def segments():
    return normalize(
        {
            "phrases": [
                {"offsetMilliseconds": i * 5000, "durationMilliseconds": 5000, "text": f"문장 {i}"}
                for i in range(36)
            ]
        },
        180000,
    )


def proposal(first="s0000", last="s0005"):
    return {"start_segment_id": first, "end_segment_id": last, "title": "제목"}


def score(item, **overrides):
    return {
        "candidate_id": item["id"],
        "hook": 4,
        "completeness": 4,
        "context_independence": 4,
        "memorable": 4,
        "editability": 4,
        "reason": "이유",
        "evidence_ids": [item["segments"][0]["id"]],
        "topic": "topic",
        **overrides,
    }


def test_padding_caps_and_stable_ids():
    valid, rejected = candidates(
        {"candidates": [proposal(), proposal("s0010", "s0021"), proposal("missing")]},
        segments(),
        180000,
    )
    assert valid[0]["start_ms"] == 0 and valid[0]["end_ms"] == 30200
    assert valid[1]["end_ms"] - valid[1]["start_ms"] == 60000
    assert rejected == [{"index": 2, "reason": "INVALID_RANGE_OR_SEGMENT"}]
    assert candidates({"candidates": []}, segments(), 180000) == ([], [])


@pytest.mark.parametrize(
    "bad",
    [
        proposal("x"),
        proposal("s0009", "s0001"),
        proposal("s0000", "s0000"),
        proposal("s0000", "s0014"),
    ],
)
def test_all_invalid_candidates_fail(bad):
    with pytest.raises(VideoError, match="계약"):
        candidates({"candidates": [bad]}, segments(), 180000)


def test_weighted_score_and_overlap_tie_order():
    valid, _ = candidates(
        {"candidates": [proposal(), proposal(), proposal("s0010", "s0021")]}, segments(), 180000
    )
    selected = rank({"scores": [score(c) for c in valid]}, valid)
    assert [c["id"] for c in selected] == ["c00", "c02"]
    assert selected[0]["score"] == 100
    assert rank({"scores": [score(valid[0], completeness=1)]}, valid[:1]) == []
    assert rank({"scores": [score(valid[0], hook=0)]}, valid[:1])[0]["score"] == 75


def test_topic_limit_and_score_contract():
    valid, _ = candidates(
        {
            "candidates": [
                proposal("s0000", "s0005"),
                proposal("s0010", "s0015"),
                proposal("s0020", "s0025"),
            ]
        },
        segments(),
        180000,
    )
    assert len(rank({"scores": [score(c) for c in valid]}, valid)) == 2
    for raw in [
        {"scores": []},
        {"scores": [score(valid[0], hook=5)]},
        {"scores": [score(valid[0], evidence_ids=["s0035"])]},
        {"scores": [score(valid[0], hook=True)]},
    ]:
        with pytest.raises(VideoError):
            rank(raw, valid[:1])


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"phrases": None},
        {"phrases": [{"offsetMilliseconds": -1, "durationMilliseconds": 10, "text": "a"}]},
        {"phrases": [{"offsetMilliseconds": 10, "durationMilliseconds": 100, "text": "a"}]},
    ],
)
def test_bad_transcription(raw):
    with pytest.raises(VideoError):
        normalize(raw, 50)


def test_transcription_empty_and_limits():
    assert normalize({"phrases": []}, 1000) == []
    with pytest.raises(VideoError):
        normalize(
            {
                "phrases": [
                    {"offsetMilliseconds": 0, "durationMilliseconds": 10, "text": "a" * 60001}
                ]
            },
            100,
        )
    with pytest.raises(VideoError):
        normalize({"phrases": [{}] * 2001}, 100)


def test_non_text_and_reversed_end_are_invalid():
    for phrases in [
        [{"offsetMilliseconds": 0, "durationMilliseconds": 10, "text": 42}],
        [
            {"offsetMilliseconds": 0, "durationMilliseconds": 20, "text": "a"},
            {"offsetMilliseconds": 10, "durationMilliseconds": 1, "text": "b"},
        ],
    ]:
        with pytest.raises(VideoError) as exc:
            normalize({"phrases": phrases}, 100)
        assert exc.value.code == "MODEL_RESPONSE_INVALID"


def test_maximum_five_and_exact_overlap_boundary():
    proposals = [
        {
            "id": f"c{i}",
            "start_ms": i * 40000,
            "end_ms": i * 40000 + 30000,
            "segments": [{"id": f"s{i}"}],
        }
        for i in range(7)
    ]
    raw = {"scores": [score(c, topic=c["id"]) for c in proposals]}
    assert len(rank(raw, proposals)) == 5
    proposals[1].update(start_ms=15000, end_ms=45000)
    assert [c["id"] for c in rank({"scores": raw["scores"][:2]}, proposals[:2])] == ["c0"]


@pytest.mark.parametrize("duration", [10, 30, 60])
def test_variable_duration_contract(duration):
    validate_range(0, MediaInfo(180, True), duration)
    assert all(validate_output(MediaInfo(duration, True, duration), True, duration).values())
    with pytest.raises(VideoError):
        validate_output(MediaInfo(duration + 0.2, True), True, duration)
    with pytest.raises(VideoError):
        validate_range(180 - duration + 1, MediaInfo(180, True), duration)
