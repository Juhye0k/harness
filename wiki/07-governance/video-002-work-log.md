# VIDEO-002 구현·검증·게시 기록

> 상태: 기능 구현·게시 기록 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../README.md) · [관리 목차](README.md)

## 목적과 범위

기존 링크 기반 10초 추출을 HTTP 접수와 백그라운드 작업으로 연결한다. 사용자는 작업 ID를 받아 상태를 조회하고 검증된 MP4를 다운로드한다. 시작 기준은 `000fee0`, 작업 브랜치는 `feat/video-002-async-extraction`이다. main 병합·배포는 이번 게시 범위가 아니다.

## 구현 결과

| 구분 | 변경과 책임 |
|---|---|
| HTTP | 접수 202, 상태 조회, 검증된 결과 다운로드. 입력·DB·발행·파일 오류 구분 |
| 작업 상태 | PostgreSQL video_jobs와 Alembic migration. pending → queued → running → succeeded/failed |
| 전달·실행 | Redis에 job_id 전달, Celery가 기존 영상 서비스 호출. 같은 ID는 조건부 선점 성공 시에만 실행 |
| 실패 관리 | 공개 오류 메시지 정제, 중단 확인 후 pending/running 수동 실패 처리, 늦은 완료 덮어쓰기 방지 |
| 실행 환경 | FFmpeg·Deno 포함 이미지, 마이그레이션 선행, 공유 영상 볼륨의 API 읽기 전용 연결 |
| 개발 하네스 | API 단위 검사, 실제 DB 경쟁 검사, 격리된 영상 통합 검사, CI·요구사항 연결표 |

세부 계약은 [API](../03-architecture/api-contract.md), [상태 모델](../03-architecture/data-and-jobs.md), [실행 안내](../05-development/async-video-jobs.md)에 둔다. [ADR-003](../04-decisions/adr-003-redis-celery.md)에 Streams 대신 Celery를 선택한 근거와 확장 조건을 기록했다.

## 검증과 발견 사항

- 기본 검사 82개와 Ruff·서식·Alembic 오프라인 검사 통과.
- 별도 PostgreSQL·Redis·Celery·FFmpeg 컨테이너에서 통합 검사 13개 통과. 다운로드만 합성 샘플로 대체하며 HTTP·대기열·DB·인코딩은 실제 실행한다.
- 일반 이미지에서 공개 MP4의 5초 위치부터 10.0초 추출, 음성 유지·디코딩·원본 보존·HTTP 다운로드 확인.
- `alembic check`에서 추가 migration 차이 없음. 일반 이미지에 tests가 포함되지 않음을 확인했다.
- 발행 커밋 전 소비자가 queued 조건만 검사하면 행을 건너뛸 위험이 있어 ID 잠금 후 조건부 UPDATE를 사용했다. 발행 성공·실패와 동시 선점을 실제 DB로 검증한다.
- 통합 빌드의 tests 제외 문제를 테스트 전용 이미지 단계로 해결했다. Windows 임시 경로 권한 오류가 있던 검사는 격리 Linux 환경에서 전체 통과했다.

원본 로그·영상·환경 비밀값은 Git에 포함하지 않는다. [하네스 연결표](../05-development/harness/video-002-requirements.md)에 각 요구사항과 검사 위치를 연결했다.

## 게시와 후속 확인

후속 기록: [PR #1](https://github.com/Juhye0k/short-form/pull/1)이 main에 병합됐다. 아래 항목은 최초 기능 브랜치 게시 당시의 검증 기록이다.

기능 브랜치에 코드·검사·문서 원본을 함께 게시하고, GitHub Wiki는 별도로 동기화한다.

- 구현 커밋: [32e992c — 비동기 영상 추출 API와 작업 검증 하네스 구현](https://github.com/Juhye0k/short-form/commit/32e992cdefccb9668bcbc2af38499486961da89c).
- 원격 브랜치: [feat/video-002-async-extraction](https://github.com/Juhye0k/short-form/tree/feat/video-002-async-extraction). main에는 병합하지 않았다.
- 해당 구현 커밋의 [CI 실행 43694535440](https://github.com/Juhye0k/short-form/actions/runs/43694535440): checks와 integration 모두 성공. 로컬 검사 결과와 별도로 GitHub Linux 환경에서 확인했다.
- Wiki는 작업 기록·목차·상태·실행 안내를 동기화하고 코드 링크를 게시된 구현 커밋으로 고정한다. 이후 문서 변경의 CI는 해당 변경 커밋의 실행을 별도로 확인하며, 위 실행 결과를 후속 커밋의 결과로 간주하지 않는다.

## 남은 한계

자동 장애 감지·outbox·재시도·인증·웹 편집·AI·SNS는 미구현이다. 실제 워커 강제 종료·hard timeout·부하 실험은 수행하지 않았다. 소프트 시간 초과 처리는 대역 예외로, 중단 처리 충돌은 실제 DB로 검증했다. 기존 Starlette/httpx 사용 중단 예정 경고와 로컬 pytest 캐시 권한 경고는 남아 있다.
