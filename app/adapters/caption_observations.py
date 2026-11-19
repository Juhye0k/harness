"""Read optional, operator-prepared OCR observations from the private asset store."""

import json

from app.domain.source_caption_evaluation import observation_samples, validate_observation_source

MAX_OBSERVATION_BYTES = 5 * 1024 * 1024


def read_caption_observations(root, asset):
    root = root.resolve()
    directory = root / "assets" / str(asset.id)
    path = directory / "caption-observations.json"
    if path.is_symlink() or path.resolve() != path:
        raise ValueError("Observation path must be inside the managed asset directory")
    if not path.is_file():
        return None
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_OBSERVATION_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(raw) > MAX_OBSERVATION_BYTES:
        raise ValueError("Observation cache exceeds size limit")
    observation = json.loads(raw)
    validate_observation_source(observation, {"source_sha256": asset.sha256})
    _, frames = observation_samples(observation)
    if frames[-1]["time_ms"] >= asset.duration_ms or any(len(f["text"]) > 200 for f in frames):
        raise ValueError("Observations exceed source duration or supported caption length")
    return observation
