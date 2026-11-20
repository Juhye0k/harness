# 현재 API 계약

> 클라이언트가 어떤 요청을 보내고 어떤 상태·오류를 받아야 하는지 정리합니다. 영상 접수·분석·자막·SNS API의 입력과 결과를 찾아볼 때 사용하는 계약 문서입니다.

API는 영상 입력·분석 접수·편집·출력·조회를 연결한다. 202 응답은 접수 완료이며 처리 완료가 아니다. 현재 엔드포인트와 오류 조건을 찾을 때 이 문서를 사용한다.

## 로컬 파일 업로드

UPLOAD-001은 `POST /assets/uploads`, raw 바이트 `PUT /assets/{id}/content`, `GET /assets/{id}/upload`를 제공한다. 영상 검사는 worker에서 수행하며 ready인 asset_id는 기존 추출·분석 입력으로 재사용한다. 크기·상태·권한·삭제 경계는 [업로드 계약](../05-development/local-video-upload.md)을 따른다.

## 전사 검수 API

`GET /analyses/{id}/transcript-review`, `PUT /analyses/{id}/transcript-review/{segment_id}`, `GET /analyses/{id}/review-audio`를 추가했다. 조회·재생은 읽기 전용이며 판정은 전사·정책 버전과 revision으로 저장한다. 완료 전/버전·동시 저장 충돌은 409, 없는 분석·구간·음성은 404다. [입력·정책·경계](../05-development/transcript-review.md)를 따른다.


[위키 홈](../README.md) · [카테고리 목차](README.md)

인증 없는 localhost 개발 API다. `/docs`, `app/api/jobs.py`, `app/main.py`를 기준으로 한다.

| 메서드·경로 | 응답 | 의미 |
|---|---|---|
| GET /health/live | 200 | API 생존 |
| GET /health/ready | 200 / 503 | DB·Redis 연결, 워커 생존은 미확인 |
| POST /jobs/video-extractions | 202 | 10초 추출 접수 |
| GET /jobs/{job_id} | 200 / 404 | 상태·시각·검사·공개 오류 |
| GET /jobs/{job_id}/download | 200 / 404 / 409 / 410 | 검증된 MP4 다운로드 |

## 접수

```json
{"url":"https://media.w3.org/2010/05/sintel/trailer.mp4","start_seconds":5}
```

길이는 10초 고정이다. URL은 기존 CLI의 공개 YouTube 단일 영상·MP4 직접 링크 제한을 따른다. 음수·NaN·무한대 시작 시간은 422다. 실제 영상 길이를 알아야 하는 범위 오류는 워커에서 실패로 기록한다.

```json
{"job_id":"UUID","status":"queued","status_url":"http://localhost:8000/jobs/UUID"}
```

202는 완료가 아니다. 같은 요청을 다시 보내면 새 ID가 생긴다. 요청 중복 키는 아직 지원하지 않는다.

## 조회와 오류

조회는 job_id, status, start_seconds, duration_seconds, UTC 시각 네 종류, error, result, download_url을 반환한다. 미완료 result/download_url은 null이다. 성공 result는 media와 checks이며 길이·영상·음성 유지·디코딩·원본 보존 검사만 공개한다. URL·서버 경로·관리 사유는 반환하지 않는다.

- 422: 입력 형식·URL·시작 시간 오류. 원본 입력을 반사하지 않는다.
- 503: DATABASE_UNAVAILABLE 또는 DISPATCH_FAILED. 생성된 ID가 확인되면 job_id도 반환한다.
- 404: JOB_NOT_FOUND.
- 409: RESULT_NOT_READY. 실패한 작업도 다운로드할 수 없다.
- 410: RESULT_UNAVAILABLE. 파일이 없거나 저장 루트 밖이면 제공하지 않는다.

영상 실패는 조회 HTTP 200 안의 status=failed와 error로 표현한다. 접수 HTTP 성공과 작업 성공을 구분한다. [실행 예시](../05-development/async-video-jobs.md), [상태 계약](data-and-jobs.md).

