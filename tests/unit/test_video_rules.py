import pytest

from app.domain.video import MediaInfo, VideoError, validate_output, validate_range


@pytest.mark.parametrize("start", [-1, float("nan"), float("inf"), 10.001])
def test_invalid_range(start):
    with pytest.raises(VideoError):
        validate_range(start, MediaInfo(20, True))


@pytest.mark.parametrize("start", [0, 10])
def test_inclusive_boundaries(start):
    validate_range(start, MediaInfo(20, True))


@pytest.mark.parametrize("info,audio", [(MediaInfo(9.8, True), True), (MediaInfo(10, False), True)])
def test_output_failure(info, audio):
    with pytest.raises(VideoError, match="출력"):
        validate_output(info, audio)


def test_container_duration_is_also_checked():
    with pytest.raises(VideoError):
        validate_output(MediaInfo(10, True, 11), True)
