import pytest

from app.domain.caption_edit import validate_cues
from app.domain.source_caption_evaluation import decision, screen_transitions
from app.domain.source_caption_proposal import propose, youtube_onsets


def raw(events):
    return {"events": events}


def event(start, *segments):
    return {"tStartMs": start, "dDurationMs": 9000, "segs": list(segments)}


def test_rolling_newline_does_not_repeat_text_or_extend_word_to_window_end():
    words = youtube_onsets(
        raw(
            [
                event(0, {"utf8": "첫"}, {"utf8": " 자막", "tOffsetMs": 500}),
                event(900, {"utf8": "\n"}),
                event(1000, {"utf8": "다음"}),
            ]
        ),
        10000,
    )
    assert words == [
        {"text": "첫", "start_ms": 0},
        {"text": "자막", "start_ms": 500},
        {"text": "다음", "start_ms": 1000},
    ]
    result = propose(words, [{"id": "s1", "start_ms": 0, "end_ms": 2000}], 0, 1000)
    assert result["cues"][-1]["end_ms"] == 1000


def test_same_onset_keeps_both_real_words_without_inventing_time():
    words = youtube_onsets(raw([event(0, {"utf8": "안"}, {"utf8": " 안"})]), 1000)
    assert words == [{"text": "안 안", "start_ms": 0}]


@pytest.mark.parametrize("offset", [-1, float("nan"), True])
def test_invalid_or_unbounded_word_times_rejected(offset):
    with pytest.raises(ValueError):
        youtube_onsets(raw([event(0, {"utf8": "안녕", "tOffsetMs": offset})]), 1000)


def test_out_of_order_words_are_not_silently_sorted():
    with pytest.raises(ValueError, match="Nonmonotonic"):
        youtube_onsets(raw([event(100, {"utf8": "가"}), event(0, {"utf8": "나"})]), 1000)


def test_readability_failure_does_not_drop_words_and_claim_success():
    words = [
        {"text": "아주긴단어가있습니다" * 4, "start_ms": 0},
        {"text": "끝", "start_ms": 1000},
    ]
    result = propose(words, [{"id": "s", "start_ms": 0, "end_ms": 2000}], 0, 1000)
    assert result["status"] == "NO_COMPLETE_READABLE_PARTITION"
    assert result["cues"] == []
    assert result["selected_words"] == 1
    assert result["words_dropped_for_readability"] == 0


def test_candidate_boundary_words_are_explicit_not_trimmed_or_forged():
    words = [
        {"text": "이전", "start_ms": 0},
        {"text": "중간", "start_ms": 500},
        {"text": "다음", "start_ms": 1200},
        {"text": "끝", "start_ms": 1800},
    ]
    result = propose(words, [{"id": "s", "start_ms": 0, "end_ms": 2000}], 200, 1500)
    assert [row["text"] for row in result["cut_words"]] == ["이전", "다음"]
    assert result["cues"][0]["start_ms"] == 500
    assert result["cues"][-1]["end_ms"] == 1200
    assert result["human_reviewed"] is False
    assert result["speech_end_verified"] is False


def test_screen_transition_uses_only_even_frames_and_rejects_transient_noise():
    even = ["첫 화면", "첫 화면", "잡음", "첫 화면", "첫 화면", "다음 화면 내용", "다음 화면 내용"]
    frames = []
    for index, text in enumerate(even):
        frames.extend(
            [
                {"time_ms": index * 200, "text": text},
                {"time_ms": index * 200 + 100, "text": "판정에 쓰지 않는 프레임"},
            ]
        )
    observation = {"sample_step_ms": 100, "frames": frames}
    assert screen_transitions(observation, 0, 1400) == (100, [1000])


def test_break_near_screen_change_uses_existing_word_intervals_and_keeps_all_words():
    words = [
        {"start_ms": time, "text": text}
        for time, text in zip((0, 600, 900, 1500), ("처음", "다음", "문구", "밖"), strict=True)
    ]
    segments = [{"id": "s1", "start_ms": 0, "end_ms": 1500}]
    original = propose(words, segments, 0, 1500)
    aligned = propose(words, segments, 0, 1500, screen_changes=[680, 690, 1100], snap_ms=100)
    assert [cue["end_ms"] for cue in original["cues"]] == [1500]
    assert [cue["end_ms"] for cue in aligned["cues"]] == [600, 1500]
    assert aligned["snapped_screen_boundaries_ms"] == [600]
    assert [cue["lines"] for cue in aligned["cues"]] == [["처음"], ["다음 문구"]]
    assert validate_cues(aligned["cues"], segments, 0, 1500, False) == aligned["cues"]
    assert aligned["human_reviewed"] is False


def test_screen_break_can_be_crossed_to_keep_short_words_readable():
    words = [
        {"start_ms": 0, "text": "안"},
        {"start_ms": 200, "text": "녕"},
        {"start_ms": 800, "text": "밖"},
    ]
    segments = [{"id": "s1", "start_ms": 0, "end_ms": 800}]
    result = propose(words, segments, 0, 800, screen_changes=[200], snap_ms=100)
    assert result["snapped_screen_boundaries_ms"] == [200]
    assert [cue["lines"] for cue in result["cues"]] == [["안 녕"]]


def test_worse_ocr_or_bad_policy_cannot_replace_baseline():
    assert (
        decision(
            {"screen_reference_cer": 0.1},
            {
                "screen_reference_cer": 0.3,
                "policy_violations": {"duration": 1},
            },
        )["action"]
        == "keep_existing"
    )
    good = decision(
        {"screen_reference_cer": 0.2, "interval_screen_reference_cer": 0.2},
        {
            "screen_reference_cer": 0.1,
            "interval_screen_reference_cer": 0.1,
            "policy_violations": {},
        },
    )
    assert good["action"] == "experimental_draft_only"
    assert good["production_approval"] is False
    assert decision(
        {"screen_reference_cer": 0.2, "interval_screen_reference_cer": 0.2},
        {
            "screen_reference_cer": 0.1,
            "interval_screen_reference_cer": 0.3,
            "policy_violations": {},
        },
    )["reasons"] == ["INTERVAL_ALIGNMENT_WORSE"]


def test_absent_reference_does_not_turn_zero_difference_into_pass():
    assert (
        decision(
            {"screen_reference_cer": None},
            {
                "screen_reference_cer": None,
                "policy_violations": {},
            },
        )["action"]
        == "keep_existing"
    )


def test_final_word_without_next_onset_is_unresolved_not_silently_dropped():
    result = propose(
        [{"text": "첫", "start_ms": 0}, {"text": "끝", "start_ms": 700}],
        [{"id": "s", "start_ms": 0, "end_ms": 2000}],
        0,
        1500,
    )
    assert result["cues"] == []
    assert result["status"] == "UNRESOLVED_FINAL_WORD"
    assert result["unresolved_words"][0]["text"] == "끝"
