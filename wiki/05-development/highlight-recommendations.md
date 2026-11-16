# 하이라이트 추천 실행과 검증 — VIDEO-004

> 상태: 구현·로컬 검증 완료 / 실제 모델 품질 미평가 · 기준일: 2026-11-15

[위키 홈](../README.md) · [개발 목차](README.md)

## 사용자 흐름

전사만 먼저 확인하려면 웹의 기본 작업 **음성 전사만 확인**을 사용한다. 이 경우 추천 대신 시간별 대사를 반환한다. 전사·추천의 독립 설정과 API는 [Groq 실행 안내](groq-free-ai.md)를 따른다. 아래 후보·점수 흐름은 하이라이트 추천 모드에 적용한다.

`/recommendations`에서 공개 영상 URL, 장르, 추천 목적을 입력한다. 서버는 원본을 한 번 내려받고 한국어 음성을 전사한 후 30~60초 후보를 최대 5개 추천한다. 사용자가 후보를 선택하면 해당 구간만 인코딩하고 기존 작업 화면에서 미리보기·MP4 다운로드를 제공한다. 추천 점수는 편집 적합도이며 조회수나 바이럴 확률이 아니다.

현재 입력 한도는 20분·500MiB다. 한국어 대화·인터뷰를 첫 품질 평가 대상으로 삼는다. 드라마·영화·게임·예능·스포츠는 장르 메타데이터를 받지만 영상 장면, 표정, 게임 이벤트, 음량 변화는 아직 분석하지 않는다. 자막 편집·SNS 업로드도 후속 단계다.

## 실행 설정

기본은 두 AI 스위치가 모두 false이며 추천 접수를 `503 AI_DISABLED`로 거부한다. 기존 10초 추출은 그대로 사용할 수 있다. 현재 권장 경로는 [Groq 무료 모드 설정](groq-free-ai.md)이다. 아래 Azure·OpenAI 설정은 기존 유료 경로에만 적용하며 무료 모드의 대체 경로로 호출하지 않는다. 테스트에는 키가 필요 없다.

| 환경 변수 | 의미 |
|---|---|
| ENABLE_PAID_AI | 실제 분석 허용 스위치. 기본 false |
| AZURE_SPEECH_ENDPOINT | `https://<resource>.cognitiveservices.azure.com` |
| AZURE_SPEECH_KEY | 분석 워커에만 주입하는 비밀값 |
| OPENAI_API_KEY | 분석 워커에만 주입하는 비밀값 |
| RECOMMENDATION_MODEL | 기본 gpt-5.6-terra; 접수 시 설정을 작업에 고정 |

`docker compose up --build -d`는 migration, API, 영상 워커, 분석 워커, PostgreSQL, Redis를 실행한다. `/recommendations?analysis=<UUID>`는 저장된 분석을 복원하며 GET·새로고침으로 새 분석을 생성하지 않는다. 배포용 인증·사용자별 접근 제어가 없으므로 로컬 개발용이다.

## 파이프라인과 저장 경계

1. `assets`: 원본 상대 경로, SHA-256, 길이, 음성 유무를 저장한다. 파일 바이트는 공유 볼륨에 있다.
2. FFmpeg로 첫 음성 트랙을 mono 16kHz로 만든다. Groq는 64kbps MP3, 기존 Azure는 PCM WAV다. 전사 버전별 디렉토리로 파일 충돌을 막는다.
3. Groq Whisper 또는 Azure Fast Transcription 결과를 `id/start_ms/end_ms/text` 전사로 정규화한다. `transcripts`의 `(asset_id, version)` 고유 제약으로 중복 전사 호출을 막고 제공자·전처리 버전을 분리한다. 진행 중이거나 실패한 전사는 자동 재호출하지 않는다.
4. 선택한 제공자의 제안 호출에 전사와 장르·목적을 전달한다. 최대 15개 구간 ID 쌍을 받고 서버가 시간을 계산한다. 30~60초 범위, 순서, 원본 경계를 검사하고 최대 200ms씩 여유를 추가한다. 최종 60초 상한을 유지한다.
5. 별도 평가 호출로 도입·완결성·독립성·인상·편집성 점수를 각각 0~4로 받는다. 근거 ID가 해당 후보에 속하는지도 검사한다.
6. 서버가 `25/25/20/20/10` 가중치로 100점 점수를 계산한다. 완결성·독립성 2점 미만은 제외한다. 점수 내림차순·시작 시간·후보 ID 순으로 정렬하고 짧은 후보 길이 대비 겹침 50% 이상을 제거한다. 동일 주제는 최대 2개, 최종 최대 5개다.
7. 최종 후보와 분석 성공 상태는 같은 DB 트랜잭션에서 확정한다. `highlight_candidates`에는 제목·구간·전사·근거·세부 점수·순위를 저장한다.
8. 후보 선택 시 `video_jobs`를 만들며 같은 후보의 재요청은 기존 작업 ID를 반환한다. 실패한 출력도 자동 재실행하지 않는다. 파일이 없으면 재다운로드하지 않고 오류로 남긴다.

