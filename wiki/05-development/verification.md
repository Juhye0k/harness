# 검증 계층과 실행 방법

> 상태: 현재 검사 + 후속 평가 방향 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../README.md) · [카테고리 목차](README.md)

## 검사 범위

| 검사 | 현재 확인하는 것 | 확인하지 않는 것 |
|---|---|---|
| Ruff | 코드 오류 패턴·서식 | 업무 결과의 정확성 |
| 단위 검사 6개 | 생존 점검의 독립성·준비 점검의 성공/실패·정보 비노출·환경 설정 | 실제 DB·워커 |
| 통합 검사 2개 | 실제 PostgreSQL·Redis 연결과 진단 작업 소비 | 영상·작업 복구 |
| Alembic | 오프라인 설정·CI 실제 접속 | 업무 migration 정확성: 아직 없음 |
| Docker 빌드 | 이미지 생성 | 운영 배포·고가용성 |

숫자는 2026-11-15 기준이며 테스트 추가 시 갱신한다.

## 기본 검사

```powershell
uv sync --locked
uv run python scripts/verify.py
```

첫 실패에서 비정상 종료한다. 기본 검사는 외부 인프라를 사용하지 않고 integration 표시 테스트를 제외한다. 일반 `pytest` 실행에서도 RUN_INTEGRATION=1이 아니면 통합 검사는 건너뛴다.

## 실제 워커 통합 검사 — 로컬 개발 전용

전용 테스트 환경에서 실행한다. 기존 worker를 잠시 중지해 진단 메시지가 결과 backend 없는 워커로 가지 않게 한다. 아래 finally는 검사 실패 시에도 진단 컨테이너와 환경 변수를 정리한다.

```powershell
docker compose up -d postgres redis
docker compose build worker
docker compose stop worker
$previousIntegration = $env:RUN_INTEGRATION
try {
    docker compose run -d --name shortform-diagnostic-worker worker /app/.venv/bin/celery -A app.worker:celery_app --result-backend redis://redis:6379/0 worker --loglevel=INFO --concurrency=1
    if ($LASTEXITCODE -ne 0) { throw '진단 워커 시작 실패' }
    $env:RUN_INTEGRATION = '1'
    uv run pytest -m integration -q
    if ($LASTEXITCODE -ne 0) { throw '통합 검사 실패' }
} finally {
    $env:RUN_INTEGRATION = $previousIntegration
    docker stop shortform-diagnostic-worker
    docker rm shortform-diagnostic-worker
}
```

일반 워커가 필요하면 검사 후 `docker compose up -d worker`로 다시 실행한다. 같은 이름의 진단 컨테이너가 이미 있다면 먼저 로그·상태를 확인하고 정리한다. 테스트 중단 시 결과 키나 컨테이너가 남을 수 있다.

## CI와 검사 증거

GitHub Actions는 checks와 integration 작업을 실행한다. 통합 작업은 서비스 컨테이너·별도 워커를 띄우고 이미지도 빌드한다. 배포·유료 모델 호출은 없다. 통합 실패 시 worker.log가 로그에 출력된다.

코드를 바꾸지 않는 문서 변경은 링크·구현 일치 검토가 중심이다. 저장소 지침상 기본 검사는 실행하되 문서 변경을 이유로 새 업무 테스트를 만들지 않는다.

## 이후 검사

2단계는 출력 파일·실패·중복 처리를, 3단계는 사용자 흐름을, 4단계는 고정 영상의 추천 품질·비용을 추가한다. 실제 모델 평가는 일반 CI와 분리한다.