웹 파일 업로드·자막 편집·사용자별 자료 소유권은 로컬 구현했다. 아래 추가 계약과 [업로드](../05-development/local-video-upload.md)·[전체 흐름](../05-development/complete-flow.md)·[인증/자료 관리](../05-development/user-auth-data.md)를 따른다. 운영 배포는 별도 검증한다.
## VIDEO-004 추천 API 추가

기존 API 계약에 아래 비동기 추천 흐름을 추가한다. [실행 계약](../05-development/highlight-recommendations.md)을 기준으로 한다.

| 요청 | 입력·응답 |
|---|---|
| POST /analyses | url 또는 준비된 asset_id 중 하나, genre, purpose. 202와 analysis_id·status_url 반환. AI 비활성 시 503 |
| GET /analysis-requests/{request_id} | 현재 사용자 범위에서 기존 접수를 조회. 미확인 404, 만료/삭제 410. 작업 생성·재발행 없음 |
| GET /analyses/{id} | 상태·단계·분석 근거·후보·기존 export_job_id. 원본 URL·파일 경로·비밀값 제외 |
| POST /analyses/{id}/candidates/{candidate_id}/exports | 저장된 후보 시간으로 추출 작업 생성. 반복 호출은 기존 작업 ID 반환 |
| GET /jobs/{id}, /jobs/{id}/download | 기존 상태·검증된 출력 다운로드 계약 재사용 |

### VIDEO-005 전사 전용 모드

`POST /analyses`는 선택 UUID `request_id`를 지원한다. 같은 사용자·같은 입력은 기존 분석을 반환하고 다른 입력이면 409다. 웹은 전송 전에 번호를 저장하고 응답 유실·새로고침 시 조회로 복원한다. receipt는 7일이며 만료 후 재접수하지 않는다. 설정 검증과 신규 분석/receipt 저장은 하나의 DB 트랜잭션이며 외부 호출은 없다. 발행 이후 강제 종료는 자동 재발행하지 않고 관리자 절차를 따른다.

`POST /analyses`의 `mode`는 `transcription` 또는 `recommendation`이며 API 생략 기본값은 기존 호환을 위해 recommendation이다. 웹은 transcription을 기본 선택한다. 전사 전용은 LLM을 호출하지 않고 `TRANSCRIBED` 또는 `NO_SPEECH`로 완료한다. 추천 제공자 none일 때 recommendation 요청은 DB 작업 생성 전 `503 RECOMMENDATION_DISABLED`로 거절한다.

`GET /analyses/{id}/transcript`는 `analysis_id`, `asset_id`, `version`, `segments`를 반환한다. 각 구간은 `id/start_ms/end_ms/text`다. 분석 성공 시와 후보 제안·채점에서 실패했더라도 성공한 전사가 저장된 경우에 읽을 수 있다. 전사에 도달하지 못했거나 전사에서 실패한 분석은 409, 분석 또는 저장 전사가 없으면 404다. 표시 자막과 SRT 조회에도 같은 기준을 적용한다. 조회는 전사 선점이나 외부 호출을 만들지 않는다. [전사 설정과 실행](../05-development/groq-free-ai.md).

추천 접수 발행 실패도 추적 가능한 202 리소스를 반환하며 조회 상태는 failed/DISPATCH_FAILED다. 같은 URL의 별도 분석 접수는 별도 자산을 만들며, 기존 파일 재사용은 asset_id를 명시한다. 인증·사용자별 소유권 검사는 아직 없으므로 로컬에서만 사용한다.

## 표시 자막 API

`GET /analyses/{id}/subtitles`는 원본 전사와 별개인 표시 cues·정책 버전·검토 사유를, `GET /analyses/{id}/subtitles.srt`는 같은 cues의 UTF-8 SRT를 반환한다. 완료 전 409, 원본 시간 기준이며 후보 MP4 시각으로 이동하지 않는다. 전사·작업 생성·외부 호출을 하지 않는다. [상세 계약](../05-development/subtitle-segmentation.md).

