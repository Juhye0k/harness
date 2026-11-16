# 데이터 모델과 작업 생명주기

> 상태: VIDEO-002 로컬 구현 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../README.md) · [카테고리 목차](README.md)

## 현재 테이블

`video_jobs`는 `app/models.py`와 Alembic `0001_video_jobs`가 정의한다. PostgreSQL은 상태의 기준이고 Redis에는 job_id만 전달한다.

| 필드 | 의미 |
|---|---|
| id / task_id | 제품 작업 UUID / 최초 Celery 전달 UUID |
| source_url / start_seconds / duration_seconds | 비공개 URL / 시작 초 / 고정 10초 |
| status | pending, queued, running, succeeded, failed |
| created_at / updated_at / started_at / finished_at | UTC 시각 |
| error_code / error_message | 공개 오류 코드·정제한 설명 |
| operator_reason | 관리자 중단 확인 사유, API 미노출 |
| run_id / output_path / result | 실행 ID / 저장 루트 상대 경로 / 검사 결과 JSONB |

영상은 공유 볼륨에 보관한다. 서버 경로·URL·원본 예외는 응답에서 제외한다. 프로젝트·자산·후보·자막·편집 버전·사용자 테이블은 후속 계획이다.

## 정상 전이와 선점

1. API가 입력을 검사한 후 pending을 별도 트랜잭션으로 저장한다.
2. 해당 행을 잠그고 Redis에 job_id를 발행한다. 성공하면 queued, 예외면 failed/DISPATCH_FAILED를 커밋한다.
3. 워커는 ID로 행 잠금을 기다린 뒤 queued인 경우에만 running으로 바꾼다. 성공한 워커만 실행한다.
4. 잠금을 해제한 상태로 다운로드·FFmpeg·출력 검증을 실행한다.
5. DB 상태가 여전히 running일 때만 succeeded 또는 failed를 저장한다.

발행 중인 pending 행에 상태 조건만 붙여 조회하면 미커밋 변경을 건너뛸 수 있어 먼저 ID로 잠근다. 동시 선점과 발행 성공·실패 경쟁은 실제 DB 검사로 확인한다. 인코딩 중에는 트랜잭션을 유지하지 않는다.

## 실패 계약

| 상황 | 저장·응답 | 처리 주체 |
|---|---|---|
| 유효성 실패 | HTTP 422, 작업 생성 전 거절 | API |
| DB 오류 | HTTP 503, 저장 여부 불확실할 수 있음 | API |
| 발행 예외 | failed, HTTP 503과 작업 ID | API |
| 구간·도구 실패·soft timeout | failed와 정제된 오류 | 워커 |
| 발행 중 API 종료 | pending 또는 queued 잔류 가능 | 자동 감지 없음 |
| 워커 전체 종료·hard timeout·완료 DB 실패 | running 잔류 가능 | 자동 감지 없음 |
| Redis 메시지 유실 | queued 잔류 가능 | 자동 복구 없음 |

DB와 Redis는 원자적 트랜잭션이 아니다. 메시지 전달 후 API가 종료되어 pending이 남으면 워커는 실행하지 않는다. 조기 ACK이므로 워커 종료 뒤 자동 재실행을 보장하지 않는다. [관리자 절차](../05-development/async-video-jobs.md)는 pending/running에 적용되고 늦은 완료가 실패를 덮어쓰지 못하도록 조건부 업데이트한다. 자동 감시·outbox·재시도·취소는 미구현이다.

## 파일과 확장

검증된 결과만 succeeded로 표시한다. 파일 생성 뒤 DB 기록이 실패하면 파일이 남아도 다운로드를 허용하지 않는다. 파일 정리 작업은 아직 없다. 다중 호스트·자동 재시도 전에는 객체 저장소·시도 ID·오래된 작업의 부작용 방지를 함께 설계한다. [ADR-003](../04-decisions/adr-003-redis-celery.md)에 결정 근거를 기록한다.
## VIDEO-004 데이터 추가

`assets → transcripts`, `assets → analysis_jobs → highlight_candidates → video_jobs`로 연결한다. `provider_calls`는 분석·단계별 호출 기록이다. 원본·음성·결과 파일은 공유 볼륨, 상태·전사·점수는 PostgreSQL에 저장한다. [실행 계약](../05-development/highlight-recommendations.md)에 선점·재사용·비용 제어를 정리한다.

분석 큐와 영상 큐를 분리하며 ID만 Redis로 전달한다. 후보별 video_jobs 고유 제약과 후보 행 잠금으로 동시 선택 시 하나의 출력 작업만 만든다. 후보·성공 상태를 원자적으로 저장하고 running 조건부 완료로 늦은 결과가 운영자 실패 확정을 덮어쓰지 못하게 한다. 외부 호출 동안 DB 트랜잭션을 유지하지 않는다.

## SNS-006 데이터 추가

`sns_oauth_states`는 세션 소유자·state 해시·만료·암호화한 PKCE 검증값을 저장한다. `sns_accounts`는 채널·연결 버전·암호화한 refresh token을 보관한다. `sns_uploads`는 성공 영상 작업과 계정·출력 해시·제목·공개 범위·아동용 여부·최종 확인 시각을 연결한다. 토큰·업로드 세션 주소를 API나 Redis 메시지에 넣지 않는다.

계정 행 잠금과 확인된 출력의 부분 고유 인덱스로 같은 계정·작업·버전이 한 번만 전송되게 한다. 초안은 발행하지 않으며, 최종 확인 트랜잭션 중 발행한 메시지는 행 잠금을 기다린 뒤 queued만 선점한다. 전송 중 트랜잭션을 유지하지 않는다. 원격 결과 미확정은 unknown을 유지하고 같은 세션의 빈 상태 조회만 허용한다. 조기 ACK·자동 재시도 없음이며 강제 종료 시 running이 남을 수 있다. [중단 확인·제한](../05-development/youtube-upload.md)을 따른다.
