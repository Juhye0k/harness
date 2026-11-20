# Groq 무료 전사·추천 설정

> 음성 전사와 추천은 각각 켜고 끌 수 있으며, 저장된 전사를 추천에 재사용합니다. Groq 설정·무료 계정 확인·호출 제한과 실패 시 유료 제공자로 전환하지 않는 동작을 설명합니다.

[위키 홈](../README.md) · [개발 목차](README.md)


## 선택과 범위

예산 0원·로컬 LLM 미사용 요구에 따라 우선 Groq Free 계정의 `whisper-large-v3-turbo`로 전사만 확인한다. 전사 제공자와 추천 제공자는 별도 설정이며 추천 기본값은 `none`이다. 나중에 Groq 추천을 선택하면 `openai/gpt-oss-120b`를 호출한다. 모델명에 openai가 있어도 호출 대상은 Groq다. 무료 계정·모델 접근·한도는 콘솔에서 확인한다.

Azure·OpenAI로 자동 전환하지 않는다. Gemini 비교, 음성 분할, 자막 편집·SNS는 이번 범위가 아니다. 무료 계정을 유료로 업그레이드하면 동일 API도 과금될 수 있다. 확인 플래그는 계정 과금 상태를 조회하거나 0원을 보장하는 기능이 아니다.

## 설정과 실행