### 후보 편집과 출력

| 요청 | 계약 |
|---|---|
| GET /analyses/{a}/candidates/{c}/editor | 저장 전사·초안·`alignment`·최근 두 버전 중 최신 본문과 직전 ID·현재 `export_profile`. 새 작업 생성 없음 |
| POST /analyses/{a}/candidates/{c}/caption-revisions | 표시 규칙·전사 버전 검사 후 불변 버전 반환. `expected_latest_revision_id`는 조회한 버전 UUID이며, 명시적 null은 아직 저장본이 없어야 한다는 뜻. 최신 버전 충돌은 409 `REVISION_CONFLICT` |
| GET /analyses/{a}/candidates/{c}/caption-revisions/{r} | 확정 여부와 연결 출력의 ID·`render_profile`을 포함한 해당 버전 조회 |
| POST /analyses/{a}/candidates/{c}/caption-revisions/{r}/exports | 미확정이면 409 `SUBTITLE_REVIEW_REQUIRED`. 빈 본문은 v2. `source_captions`로 원본 해시와 확인된 표시 구간을 제공할 수 있으며 같은 입력은 같은 작업 반환 |
| GET /jobs/{j}/subtitles.srt | 성공한 편집 출력과 동일한 자막 버전 전체를 클립 시간 기준 UTF-8 SRT로 반환 |

[편집·출력 상세](../05-development/complete-flow.md) · [화면 관측과 정렬 조건](../05-development/source-caption-evaluation.md).

## SNS-006 YouTube 업로드 API

상세 입력·설정·제한은 [YouTube 계약](../05-development/youtube-upload.md)을 따른다. `/sns/session`의 HttpOnly 쿠키와 반환된 CSRF 토큰이 필요하다. 변경 요청은 `X-SNS-CSRF` 헤더를 보내며 설정한 로컬 Origin 외의 접근은 거부한다. SNS 계정·업로드만 브라우저 세션에 속하며, 기존 영상 소유권·일반 사용자 인증은 제공하지 않는다.

| 요청 | 의미 |
|---|---|
| GET /sns | 계정 연결·확인·상태 화면 |
| GET /sns/session | 세션 쿠키와 csrf·enabled 반환, 전송 없음 |
| POST /sns/youtube/connect | 10분·1회 state와 PKCE를 가진 Google 동의 URL |
| GET /sns/youtube/callback | state 검증·코드 교환·채널 저장 후 결과 화면으로 303 이동 |
| GET /sns/accounts | 해당 세션의 연결된 채널·연결 버전, 토큰 제외 |
| DELETE /sns/accounts/{id} | 로컬 토큰 삭제·연결 버전 변경, 진행 중 전송 취소 아님 |
| POST /sns/uploads | request_id·account_id·job_id·title·made_for_kids, privacy 기본 private. 201 확인 초안, 전송 없음 |
| GET /sns/uploads/{id} | 상태·approval·계정 표시값·오류 코드·영상 URL, 비밀값·경로 제외 |
| POST /sns/uploads/{id}/confirm | confirmed=true·서버 초안과 같은 approval. 202 추적 리소스, 반복 요청은 기존 작업 |
| POST /sns/uploads/{id}/probe | unknown의 기존 세션만 조회하는 작업 접수. 영상 재전송 없음 |

없는 계정·다른 세션 리소스는 404, 승인 불일치·만료·중복 설정 변경은 409, 입력 오류는 422, 기능 비활성화·설정 누락은 503이다. 확인 발행 실패는 202 응답의 failed/DISPATCH_FAILED로 추적하며 같은 출력의 자동 재요청을 허용하지 않는다. 응답 미확인은 같은 초안 주소의 GET으로 확인한다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: VIDEO-002 로컬 구현 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

</details>
