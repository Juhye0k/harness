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
from app.domain.transcript_review import quality
from app.domain.video import VideoError

MAX_AUDIO_BYTES = 25_000_000
BASE_URL = "https://api.groq.com/openai/v1"


def failure_diagnostics(response):
    """Only fixed codes/categories; never persist raw error bodies or credentials."""
    allowed = {
        "model_permission_blocked_org",
        "model_permission_blocked_project",
        "invalid_api_key",
        "insufficient_permissions",
        "organization_restricted",
        "access_denied",
        "rate_limit_exceeded",
        "empty_audio_file",
    }
    try:
        raw = response.json()
        error = raw.get("error", {}) if isinstance(raw, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        kind = "json"
    except ValueError:
        code = None
        kind = "html" if "html" in response.headers.get("content-type", "") else "other"
    return {
        "http_status": response.status_code,
        "provider_code": code if isinstance(code, str) and code in allowed else None,
        "response_kind": kind,
        "edge_error_1010": "1010" in response.text and "error" in response.text.lower(),
    }


def parse_transcription(raw):
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
            if not isinstance(segment["text"], str):
                raise ValueError()
            phrases.append(
                {
                    "offsetMilliseconds": round(start * 1000),
                    "durationMilliseconds": round(end * 1000) - round(start * 1000),
                    "text": segment["text"],
                    "quality": quality(segment),
                }
            )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise invalid() from exc
    from app.domain.word_alignment import recover

    source_segments = [
        {
            "id": f"s{index:04d}",
            "start_ms": phrase["offsetMilliseconds"],
            "end_ms": phrase["offsetMilliseconds"] + phrase["durationMilliseconds"],
            "text": phrase["text"],
        }
        for index, phrase in enumerate(phrases)
    ]
    aligned, report = recover(source_segments, raw.get("words"))
    for phrase, segment in zip(phrases, aligned, strict=True):
        if "words" in segment:
            phrase["words"] = segment["words"]
        else:
            phrase["word_timestamps_issue"] = "UNALIGNED_WORD_TIMESTAMPS"
    return {
        "phrases": phrases,
        "_normalized_word_timestamps": True,
        "_word_alignment": {k: v for k, v in report.items() if k != "segments"},
    }


def request_error(response):
    diagnostics = failure_diagnostics(response)
    # 403 alone is not evidence of an invalid credential.
    if response.status_code == 403 and diagnostics["provider_code"] != "invalid_api_key":
        error = VideoError(
            "PROVIDER_ACCESS_DENIED",
            "Groq가 요청 접근을 거부했습니다. 키 인증과 별도로 제공자 권한·요청 제한을 확인하세요.",
        )
    else:
        error = status_error(response.status_code)
    error.provider_diagnostics = diagnostics
    return error


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
                raise request_error(response)
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
        parsed = parse_transcription(raw)
        return parsed, {
            "provider": "groq",
            "model": GROQ_ASR_MODEL,
            "request_id": request_id,
            "usage": None,
            "cost": None,
            "version": GROQ_ASR_VERSION,
            "word_alignment": parsed["_word_alignment"],
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
