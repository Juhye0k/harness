# 현재 API 계약

> 상태: VIDEO-002 로컬 구현 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

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

웹 업로드·소유권·AI 추천·자막 편집·SNS API는 미구현이다. 파일 보존과 다운로드 인증은 외부 사용자 테스트 전에 확정한다.
## VIDEO-004 추천 API 추가

기존 API 계약에 아래 비동기 추천 흐름을 추가한다. [실행 계약](../05-development/highlight-recommendations.md)을 기준으로 한다.

| 요청 | 입력·응답 |
|---|---|
| POST /analyses | url 또는 준비된 asset_id 중 하나, genre, purpose. 202와 analysis_id·status_url 반환. AI 비활성 시 503 |
| GET /analyses/{id} | 상태·단계·분석 근거·후보·기존 export_job_id. 원본 URL·파일 경로·비밀값 제외 |
| POST /analyses/{id}/candidates/{candidate_id}/exports | 저장된 후보 시간으로 추출 작업 생성. 반복 호출은 기존 작업 ID 반환 |
| GET /jobs/{id}, /jobs/{id}/download | 기존 상태·검증된 출력 다운로드 계약 재사용 |

추천 접수 발행 실패도 추적 가능한 202 리소스를 반환하며 조회 상태는 failed/DISPATCH_FAILED다. 같은 URL의 별도 분석 접수는 별도 자산을 만들며, 기존 파일 재사용은 asset_id를 명시한다. 인증·사용자별 소유권 검사는 아직 없으므로 로컬에서만 사용한다.
