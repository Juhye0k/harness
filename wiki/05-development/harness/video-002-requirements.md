# VIDEO-002 요구사항과 검증

> 상태: 구현 검사 계약 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../../README.md) · [하네스 목차](README.md)

제품 코드는 `app/`에 두고, 이를 통제하는 하네스는 지침·검사·CI·기록으로 나눈다. 새로운 프레임워크나 공통 harness 디렉토리를 추가하지 않는다.

| 요구사항 | 구현 책임 | 검증 위치 |
|---|---|---|
| HTTP에서 인코딩하지 않고 202·작업 ID 반환 | API, jobs 서비스 | unit/test_jobs.py |
| DB·발행 실패를 503과 공개 오류로 구분 | repository, publisher, 예외 처리기 | unit/test_jobs.py, integration/test_jobs_flow.py |
| 같은 ID는 queued일 때만 실행 | repository.claim | integration/test_jobs_database.py: 동시 선점 |
| 발행 트랜잭션 완료 전 소비 경쟁 처리 | ID 행 잠금 후 상태 조건 UPDATE | integration/test_jobs_database.py: 발행 성공·실패 경쟁 |
| 실패를 DB에 저장하고 미완료 다운로드 거부 | jobs 서비스, 다운로드 API | unit/test_jobs.py, integration/test_jobs_flow.py |
| 길이·음성·디코딩·원본 보존 | 기존 video 서비스 | media 검사 + 실제 워커 통합 흐름 |
| 완료 메시지 재전달 시 재실행 없음 | 조건부 선점 | integration/test_jobs_flow.py |
| 수동 실패와 늦은 완료가 서로 덮어쓰지 않음 | 조건부 finish/mark_interrupted | integration/test_jobs_database.py |
| 서버 경로·원본 URL·원본 예외 노출 방지 | 공개 응답 허용 목록 | unit/test_jobs.py |
| 개발 DB와 외부 영상 서버를 테스트에서 사용하지 않음 | 격리 Compose, 합성 샘플 워커 | compose.integration.yaml, CI |

실행 방법은 [검증 안내](verification.md), 결과는 [현황 기록](../../07-governance/status.md)에 둔다. 통합 검사에서 다운로드만 합성 파일 복사로 대체한다. FastAPI·PostgreSQL·Redis·Celery·FFmpeg와 다운로드 HTTP는 실제로 실행한다. 네트워크 다운로드의 성공 여부와 강제 종료 복구를 이 검사 결과로 주장하지 않는다.

## 리뷰 기준

행 잠금이 인코딩 중 유지되지 않는지, 발행 실패 후 메시지가 남아도 실행되지 않는지, 늦은 완료가 수동 실패를 덮어쓰지 않는지 확인한다. 재시도 추가 시 현재 조건부 선점만으로 안전하다고 간주하지 않는다. 예외를 사용자에게 그대로 반환하거나 통합 검사를 대역 검사로 교체하면 완료로 인정하지 않는다.

## 발견한 설계 위험

발행자가 `pending → queued`를 아직 커밋하지 않은 순간, 워커가 곧바로 `WHERE status='queued'`를 검사하면 미커밋 행을 건너뛸 수 있다. 구현 리뷰에서 확인한 위험으로, 먼저 ID로 행 잠금을 기다린 뒤 별도 조건부 UPDATE를 수행하도록 정했다. 실제 PostgreSQL 두 연결로 발행 완료 전 선점이 대기하는지, 성공 후 한 번만 실행되는지, 발행 실패 뒤 실행되지 않는지 검사한다.