기존 추출은 기본 10초를 유지한다. 추천 출력만 저장된 후보의 가변 길이를 사용한다. 모든 출력은 길이 ±0.1초, 영상·음성, 디코딩, 원본 해시 검사를 통과해야 한다.

## 실패·비용 제어

분석 큐와 영상 큐는 별도 워커가 처리하며 기본 동시성은 각각 1이다. Redis에는 ID만 전달한다. 분석도 `pending → queued → running → succeeded/failed` 조건부 선점을 적용한다. 발행과 선점 경쟁은 DB 행 잠금으로 조정하며 외부 AI 호출 중에는 DB 잠금을 잡지 않는다.

분석당 전사 1회, 제안 1회, 평가 1회가 상한이다. OpenAI SDK 재시도는 0이며 응답 보정 호출을 하지 않는다. 전사는 최대 2,000구간·60,000자다. OpenAI 호출은 출력 8,000토큰·120초, Azure는 180초 제한을 둔다. 분석 워커 soft/hard 제한은 960/1020초, Redis visibility timeout은 1200초다. HTTP 제한은 연결·읽기 단계 제한이며 작업 전체 상한은 Celery가 적용한다.

`provider_calls`는 단계당 고유 기록을 호출 전에 만들고 관측된 응답 모델·요청 ID·사용량·경과 시간·성공/실패를 기록한다. 비용이 제공되지 않으면 null로 남긴다. 원문 응답·비밀값은 오류 메시지나 로그에 넣지 않는다. `store=false`는 OpenAI 응답 저장 옵션이며 모든 제공자의 데이터 보존 정책을 대신하는 보장은 아니다.

무음 전사는 성공한 빈 결과 `NO_SPEECH`, 적절한 후보 없음은 `NO_SUITABLE_CANDIDATES`다. 음성 트랙 없음은 `NO_AUDIO`, 모델 형식/범위 불량은 `MODEL_RESPONSE_INVALID`다. 인증, 요청 제한, 시간 초과를 별도 오류 코드로 구분한다. 통신 조회 오류를 분석 실패로 바꾸지 않는다.

프로세스 강제 종료는 자동 감지·복구하지 않는다. 실제 실행 중단을 확인한 운영자는 다음 명령으로 pending/running 상태만 실패 확정한다. 늦게 도착한 완료 응답은 실패 상태를 덮어쓰지 않는다. 이 명령은 전사 선점을 해제하거나 유료 호출을 재시도하지 않는다.

```sh
uv run python -m app.cli.fail_job <analysis-id> --analysis --confirmed-stopped --reason "중단 확인 사유"
```

## 검증

```sh
uv run python scripts/verify.py
docker compose -f compose.integration.yaml build runner
docker compose -f compose.integration.yaml up --no-build -d api worker analysis-worker
docker compose -f compose.integration.yaml run --rm runner
docker compose -f compose.integration.yaml down -v
```

통합 검사는 격리된 테스트 볼륨의 합성 영상과 전사·추천 대역을 사용한다. 실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium을 거친다. 외부 모델 API의 실제 품질·지연·요금·계정 가용성은 일반 CI 성공으로 증명되지 않는다. 실제 샘플 평가는 별도 승인된 입력·제공자·예산으로 진행한다.

제품 규칙은 `app/domain/recommendations.py`, 외부 호출은 `app/adapters/ai.py`, 상태 저장은 `analysis_repository.py`, 단계 연결은 `app/services/analysis.py`에 있다. 하네스는 AGENTS 규칙, `tests/unit/test_recommendations.py`, `test_ai_providers.py`, `tests/integration/test_analysis_flow.py`, 기존 CI 필수 검사로 구성한다.

전사·추천 완료 뒤 표시 자막·SRT를 제공한다. 원본과 별도 계산하며 구버전 단어 시각이 없으면 추정 없이 검토 필요로 표시한다. [표시 자막 계약](subtitle-segmentation.md)에 캐시 버전·초안·제한을 정리했다. 내용 편집·영상 합성은 후속 범위다.