1. [Groq Console](https://console.groq.com/)에서 Free 상태인지 확인하고 API 키를 만든다. 결제 업그레이드·결제수단 등록은 하지 않는다.
2. 기존 `.env`를 보존하고 아래 항목만 편집한다. 파일이 없을 때만 `.env.example`을 복사한다. 키를 채팅·Git·Wiki에 넣지 않는다.

```dotenv
ENABLE_PAID_AI=false
ENABLE_FREE_AI=true
GROQ_FREE_TIER_CONFIRMED=true
GROQ_API_KEY=여기에_로컬에서_입력
TRANSCRIPTION_PROVIDER=groq
RECOMMENDATION_PROVIDER=none
```

3. `uv run python -m scripts.evaluate_recommendations preflight`로 설정 여부만 확인한다. 키 값은 출력하지 않으며 인증·무료 잔량을 검사하는 명령은 아니다.
4. `docker compose up --build -d`로 실행한다. 키는 분석 워커에만 전달한다.
5. `http://localhost:8000/recommendations`에서 기본 선택인 **음성 전사만 확인**으로 실행한다. 외부 전송이 허용된 한국어 대화·인터뷰 1~3분으로 시작한다. 음성만 Groq 전사 API로 보내며 추천 API에는 대사를 보내지 않는다.
6. 결과의 시작·종료 시간과 대사를 원본 음성과 비교한다. 페이지 새로고침은 저장된 전사를 읽으며 새 전사를 발행하지 않는다.

## 전사와 추천 분리

`TRANSCRIPTION_PROVIDER`는 `groq` 또는 `azure`, `RECOMMENDATION_PROVIDER`는 `none`, `groq`, `openai`다. 현재 예산 0원에서는 `groq`/`none`을 사용한다. 무료·유료 스위치를 동시에 켜는 조합은 차단하며 유료 제공자는 별도 허용 없이 호출하지 않는다. Claude·Gemini·로컬 Whisper 어댑터는 아직 없다.

API는 `POST /analyses`에 `mode: "transcription"`을 명시한다. 웹 기본값은 전사지만 기존 API 호환을 위해 mode 생략 시 추천 요청으로 취급한다. 추천 제공자가 none인 상태에서 추천을 요청하면 작업 생성 전에 `503 RECOMMENDATION_DISABLED`로 거절한다.

```json
{"url":"https://example.com/authorized-sample.mp4","mode":"transcription"}
```

완료 후 `GET /analyses/{id}/transcript`에서 `id/start_ms/end_ms/text` 구간 목록을 읽는다. 전사만 성공하면 `TRANSCRIBED`, 무음은 `NO_SPEECH`다. 후보 제안이나 채점에서 중단돼도 전사가 성공했다면 같은 프로젝트에서 전사와 표시 자막을 읽을 수 있다. GET은 작업·전사 선점을 생성하지 않는다. 인증을 끈 개발 모드는 외부 공개하지 않는다. 계정별 접근 설정은 [인증 안내](user-auth-data.md)를 따른다.

추천 실험 시 `RECOMMENDATION_PROVIDER=groq`로 변경하고 API·분석 워커를 재생성한다. 준비된 `asset_id`와 `mode: "recommendation"`을 제출하면 동일 전사 버전을 재사용한다. 새 URL 접수는 별도 자산이므로 재사용을 보장하지 않는다. 실제 품질 기록은 [평가 기준선](recommendation-quality-baseline.md)을 따른다.

추천 프로필 `groq-records-low-2048-v1`은 같은 120B 모델을 유지하며 전사 ID·시간·문장을 텍스트 레코드로 전달한다. Groq가 공식 지원하는 OpenAI 호환 SDK를 Groq 주소에만 연결하고 재시도를 0회로 고정한다. 유료 OpenAI 호출이 아니다. 낮은 추론 강도·출력 상한 2,048토큰·제안 최대 5개를 사용하며 원문·응답 스키마·범위·근거 검증은 유지한다. 프로필을 작업 설정과 호출 메타데이터에 기록하고 명시적인 프로필 드리프트를 거부한다.

2026-11-17 승인된 전체 전사 1건으로 해당 프로필의 실제 후보 생성·채점 성공을 확인했다. 단, 동일 조건 A/B에서 기존 JSON 입력도 200이었으므로 JSON 중첩만이 403의 원인이라고 단정하지 않는다. 합성 입력의 413과 후속 비교의 429도 관측했다. 403의 Groq 내부 접근 제어 규칙은 미확정이며, 특정 샘플의 성공을 계정·네트워크 제한이 항상 해제됐다는 보장으로 해석하지 않는다. [상세 실험 기록](harness/records/2026-11-17-recommendation-manual-review.md).

## 구현과 하네스

| 파일 | 역할 |
|---|---|
| `app/config.py`, `compose.yaml` | 무료 모드·계정 확인·키 주입 |
| `app/adapters/ai.py` | 제공자 선택. 무료·유료 모드 동시 활성화 거부 |
| `app/adapters/groq.py` | 고정 HTTPS 주소·모델 제한·HTTP 오류 변환 |
| `app/services/analysis.py` | 전사 캐시·MP3 전처리·호출 전 단계 기록 |
| `tests/unit/test_groq_provider.py` | 인증·한도·시간 초과·응답 불량·유료 대체 호출 방지 |
| `tests/integration/fixture_analysis_worker.py` | 실제 MP3 코덱·16kHz·mono·크기 검사. AI만 대역 사용 |

첫 음성 트랙을 mono 16kHz·64kbps MP3로 변환한다. 20분은 대략 9.6MB이며 전송 전 실제 파일 크기를 25,000,000바이트 이하로 검사한다. 압축에 따른 전사·시간 경계 품질은 실제 평가 대상이다. 무음·순서·원본 범위는 기존 정규화 규칙을 적용한다.

작업에 mode·전사/추천 제공자·모델·전사 버전을 저장한다. 전사 작업에는 추천 제공자 none, 추천 모델 null을 고정한다. 필요한 제공자가 대기 중 바뀌면 실패하고 몰래 다른 제공자를 사용하지 않는다. 전사 전용 작업은 추천 설정 변경의 영향을 받지 않는다. 이전 Groq 작업은 기존 provider 필드로, 그 이전 작업은 Azure·OpenAI로 해석한다. 전사는 최대 1회, 추천 모드에만 제안·평가 각 1회를 허용하며 재시도는 없다. 전사 180초, 추천 120초와 Celery 전체 실행 제한을 유지한다.

401과 명시적인 잘못된 키 응답은 `PROVIDER_AUTH`, 나머지 403은 `PROVIDER_ACCESS_DENIED`다. 403만으로 키가 잘못됐다고 단정하지 않는다. 429는 `PROVIDER_RATE_LIMIT`, 시간 초과는 `PROVIDER_TIMEOUT`, 잘못된 JSON·시간 정보는 `MODEL_RESPONSE_INVALID`다. 비용은 미측정 `null`, 사용량은 제공된 값만 기록한다.

## 검증과 남은 제한

일반 CI는 실제 API에 접속하지 않는다. 계정 가용성·한국어 인식률·추천 유용성·실제 지연은 승인된 영상으로 평가해야 한다. 테스트 통과를 품질 평가 완료로 해석하지 않는다. 사용자별 할당량 없는 로컬 개발용이며 공개 운영용 무료 비용 차단 시스템은 아니다.

공식 문서 확인일 2026-11-15: [전사·25MB 제한](https://console.groq.com/docs/speech-to-text), [구조화 출력 모델](https://console.groq.com/docs/structured-outputs), [무료/유료 전환](https://console.groq.com/docs/billing-faqs), [한도](https://console.groq.com/docs/rate-limits), [데이터 정책](https://console.groq.com/docs/your-data).

새 Groq 전사는 word+segment 요청의 v2 캐시를 사용한다. v1은 보존하며 과거 성공한 분석에서 조회한다. 원본 영상 시간 기준 SRT의 [분할·구버전 계약](subtitle-segmentation.md)을 확인한다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 연동 구현 / 실제 계정 호출·한국어 품질 미검증 · 기준일: 2026-11-15

</details>
