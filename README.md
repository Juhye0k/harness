# Shortform Harness

FastAPI + PostgreSQL + Redis + Celery를 사용하는 숏폼 서비스의 **초기 개발 기반**입니다. 현재 제품 기능은 구현하지 않았습니다.

![시스템 아키텍처](docs/architecture.png)

[확대 가능한 SVG](docs/architecture.svg) · [아키텍처 설명](docs/architecture.md) · [최소 하네스](docs/harness.md)

## 현재 범위

| 준비된 것 | 아직 구현하지 않은 것 |
|---|---|
| API 생존·의존성 상태 점검 | 영상 링크 수집·업로드 |
| DB 연결과 Alembic 설정 | 프로젝트·작업·자막 테이블 |
| Celery 설정과 진단 작업 | 음성·영상·텍스트 분석·점수 계산 |
| 로컬 Compose, 단위·통합 검사, CI | FFmpeg 렌더링·객체 저장소 연동 |
| 에이전트 작업 규칙과 리뷰 기준 | 인증·비용 제한·자동 복구·SNS 게시 |

`/health/ready`는 PostgreSQL·Redis 연결만 검사합니다. Celery 워커의 생존·작업 소비 여부는 별도 통합 검사로 확인합니다. DB migration은 아직 비어 있으며 업무 테이블을 생성하지 않습니다.

## 빠른 시작: Docker

Docker Desktop의 Linux 컨테이너 엔진을 먼저 실행합니다. 아래 명령은 이 저장소 루트에서 실행합니다.

```powershell
docker compose up --build -d
docker compose ps
curl.exe http://localhost:8000/health/live
curl.exe http://localhost:8000/health/ready
```

- API 문서: http://localhost:8000/docs
- 로그: `docker compose logs -f api worker`
- 중지: `docker compose down` (데이터 볼륨 유지)
- 기본 포트: API 8000, PostgreSQL 5432, Redis 6379. 기존 서비스와 충돌하면 Compose의 호스트 포트와 로컬 환경 변수를 함께 변경합니다.

Compose는 **로컬 개발용**입니다. 예시 DB 암호와 인증 없는 Redis를 포함하며 호스트 포트는 127.0.0.1에만 바인딩합니다. 외부 공개 배포에는 인증, 비밀 관리, TLS, 백업, 네트워크 분리 등의 별도 구성이 필요합니다.

## 로컬 Python 개발

uv와 Python 3.12를 사용합니다. uv.lock이 정확한 패키지 버전을 고정합니다.

```powershell
uv sync --locked
Copy-Item .env.example .env
docker compose up -d postgres redis
uv run uvicorn app.main:app --reload
```

다른 터미널에서 워커는 Docker로 실행합니다.

```powershell
docker compose up --build -d worker
```

Celery 워커는 Linux 컨테이너 또는 WSL2에서 실행하는 구성을 기준으로 합니다. Windows에서 `--pool=solo`로 우회한 결과를 운영 동작 검증으로 대체하지 않습니다.

## 검사

외부 인프라 없이 실행하는 기본 검사:

```powershell
uv run python scripts/verify.py
```

Ruff 오류 검사 → 서식 검사 → 단위 검사 → Alembic 오프라인 설정 검사를 실행합니다. 하나라도 실패하면 실패 코드로 종료합니다.

실제 DB·Redis·워커 연결 검사:

```powershell
docker compose up -d postgres redis
# 기존 워커가 진단 메시지를 가져가지 않도록 잠시 중지
docker compose stop worker
# 진단 결과만 Redis에 잠시 저장하는 별도 워커
docker compose run -d --name shortform-diagnostic-worker worker /app/.venv/bin/celery -A app.worker:celery_app --result-backend redis://redis:6379/0 worker --loglevel=INFO --concurrency=1
$env:RUN_INTEGRATION = "1"
uv run pytest -m integration -q
Remove-Item Env:RUN_INTEGRATION
docker stop shortform-diagnostic-worker
docker rm shortform-diagnostic-worker
```

진단 결과는 테스트 종료 시 제거합니다. 일반 워커는 결과 backend를 사용하지 않으며, 향후 제품 작업 상태는 PostgreSQL에 저장할 계획입니다. 테스트가 중단되면 진단 컨테이너를 수동 정리합니다.

GitHub Actions는 기본 검사와 Linux 서비스 기반 통합 검사·Docker 빌드를 실행합니다. 이 워크플로는 자동 배포나 유료 AI 호출을 하지 않습니다. 필수 검사 병합 차단은 GitHub ruleset에서 별도 설정해야 하며 파일만으로 활성화되지 않습니다.

## 구조

```text
app/
  main.py            # HTTP 상태 점검
  config.py          # 환경 변수
  db.py              # 지연 연결·SQLAlchemy metadata
  worker.py          # Celery 실행 설정·진단
  domain/            # 향후 점수·구간 규칙
  services/          # 향후 처리 흐름
  adapters/          # 향후 AI·영상·저장소 연결
migrations/          # Alembic 설정, 업무 migration 없음
tests/               # 기본 검사와 별도 인프라 통합 검사
scripts/verify.py    # 로컬·CI 공통 진입점
docs/                # 설계, 다이어그램, 하네스 설명
.github/             # CI와 PR 검토 양식
```

## 다음 개발 순서

1. 작업·영상 데이터 모델과 migration 설계
2. 작업 등록·중복 처리·실패 상태·전달 누락 복구 설계
3. 작은 샘플 영상의 추출·검증
4. 파일 저장소와 업로드 연결
5. 분석 특징·점수 계산·고정 데이터 평가

현재는 위 기능을 구현하지 않고 경계와 실행 환경만 준비했습니다. 기존 화면 프로토타입과의 API 연결도 아직 하지 않았습니다.
