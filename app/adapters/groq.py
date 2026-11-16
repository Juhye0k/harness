"""Groq REST adapter. Free account confirmation is not a billing API guarantee."""

import json
import math

import httpx

from app.adapters.ai import (
    EVALUATE,
    GROQ_ASR_MODEL,
    GROQ_ASR_VERSION,
    GROQ_MODEL,
    PROMPT_VERSION,
    PROPOSE,
    SYSTEM,
    enabled,
    status_error,
)
from app.domain.recommendations import Proposals, Scores, invalid
from app.domain.subtitles import compact, validate_words
from app.domain.transcript_review import quality
from app.domain.video import VideoError

MAX_AUDIO_BYTES = 25_000_000
BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider:
    def __init__(self, settings):
        enabled(settings, "transcription")
        if not settings.enable_free_ai or not settings.groq_api_key.get_secret_value():
            raise VideoError("PROVIDER_CONFIG", "Groq 무료 모드와 API 키를 확인하세요.")
        self.key = settings.groq_api_key.get_secret_value()
        self.settings = settings

    def request(self, path, *, timeout, **kwargs):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.post(
                    BASE_URL + path,
                    headers={"Authorization": f"Bearer {self.key}"},
                    **kwargs,
                )
            if not 200 <= response.status_code < 300:
                raise status_error(response.status_code)
            raw = response.json()
            if not isinstance(raw, dict):
                raise invalid()
            return raw, response.headers.get("x-request-id")
        except httpx.TimeoutException as exc:
            raise VideoError("PROVIDER_TIMEOUT", "Groq 요청 시간이 초과되었습니다.") from exc
        except httpx.RequestError as exc:
            raise VideoError("PROVIDER_FAILED", "Groq 서버에 연결하지 못했습니다.") from exc
        except ValueError as exc:
            raise invalid() from exc

    def transcribe(self, audio):
        if not 0 < audio.stat().st_size <= MAX_AUDIO_BYTES:
            raise VideoError("LIMIT_EXCEEDED", "Groq 전사 파일은 25MB 이하여야 합니다.")
        with audio.open("rb") as file:
            raw, request_id = self.request(
                "/audio/transcriptions",
                timeout=180,
                files={"file": ("audio.mp3", file, "audio/mpeg")},
                data={
                    "model": GROQ_ASR_MODEL,
                    "language": "ko",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": ["word", "segment"],
                    "temperature": "0",
                },
            )
        try:
            segments = raw["segments"]
            if not isinstance(segments, list):
                raise ValueError()
            if len(segments) > 2000:
                raise VideoError("TRANSCRIPT_LIMIT", "전사 구간 제한을 초과했습니다.")
            phrases = []
            for segment in segments:
                start, end = segment["start"], segment["end"]
                if any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end)):
                    raise ValueError()
                if start < 0 or end <= start:
                    raise ValueError()
                phrases.append(
                    {
                        "offsetMilliseconds": round(start * 1000),
                        "durationMilliseconds": round(end * 1000) - round(start * 1000),
                        "text": segment["text"],
                        "quality": quality(segment),
                    }
                )
            words = raw["words"]
            if not isinstance(words, list) or len(words) > 60000:
                raise ValueError()
            cursor = 0
            for phrase in phrases:
                phrase["words"] = []
                covered = ""
                if not isinstance(phrase["text"], str):
                    raise ValueError()
                target = compact(phrase["text"])
                while len(covered) < len(target):
                    word = words[cursor]
                    start, end = word["start"], word["end"]
                    if any(
                        type(t) not in (int, float) or not math.isfinite(t) for t in (start, end)
                    ):
                        raise ValueError()
                    normalized = {
                        "text": word["word"],
                        "start_ms": round(start * 1000),
                        "end_ms": round(end * 1000),
                    }
                    if not isinstance(normalized["text"], str):
                        raise ValueError()
                    covered += compact(normalized["text"])
                    if not target.startswith(covered):
                        raise ValueError()
                    phrase["words"].append(normalized)
                    cursor += 1
                if target:
                    validate_words(
                        {
                            "text": phrase["text"],
                            "words": phrase["words"],
                            "start_ms": phrase["offsetMilliseconds"],
                            "end_ms": phrase["offsetMilliseconds"] + phrase["durationMilliseconds"],
                        }
                    )
            if cursor != len(words):
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
            raise invalid() from exc
        return {"phrases": phrases, "_normalized_word_timestamps": True}, {
            "provider": "groq",
            "model": GROQ_ASR_MODEL,
            "request_id": request_id,
            "usage": None,
            "cost": None,
            "version": GROQ_ASR_VERSION,
        }

    def recommend(self, stage, payload, model):
        enabled(self.settings, "recommendation")
        if model != GROQ_MODEL or stage not in ("proposal", "scoring"):
            raise VideoError("PROVIDER_CONFIG", "허용된 Groq 모델과 단계를 사용하세요.")
        schema = Proposals if stage == "proposal" else Scores
        raw, request_id = self.request(
            "/chat/completions",
            timeout=120,
            json={
                "model": model,
                "max_completion_tokens": 8000,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM + " " + (PROPOSE if stage == "proposal" else EVALUATE),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": stage,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
            },
        )
        try:
            choice = raw["choices"][0]
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError()
            if choice["finish_reason"] != "stop" or message.get("refusal"):
                raise ValueError()
            result = schema.model_validate_json(message["content"]).model_dump()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise invalid() from exc
        return result, {
            "provider": "groq",
            "model": raw.get("model", model),
            "configured_model": model,
            "request_id": request_id or raw.get("id"),
            "usage": raw.get("usage"),
            "cost": None,
            "prompt_version": PROMPT_VERSION,
        }
